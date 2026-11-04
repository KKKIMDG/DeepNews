from __future__ import annotations

from fastapi import HTTPException

from ...config import settings
from .extractor import clean_article_text, extract_token_counts, get_konlpy_analyzer, normalize_published_at
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


def prepare_browser_article(url: str, title: str, text: str, published_at: str = "") -> CrawlResponse:
    """Process supplied plain text without fetching the caller's URL."""
    content = clean_article_text(text)
    if len(content) < 80:
        raise HTTPException(
            status_code=422,
            detail="기사 본문을 찾지 못했습니다. 제목만 있는 기사(속보 등)이거나 본문이 너무 짧습니다.",
        )
    analyzer, _ = get_konlpy_analyzer()
    counts = limit_token_counts(extract_token_counts(content, analyzer))
    return CrawlResponse(title=title.strip(), url=url, content=content,
                         published_at=normalize_published_at(published_at), token_counts=counts, keywords=list(counts))
