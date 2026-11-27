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
# Context (embedding) selection: share of the score from closeness to the title and summary, the MMR trade-off
# between that score and similarity to keywords already picked, and how many candidates get embedded.
CONTEXT_WEIGHT = 0.5
MMR_RELEVANCE = 0.75
MAX_CONTEXT_CANDIDATES = 60


def limit_token_counts(token_counts: dict[str, int]) -> dict[str, int]:
    filtered = {
        word: count
        for word, count in token_counts.items()
        if word not in settings.keyword_stopwords and count > 0
    }
    return dict(
        sorted(filtered.items(), key=lambda item: (-item[1], item[0]))[: settings.keyword_limit]
    )


def keyword_candidates(candidates: dict[str, int], *, title: str, summary: str) -> list[str]:
    """Terms that may become keywords, most frequent first (capped, as each one is embedded for context).

    A term used once must also be in the title or summary, otherwise one-off phrases crowd out the subject.
    """
    eligible = [
        term for term, count in candidates.items()
        if count > 0 and term not in settings.keyword_stopwords and (count > 1 or term in title or term in summary)
    ]
    # Title and summary terms first, so the cap never drops them.
    eligible.sort(key=lambda term: (-(term in title or term in summary), -candidates[term], term))
    return eligible[:MAX_CONTEXT_CANDIDATES]


def keyword_document(title: str, summary: str, content: str) -> str:
    """What a keyword should be close to: the title plus the KoBART summary (or the lead when there is none)."""
    return f"{title}\n{summary or content[:400]}"


def select_keywords(
    candidates: dict[str, int],
    *,
    title: str,
    summary: str,
    content: str,
    doc_freq: dict[str, int],
    total_docs: int,
    context=None,
) -> dict[str, int]:
    """Pick the article's keywords from its noun-phrase counts; returns {term: count} in rank order.

    Base score = (1 + ln count) × IDF × position boost. IDF uses keyword.article_count (articles already carrying
    the term), so words every article has (정부, 기업) sink; a term never seen before counts as seen once.

    context, from analysis.embedding.keyword_context: (document vector, {term: vector}). With it, the score mixes
    in how close each term is to the title and summary in meaning, which drops terms that are frequent but beside
    the point (동반, 우위), and picks by MMR so near-synonyms (유출 / 노출) do not fill the list together.
    """
    lead = content[: max(200, len(content) // 5)]
    scores: dict[str, float] = {}
    for term in keyword_candidates(candidates, title=title, summary=summary):
        idf = math.log((total_docs + 1) / (doc_freq.get(term, 1) + 1)) + 1
        boost = 1 + TITLE_BOOST * (term in title) + SUMMARY_BOOST * (term in summary) + LEAD_BOOST * (term in lead)
        scores[term] = (1 + math.log(candidates[term])) * idf * boost
    if not scores:
        return {}

    vectors: dict = {}
    if context is not None:
        document, vectors = context
        scores = _blend_context(scores, {term: float(vectors[term] @ document) for term in scores if term in vectors})

    picked: list[str] = []
    remaining = set(scores)
    while remaining and len(picked) < settings.keyword_limit:
        def mmr(term: str) -> float:
            # Without context there are no vectors and this is plain score order.
            overlap = max((float(vectors[term] @ vectors[other]) for other in picked
                           if term in vectors and other in vectors), default=0.0)
            return MMR_RELEVANCE * scores[term] - (1 - MMR_RELEVANCE) * overlap

        term = max(sorted(remaining), key=mmr)
        remaining.discard(term)
        # One of 잠수함 / 핵추진잠수함: whichever ranks higher stands for both.
        if any(term in other or other in term for other in picked):
            continue
        picked.append(term)
    return {term: candidates[term] for term in picked}


def _blend_context(scores: dict[str, float], relevance: dict[str, float]) -> dict[str, float]:
    """Both parts rescaled to 0..1 across this article's candidates, then mixed by CONTEXT_WEIGHT."""
    top = max(scores.values())
    low, high = (min(relevance.values()), max(relevance.values())) if relevance else (0.0, 0.0)
    spread = high - low
    return {
        term: (1 - CONTEXT_WEIGHT) * score / top
        + CONTEXT_WEIGHT * ((relevance[term] - low) / spread if term in relevance and spread > 0 else 0.0)
        for term, score in scores.items()
    }


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
