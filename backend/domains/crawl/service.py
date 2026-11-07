from __future__ import annotations

import math

from fastapi import HTTPException

from ...config import settings
from .extractor import clean_article_text, extract_token_counts, get_analyzer, normalize_published_at
from .schemas import CrawlResponse

# Position boosts: the title and the KoBART summary name what the article is about; the lead usually restates it.
TITLE_BOOST = 0.6
SUMMARY_BOOST = 0.4
LEAD_BOOST = 0.2


def limit_token_counts(token_counts: dict[str, int]) -> dict[str, int]:
    filtered = {
        word: count
        for word, count in token_counts.items()
        if word not in settings.keyword_stopwords and count > 0
    }
    return dict(
        sorted(filtered.items(), key=lambda item: (-item[1], item[0]))[: settings.keyword_limit]
    )


def select_keywords(
    candidates: dict[str, int],
    *,
    title: str,
    summary: str,
    content: str,
    doc_freq: dict[str, int],
    total_docs: int,
) -> dict[str, int]:
    """Pick the article's keywords from its noun-phrase counts; returns {term: count} in rank order.

    score = (1 + ln count) × IDF × position boost. IDF uses keyword.article_count (articles already carrying the
    term), so words every article has (정부, 기업) sink; a term never seen before counts as seen once. A term used
    once must also be in the title or summary, otherwise one-off phrases crowd out the subject.
    """
    lead = content[: max(200, len(content) // 5)]
    scores: dict[str, float] = {}
    for term, count in candidates.items():
        in_title, in_summary = term in title, term in summary
        if count <= 0 or term in settings.keyword_stopwords or (count == 1 and not (in_title or in_summary)):
            continue
        idf = math.log((total_docs + 1) / (doc_freq.get(term, 1) + 1)) + 1
        boost = 1 + TITLE_BOOST * in_title + SUMMARY_BOOST * in_summary + LEAD_BOOST * (term in lead)
        scores[term] = (1 + math.log(count)) * idf * boost

    picked: list[str] = []
    for term in sorted(scores, key=lambda item: (-scores[item], item)):
        # One of 잠수함 / 핵추진잠수함: whichever scores higher stands for both.
        if any(term in other or other in term for other in picked):
            continue
        picked.append(term)
        if len(picked) == settings.keyword_limit:
            break
    return {term: candidates[term] for term in picked}


def warm_up() -> None:
    # Kiwi loads its model on first use (~2 s).
    analyzer, _ = get_analyzer()
    analyzer.nouns("정부는 오늘 내년도 예산안을 발표했다.")


def prepare_browser_article(url: str, title: str, text: str, published_at: str = "") -> CrawlResponse:
    """Process supplied plain text without fetching the caller's URL.

    token_counts holds every noun-phrase candidate; the caller picks the keywords with select_keywords once the
    summary exists.
    """
    content = clean_article_text(text)
    if len(content) < 80:
        raise HTTPException(
            status_code=422,
            detail="기사 본문을 찾지 못했습니다. 제목만 있는 기사(속보 등)이거나 본문이 너무 짧습니다.",
        )
    analyzer, _ = get_analyzer()
    counts = extract_token_counts(content, analyzer)
    return CrawlResponse(title=title.strip(), url=url, content=content,
                         published_at=normalize_published_at(published_at), token_counts=counts, keywords=list(counts))
