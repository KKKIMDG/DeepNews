from __future__ import annotations

from typing import Any
from urllib.parse import urlparse
from fastapi import HTTPException

from ...database import get_session
from ..analysis.service import analyze_article
from ..crawl.schemas import CrawlResponse
from ..crawl.service import crawl_article, limit_token_counts, prepare_browser_article
from .models import News, NewsAnalysis
from . import repository
from .schemas import (
    AdLikelihoodPayload,
    AnalyzeArticleApiResponse,
    ArticlePayload,
    KeywordPayload,
    NewsCrawlRequest,
)


def ad_label_for(score: float) -> str:
    if score < 0:
        return "미분석"
    if score >= 0.8:
        return "광고성 높음"
    if score >= 0.4:
        return "검토 필요"
    return "광고성 낮음"


def merge_extra_data(payload: NewsCrawlRequest) -> dict[str, Any]:
    extra_data = dict(payload.extraData or {})
    for key, value in (payload.model_extra or {}).items():
        if key not in {
            "title",
            "url",
            "source",
            "content",
            "original_content",
            "published_at",
            "token_counts",
            "extraData",
        }:
            extra_data[key] = value
    return extra_data


def build_article_data_from_crawl(payload: NewsCrawlRequest) -> dict[str, Any]:
    limited = limit_token_counts(payload.token_counts or {})
    keywords = [{"term": term, "count": count} for term, count in limited.items()]
    extra_data = merge_extra_data(payload)
    extra_data["token_counts"] = limited
    extra_data["keywords"] = keywords
    if payload.original_content:
        extra_data.setdefault("original_content", payload.original_content)
    return {
        "source": payload.source,
        "content": payload.content,
        "publishedAt": payload.published_at or "",
        "extraData": extra_data,
    }


def build_article_data_from_analysis(crawl_result: CrawlResponse) -> dict[str, Any]:
    return {
        "source": urlparse(crawl_result.url).hostname or "unknown",
        "content": crawl_result.content,
        "publishedAt": crawl_result.published_at,
        "extraData": {
            "token_counts": crawl_result.token_counts,
            "keywords": [
                {"term": term, "count": count}
                for term, count in crawl_result.token_counts.items()
            ],
        },
    }


def save_crawled_news(payload: NewsCrawlRequest) -> int:
    article_data = build_article_data_from_crawl(payload)
    with get_session() as session:
        news = repository.upsert_news(session, payload.title, payload.url, article_data)
        repository.save_keyword_mappings(session, news.id, payload.token_counts)
        return news.id


def bulk_save_crawled_news(payloads: list[NewsCrawlRequest]) -> dict[str, Any]:
    success_count = 0
    fail_count = 0
    fail_messages: list[str] = []

    for payload in payloads:
        try:
            save_crawled_news(payload)
            success_count += 1
        except Exception as exception:
            fail_count += 1
            fail_messages.append(f"{payload.title} : {exception}")

    return {
        "total": len(payloads),
        "success": success_count,
        "fail": fail_count,
        "errors": fail_messages,
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


def serialize_analysis_response(news: News, analysis: NewsAnalysis, cached: bool) -> AnalyzeArticleApiResponse:
    article_data = news.article_data or {}
    score = -1.0 if analysis.ad_probability is None else float(analysis.ad_probability)
    return AnalyzeArticleApiResponse(
        newsId=news.id,
        cached=cached,
        article=ArticlePayload(title=news.title, url=news.url),
        keywords=extract_keywords_from_article_data(article_data),
        summary=analysis.summary or "",
        recommendations=[{"title": news.title, "url": news.url}],
        adLikelihood=AdLikelihoodPayload(label=ad_label_for(score), score=score),
    )


def analyze_or_get(url: str, title: str | None = None, content: str | None = None) -> AnalyzeArticleApiResponse:
    browser_article = prepare_browser_article(url, title or "", content) if content is not None else None
    with get_session() as session:
        existing_news = repository.fetch_news_by_url(session, url)
        if browser_article and existing_news:
            # Browser input must not silently replace a shared article with different text.
            stored_content = (existing_news.article_data or {}).get("content")
            if stored_content != browser_article.content:
                raise HTTPException(status_code=409, detail="저장된 기사와 본문이 다릅니다. 기사 내용 변경 여부를 확인해 주세요.")
        if existing_news and existing_news.analysis:
            return serialize_analysis_response(existing_news, existing_news.analysis, cached=True)

        crawl_result = browser_article or crawl_article(url)
        article_data = build_article_data_from_analysis(crawl_result)
        article_data["extraData"]["content_origin"] = "browser" if browser_article else "server"
        news = repository.upsert_news(session, crawl_result.title, crawl_result.url, article_data)
        repository.save_keyword_mappings(session, news.id, crawl_result.token_counts)

        analysis_result = analyze_article(crawl_result.url, crawl_result.title, crawl_result.content)
        analysis = repository.upsert_news_analysis(
            session=session,
            news_id=news.id,
            summary=analysis_result["summary"],
            ad_probability=analysis_result["ad_probability"],
            is_clickbait=analysis_result["is_clickbait"],
            named_entities=analysis_result["named_entities"],
        )

        return serialize_analysis_response(news, analysis, cached=False)
