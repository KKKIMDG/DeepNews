"""BigKinds (한국언론진흥재단) Excel export → news rows.

The export carries only the first 200 characters of each article (copyright), so imported rows
are recommendation candidates, not analysis input: they are flagged `content_partial` and the full
text arrives later when a user analyzes the article in the extension.
"""
from __future__ import annotations

import html
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from ..domains.crawl.extractor import canonical_article_url

SOURCE_NAME = "bigkinds"
MAX_URL_LENGTH = 512
MAX_TITLE_LENGTH = 512
REQUIRED_COLUMNS = ("뉴스 식별자", "일자", "언론사", "제목", "통합 분류1", "키워드", "본문", "URL")
CATEGORY_COLUMNS = ("통합 분류1", "통합 분류2", "통합 분류3")


@dataclass(frozen=True)
class BigKindsArticle:
    bigkinds_id: str
    title: str
    url: str
    publisher: str
    published_at: str
    categories: list[str]
    lead: str
    token_counts: dict[str, int]

    def article_data(self, import_time: str) -> dict[str, Any]:
        return {
            "source": urlparse(self.url).hostname or self.publisher,
            "content": self.lead,
            "publishedAt": self.published_at,
            "extraData": {
                "content_origin": SOURCE_NAME,
                "content_partial": True,
                "bigkinds_id": self.bigkinds_id,
                "publisher": self.publisher,
                "category": self.categories[0] if self.categories else "",
                "categories": self.categories,
                "import_time": import_time,
                "token_counts": self.token_counts,
                "keywords": [{"term": term, "count": count} for term, count in self.token_counts.items()],
            },
        }


@dataclass
class ParseResult:
    articles: list[BigKindsArticle] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)


def _text(value: Any) -> str:
    # pandas gives NaN (a float) for empty cells; read the sheet with dtype=str.
    return value.strip() if isinstance(value, str) else ""


def _published_at(value: str) -> str:
    try:
        return datetime.strptime(value[:8], "%Y%m%d").date().isoformat()
    except ValueError:
        return ""


def keyword_counts(raw: str) -> dict[str, int]:
    words = [word.strip() for word in raw.split(",")]
    return dict(Counter(word for word in words if len(word) >= 2))


def parse_rows(
    rows: Iterable[dict[str, Any]],
    limit_counts: Callable[[dict[str, int]], dict[str, int]],
) -> ParseResult:
    result = ParseResult()
    seen_urls: set[str] = set()

    for row in rows:
        # Some publishers' URLs come HTML-escaped ('&amp;'), which would never match the browser's location.href.
        # Naver links are stored in the same canonical form the extension's analyze requests use.
        url = canonical_article_url(html.unescape(_text(row.get("URL"))))
        title = _text(row.get("제목"))
        if _text(row.get("분석제외 여부")):
            # BigKinds marks duplicates ('중복') and outliers ('예외') itself.
            result.skipped["bigkinds_excluded"] += 1
            continue
        if not url:
            result.skipped["no_url"] += 1
            continue
        if urlparse(url).scheme not in {"http", "https"} or len(url) > MAX_URL_LENGTH:
            result.skipped["invalid_url"] += 1
            continue
        if not title:
            result.skipped["no_title"] += 1
            continue
        if url in seen_urls:
            result.skipped["duplicate_url"] += 1
            continue
        seen_urls.add(url)

        result.articles.append(
            BigKindsArticle(
                bigkinds_id=_text(row.get("뉴스 식별자")),
                title=title[:MAX_TITLE_LENGTH],
                url=url,
                publisher=_text(row.get("언론사")),
                published_at=_published_at(_text(row.get("일자"))),
                categories=[category for column in CATEGORY_COLUMNS if (category := _text(row.get(column)))],
                lead=_text(row.get("본문")),
                token_counts=limit_counts(keyword_counts(_text(row.get("키워드")))),
            )
        )
    return result


def read_export(path: str) -> list[dict[str, Any]]:
    import pandas as pd

    # dtype=str keeps identifiers like '02100101.20261030123456789' from collapsing into floats.
    frame = pd.read_excel(path, header=0, dtype=str)
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"BigKinds 엑셀 형식이 아닙니다. 누락된 컬럼: {', '.join(missing)}")
    return frame.to_dict(orient="records")
