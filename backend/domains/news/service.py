from __future__ import annotations

import copy
import logging
import re
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException

from ...database import get_session
from ..analysis.embedding import keyword_context
from ..analysis.service import AD_HIGH_THRESHOLD, AD_REVIEW_THRESHOLD, analyze_article
from ..auth.dependencies import CurrentUser
from ..personalization import service as personalization
from ..personalization.schemas import RecommendationPayload
from ..crawl.schemas import CrawlResponse
from ..crawl.extractor import canonical_article_url
from ..crawl.service import keyword_candidates, keyword_document, prepare_browser_article, select_keywords
from .models import News, NewsAnalysis
from . import repository
from .schemas import (
    AdLikelihoodPayload,
    AnalyzeArticleApiResponse,
    ArticlePayload,
    KeywordPayload,
    ReportResponse,
)

logger = logging.getLogger(__name__)

# Distinct users who must report a shared analysis before it is dropped and re-analyzed.
REANALYSIS_REPORTS = 3
# Share of the BigKinds lead's character bigrams that must appear in the submitted text.
LEAD_MATCH_RATIO = 0.6
# Stored extraData that describes the old text and must not survive a replacement.
REPLACED_EXTRA_KEYS = ("content_partial", "original_content", "token_counts", "keywords")


def ad_label_for(score: float) -> str:
    if score < 0:
        return "미분석"
    if score >= AD_HIGH_THRESHOLD:
        return "광고성 높음"
    if score >= AD_REVIEW_THRESHOLD:
        return "검토 필요"
    return "광고성 낮음"


def _bigrams(text: str) -> set[str]:
    compact = re.sub(r"[^0-9A-Za-z가-힣]", "", text)
    return {compact[i:i + 2] for i in range(len(compact) - 1)}


def matches_lead(lead: str, content: str) -> bool:
    """Whether submitted text plausibly is the article whose first 200 characters BigKinds gave us."""
    lead_grams = _bigrams(lead[:200])
    if len(lead_grams) < 20:
        return True  # too little to judge
    return len(lead_grams & _bigrams(content)) / len(lead_grams) >= LEAD_MATCH_RATIO


def is_reusable(news: News | None) -> bool:
    if news is None or news.analysis is None:
        return False
    extra = (news.article_data or {}).get("extraData") or {}
    if extra.get("content_partial"):
        return False
    # Placeholder rows from old batch runs (ad_probability = -1) get a real analysis on the next request.
    return news.analysis.ad_probability is not None and float(news.analysis.ad_probability) >= 0


def build_article_data(
    article: CrawlResponse, keywords: dict[str, int], stored_data: dict[str, Any], user: CurrentUser, lead_verified: bool
) -> dict[str, Any]:
    # Keep what earlier sources knew (BigKinds category/publisher, publish date); replace only text-derived parts.
    extra = {
        key: value
        for key, value in (stored_data.get("extraData") or {}).items()
        if key not in REPLACED_EXTRA_KEYS
    }
    extra.update(
        token_counts=keywords,
        keywords=[{"term": term, "count": count} for term, count in keywords.items()],
        content_origin="browser",
        submitted_by=user.id,
    )
    if lead_verified:
        extra["lead_verified"] = True
    return {
        "source": stored_data.get("source") or urlparse(article.url).hostname or "unknown",
        "content": article.content,
        "publishedAt": stored_data.get("publishedAt") or article.published_at,
        "extraData": extra,
    }


def extract_keywords_from_article_data(article_data: dict[str, Any]) -> list[KeywordPayload]:
    extra_data = article_data.get("extraData") or {}
    keywords = extra_data.get("keywords")
    if isinstance(keywords, list):
        payloads = []
        for item in keywords:
            if isinstance(item, dict):
                term = str(item.get("term", "")).strip()
                count = int(item.get("count", 0) or 0)
                if term:
                    payloads.append(KeywordPayload(term=term, count=count))
        if payloads:
            return payloads[:8]

    token_counts = extra_data.get("token_counts")
    if isinstance(token_counts, dict):
        items = sorted(token_counts.items(), key=lambda item: (-int(item[1]), item[0]))
        return [KeywordPayload(term=str(term), count=int(count)) for term, count in items[:8]]
    return []


def serialize_analysis_response(
    news: News,
    analysis: NewsAnalysis,
    cached: bool,
    recommendations: list[RecommendationPayload],
    user: CurrentUser | None = None,
    report_count: int = 0,
    reported_by_me: bool = False,
    recommendations_deferred: bool = False,
) -> AnalyzeArticleApiResponse:
    article_data = news.article_data or {}
    extra = article_data.get("extraData") or {}
    score = -1.0 if analysis.ad_probability is None else float(analysis.ad_probability)
    return AnalyzeArticleApiResponse(
        newsId=news.id,
        cached=cached,
        article=ArticlePayload(title=news.title, url=news.url),
        keywords=extract_keywords_from_article_data(article_data),
        summary=analysis.summary or "",
        recommendations=recommendations,
        recommendationsDeferred=recommendations_deferred,
        adLikelihood=AdLikelihoodPayload(label=ad_label_for(score), score=score),
        contentOrigin=str(extra.get("content_origin") or ""),
        sharedFromOther=cached and (user is None or extra.get("submitted_by") != user.id),
        reportCount=report_count,
        reportedByMe=reported_by_me,
    )


def personalize_response(
    session, news: News, analysis: NewsAnalysis, cached: bool, user: CurrentUser | None, defer: bool = False
) -> AnalyzeArticleApiResponse:
    # A savepoint keeps a personalization failure from rolling back the (expensive) analysis itself.
    recommendations = []
    try:
        with session.begin_nested():
            if user is not None:
                personalization.record_read(session, user, news.id)
            if not defer:
                recommendations = personalization.recommend(session, user, current_news_id=news.id)
    except Exception:
        logger.exception("개인화 처리 실패 (news_id=%s)", news.id)
    report_count, reported_by_me = repository.report_counts(session, news.id, user.id if user else None)
    return serialize_analysis_response(
        news, analysis, cached, recommendations, user, report_count, reported_by_me, recommendations_deferred=defer
    )


def analyze_or_get(
    url: str,
    title: str,
    content: str,
    user: CurrentUser,
    published_at: str = "",
    defer_recommendations: bool = False,
) -> AnalyzeArticleApiResponse:
    """Serve the shared analysis of an article, or analyze the text the user's browser extracted.

    The server never fetches the URL. A stored analysis is never overwritten by a different text;
    users report a wrong one instead (report_news).
    """
    url = canonical_article_url(url)
    with get_session() as session:
        existing = repository.fetch_news_by_canonical_url(session, url)
        if is_reusable(existing):
            return personalize_response(session, existing, existing.analysis, True, user, defer_recommendations)
        # Snapshot: ORM objects expire once this session commits.
        target_url = existing.url if existing else url  # a legacy-URL row is updated in place, not duplicated
        stored_title = existing.title if existing else ""
        stored_data = copy.deepcopy(existing.article_data or {}) if existing else {}

    stored_partial = bool((stored_data.get("extraData") or {}).get("content_partial"))
    if stored_partial and not matches_lead(stored_data.get("content", ""), content):
        # Otherwise anyone could claim an imported BigKinds candidate with made-up text for everyone.
        raise HTTPException(
            status_code=409,
            detail="저장된 기사 정보(빅카인즈)와 본문이 달라 분석하지 않았습니다. 기사 페이지가 맞는지 확인해 주세요.",
        )

    article = prepare_browser_article(target_url, title, content, published_at)
    # Inference runs with no DB session open, so slow requests don't pin pooled connections.
    result = analyze_article(article.url, article.title, article.content)
    # Keyword context vectors also come from a model, so they too are computed before the session opens.
    keyword_title = stored_title or article.title
    context = keyword_context(
        keyword_document(keyword_title, result["summary"], article.content),
        keyword_candidates(article.token_counts, title=keyword_title, summary=result["summary"]),
    )

    with get_session() as session:
        current = repository.fetch_news_by_url(session, target_url)
        if is_reusable(current):  # another request finished the same article meanwhile
            return personalize_response(session, current, current.analysis, True, user, defer_recommendations)
        # Keywords are picked after inference so terms in the summary can rank higher.
        doc_freq, total_docs = repository.keyword_document_frequency(session, article.token_counts)
        keywords = select_keywords(article.token_counts, title=keyword_title, summary=result["summary"],
                                   content=article.content, doc_freq=doc_freq, total_docs=total_docs, context=context)
        article_data = build_article_data(article, keywords, stored_data, user, lead_verified=stored_partial)
        news = repository.upsert_news(session, stored_title or article.title, target_url, article_data)
        repository.save_keyword_mappings(session, news.id, keywords)
        analysis = repository.upsert_news_analysis(
            session=session,
            news_id=news.id,
            summary=result["summary"],
            ad_probability=result["ad_probability"],
            is_clickbait=result["is_clickbait"],
            named_entities=result["named_entities"],
        )
        repository.clear_reports(session, news.id)
        return personalize_response(session, news, analysis, False, user, defer_recommendations)


def report_news(news_id: int, user: CurrentUser, reason: str) -> ReportResponse:
    with get_session() as session:
        news = session.get(News, news_id)
        if news is None:
            raise HTTPException(status_code=404, detail="없는 기사입니다.")
        if news.analysis is None:
            raise HTTPException(status_code=409, detail="분석 결과가 없는 기사입니다.")
        repository.add_report(session, news_id, user.id, reason.strip())
        report_count, reported_by_me = repository.report_counts(session, news_id, user.id)
        reanalysis = report_count >= REANALYSIS_REPORTS
        if reanalysis:
            # The next browser submission re-analyzes the article; its reports are cleared then.
            repository.delete_news_analysis(session, news_id)
        return ReportResponse(reportCount=report_count, reportedByMe=reported_by_me, reanalysis=reanalysis)
