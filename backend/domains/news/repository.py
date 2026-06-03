from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from .models import ArticleKeyword, Keyword, News, NewsAnalysis
from ..crawl.service import limit_token_counts


def fetch_news_by_url(session: Session, url: str) -> News | None:
    statement = (
        select(News)
        .options(selectinload(News.analysis), selectinload(News.keywords).selectinload(ArticleKeyword.keyword))
        .where(News.url == url)
    )
    return session.scalar(statement)


def fetch_news_analysis(session: Session, news_id: int) -> NewsAnalysis | None:
    return session.scalar(select(NewsAnalysis).where(NewsAnalysis.news_id == news_id))


def upsert_news(session: Session, title: str, url: str, article_data: dict[str, Any]) -> News:
    news = session.scalar(select(News).where(News.url == url))
    if news is None:
        news = News(title=title, url=url, article_data=article_data)
        session.add(news)
        session.flush()
        return news

    news.title = title
    news.article_data = article_data
    session.flush()
    return news


def _refresh_keyword_stats(session: Session, keyword_ids: set[int]) -> None:
    if not keyword_ids:
        return

    stats_rows = session.execute(
        select(
            ArticleKeyword.keyword_id,
            func.coalesce(func.sum(ArticleKeyword.count), 0),
            func.count(ArticleKeyword.news_id),
        )
        .where(ArticleKeyword.keyword_id.in_(keyword_ids))
        .group_by(ArticleKeyword.keyword_id)
    ).all()
    stats_map = {keyword_id: (int(total_count), int(article_count)) for keyword_id, total_count, article_count in stats_rows}

    keywords = session.scalars(select(Keyword).where(Keyword.id.in_(keyword_ids))).all()
    for keyword in keywords:
        total_count, article_count = stats_map.get(keyword.id, (0, 0))
        keyword.total_count = total_count
        keyword.article_count = article_count

    session.flush()


def save_keyword_mappings(session: Session, news_id: int, token_counts: dict[str, int]) -> None:
    limited = limit_token_counts(token_counts)
    if not limited:
        session.execute(delete(ArticleKeyword).where(ArticleKeyword.news_id == news_id))
        session.flush()
        return

    existing_mappings = session.scalars(
        select(ArticleKeyword).where(ArticleKeyword.news_id == news_id)
    ).all()
    affected_keyword_ids = {mapping.keyword_id for mapping in existing_mappings}

    session.execute(delete(ArticleKeyword).where(ArticleKeyword.news_id == news_id))

    words = sorted(limited.keys())
    existing_keywords = session.scalars(select(Keyword).where(Keyword.word.in_(words))).all()
    keyword_map = {keyword.word: keyword for keyword in existing_keywords}

    for word in words:
        if word in keyword_map:
            continue
        keyword = Keyword(word=word)
        session.add(keyword)
        session.flush()
        keyword_map[word] = keyword

    for word, count in limited.items():
        keyword = keyword_map[word]
        affected_keyword_ids.add(keyword.id)
        session.add(ArticleKeyword(news_id=news_id, keyword_id=keyword.id, count=count))

    session.flush()
    _refresh_keyword_stats(session, affected_keyword_ids)


def upsert_news_analysis(
    session: Session,
    news_id: int,
    summary: str,
    ad_probability: float,
    is_clickbait: bool,
    named_entities: list[Any],
) -> NewsAnalysis:
    analysis = session.scalar(select(NewsAnalysis).where(NewsAnalysis.news_id == news_id))
    if analysis is None:
        analysis = NewsAnalysis(
            news_id=news_id,
            summary=summary,
            ad_probability=round(float(ad_probability), 2),
            is_clickbait=is_clickbait,
            named_entities=named_entities,
        )
        session.add(analysis)
        session.flush()
        return analysis

    analysis.summary = summary
    analysis.ad_probability = round(float(ad_probability), 2)
    analysis.is_clickbait = is_clickbait
    analysis.named_entities = named_entities
    session.flush()
    return analysis
