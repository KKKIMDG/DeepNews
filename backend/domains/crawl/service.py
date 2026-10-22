from __future__ import annotations

from fastapi import HTTPException

from .extractor import (
    clean_article_text,
    extract_article,
    extract_token_counts,
    get_article_config,
    get_konlpy_analyzer,
    to_iso_datetime,
)

from ...config import settings
from .schemas import CrawlResponse


def limit_token_counts(token_counts: dict[str, int]) -> dict[str, int]:
    filtered = {
        word: count
        for word, count in token_counts.items()
        if word not in settings.keyword_stopwords and count > 0
    }
    return dict(
        sorted(filtered.items(), key=lambda item: (-item[1], item[0]))[: settings.keyword_limit]
    )


def crawl_article(url: str) -> CrawlResponse:
    config = get_article_config()
    analyzer, analyzer_name = get_konlpy_analyzer()
    print(f"단건 크롤링 요청: {url} / analyzer={analyzer_name}")

    try:
        title, original_content, published_at = extract_article(url, config)
        if not original_content:
            raise ValueError("Empty article content")

        content = clean_article_text(original_content)
        token_counts = extract_token_counts(content, analyzer)
        limited_token_counts = limit_token_counts(token_counts)
        keywords = list(limited_token_counts.keys())

        if not content:
            raise ValueError("Cleaned article content is empty")
    except Exception as exception:
        raise HTTPException(status_code=500, detail=f"크롤링 실패: {exception}") from exception

    return CrawlResponse(
        title=title,
        url=url,
        content=content,
        published_at=to_iso_datetime(published_at),
        token_counts=limited_token_counts,
        keywords=keywords,
    )


def prepare_browser_article(url: str, title: str, text: str) -> CrawlResponse:
    """Process supplied plain text without fetching the caller's URL."""
    content = clean_article_text(text)
    if len(content) < 80:
        raise HTTPException(status_code=422, detail="정제 후 기사 본문이 너무 짧습니다.")
    analyzer, _ = get_konlpy_analyzer()
    counts = limit_token_counts(extract_token_counts(content, analyzer))
    return CrawlResponse(title=title.strip(), url=url, content=content,
                         published_at="", token_counts=counts, keywords=list(counts))
