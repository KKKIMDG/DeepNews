from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from .models import ArticleKeyword, Keyword, News, NewsAnalysis, NewsReport
from ..crawl.extractor import NAVER_CANONICAL_HOSTS, NAVER_SECTION_HOSTS
from ..crawl.service import limit_token_counts


def fetch_news_by_url(session: Session, url: str) -> News | None:
    statement = (
        select(News)
        .options(selectinload(News.analysis), selectinload(News.keywords).selectinload(ArticleKeyword.keyword))
        .where(News.url == url)
    )
    return session.scalar(statement)


def fetch_news_by_canonical_url(session: Session, url: str) -> News | None:
    """Exact match first, then Naver rows saved before canonicalization (the same URL plus ?sid=...).

    Only Naver: elsewhere the query often names the article (view.php?id=1), so a prefix match would be another article.
    """
    news = fetch_news_by_url(session, url)
    host = urlparse(url).hostname or ""
    if news is not None or "?" in url or host not in NAVER_CANONICAL_HOSTS | NAVER_SECTION_HOSTS:
        return news
    statement = (
        select(News)
        .options(selectinload(News.analysis), selectinload(News.keywords).selectinload(ArticleKeyword.keyword))
        .where(News.url.startswith(url + "?", autoescape=True))
        .order_by(News.id)
        .limit(1)
    )
    return session.scalar(statement)


def fetch_news_analysis(session: Session, news_id: int) -> NewsAnalysis | None:
    return session.scalar(select(NewsAnalysis).where(NewsAnalysis.news_id == news_id))


def upsert_news(session: Session, title: str, url: str, article_data: dict[str, Any]) -> News:
    # INSERT ... ON CONFLICT: two users analyzing the same new article must not race into a UniqueViolation.
    statement = (
        pg_insert(News)
        .values(title=title, url=url, article_data=article_data)
        .on_conflict_do_update(index_elements=[News.url], set_={"title": title, "article_data": article_data})
        .returning(News.id)
    )
    news_id = session.execute(statement).scalar_one()
    return session.get(News, news_id, populate_existing=True)


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
    session.execute(
        pg_insert(Keyword).values([{"word": word} for word in words]).on_conflict_do_nothing(index_elements=[Keyword.word])
    )
    keyword_map = {keyword.word: keyword for keyword in session.scalars(select(Keyword).where(Keyword.word.in_(words)))}

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
    values = {
        "summary": summary,
        "ad_probability": round(float(ad_probability), 2),
        "is_clickbait": is_clickbait,
        "named_entities": named_entities,
        "analyzed_at": func.now(),
    }
    statement = (
        pg_insert(NewsAnalysis)
        .values(news_id=news_id, **values)
        .on_conflict_do_update(index_elements=[NewsAnalysis.news_id], set_=values)
        .returning(NewsAnalysis.id)
    )
    analysis_id = session.execute(statement).scalar_one()
    return session.get(NewsAnalysis, analysis_id, populate_existing=True)


def delete_news_analysis(session: Session, news_id: int) -> None:
    session.execute(delete(NewsAnalysis).where(NewsAnalysis.news_id == news_id))


def report_counts(session: Session, news_id: int, user_id: int | None) -> tuple[int, bool]:
    count = session.scalar(select(func.count()).select_from(NewsReport).where(NewsReport.news_id == news_id)) or 0
    mine = user_id is not None and session.scalar(
        select(NewsReport.id).where(NewsReport.news_id == news_id, NewsReport.user_id == user_id)
    ) is not None
    return int(count), mine


def add_report(session: Session, news_id: int, user_id: int, reason: str) -> None:
    session.execute(
        pg_insert(NewsReport)
        .values(news_id=news_id, user_id=user_id, reason=reason)
        .on_conflict_do_nothing(constraint="unique_news_report")
    )


def clear_reports(session: Session, news_id: int) -> None:
    session.execute(delete(NewsReport).where(NewsReport.news_id == news_id))
