from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..auth.models import AppUser
from ..news.models import ArticleKeyword, Keyword, News, NewsAnalysis
from .models import UserInterestTopic, UserKeywordPreference, UserReadHistory
from .ranking import TOPIC_LABELS, Candidate, idf, normalize_keywords, normalize_term


KST = timezone(timedelta(hours=9))
# "경제>증권_증시" -> "경제"; browser-only articles have no category and match no topic.
TOP_CATEGORY = func.split_part(News.article_data["extraData"]["category"].astext, literal_column("'>'"), 1)


def _ad_probability(value: Any) -> float | None:
    # Placeholder analyses store -1; treat them as unknown rather than "not an ad".
    if value is None or float(value) < 0:
        return None
    return float(value)


def total_news_count(session: Session) -> int:
    return int(session.scalar(select(func.count(News.id))) or 0)


def keyword_counts_for_news(session: Session, news_ids: list[int]) -> dict[int, dict[str, int]]:
    if not news_ids:
        return {}
    rows = session.execute(
        select(ArticleKeyword.news_id, Keyword.word, ArticleKeyword.count)
        .join(Keyword, Keyword.id == ArticleKeyword.keyword_id)
        .where(ArticleKeyword.news_id.in_(news_ids))
    ).all()
    raw: dict[int, dict[str, int]] = defaultdict(dict)
    for news_id, word, count in rows:
        raw[news_id][word] = int(count)
    return {news_id: normalize_keywords(counts) for news_id, counts in raw.items()}


def _stored_variants(terms: set[str]) -> set[str]:
    # Stored keywords may still carry the particles normalize_term strips.
    return terms | {term + suffix for term in terms for suffix in ("을", "를", "으로", "에서")}


def idf_for_words(session: Session, words: set[str], total_articles: int) -> dict[str, float]:
    """IDF per normalized term; '안경' and '안경을' pool their article counts."""
    if not words:
        return {}
    rows = session.execute(
        select(Keyword.word, Keyword.article_count).where(Keyword.word.in_(_stored_variants(words)))
    ).all()
    pooled: dict[str, int] = defaultdict(int)
    for word, article_count in rows:
        term = normalize_term(word)
        if term in words:
            pooled[term] += int(article_count)
    found = {word: idf(min(count, total_articles), total_articles) for word, count in pooled.items()}
    # Words nobody has extracted yet (e.g. manual interests) are maximally specific.
    return {word: found.get(word, idf(0, total_articles)) for word in words}


def history_rows(session: Session, user_id: int, limit: int) -> list[tuple[int, int, datetime]]:
    rows = session.execute(
        select(UserReadHistory.news_id, UserReadHistory.read_count, UserReadHistory.last_read_at)
        .where(UserReadHistory.user_id == user_id)
        .order_by(UserReadHistory.last_read_at.desc())
        .limit(limit)
    ).all()
    return [(int(news_id), int(read_count), last_read_at) for news_id, read_count, last_read_at in rows]


def news_titles(session: Session, news_ids: list[int]) -> list[str]:
    if not news_ids:
        return []
    return list(session.scalars(select(News.title).where(News.id.in_(news_ids))))


def read_news_ids(session: Session, user_id: int) -> set[int]:
    return set(session.scalars(select(UserReadHistory.news_id).where(UserReadHistory.user_id == user_id)))


def history_count(session: Session, user_id: int) -> int:
    return int(session.scalar(select(func.count(UserReadHistory.id)).where(UserReadHistory.user_id == user_id)) or 0)


def preferences(session: Session, user_id: int) -> tuple[set[str], set[str]]:
    rows = session.execute(
        select(UserKeywordPreference.word, UserKeywordPreference.preference).where(
            UserKeywordPreference.user_id == user_id
        )
    ).all()
    include = {normalize_term(word) or word for word, preference in rows if preference == "include"}
    exclude = {normalize_term(word) or word for word, preference in rows if preference == "exclude"}
    return include, exclude


def candidate_news_ids(session: Session, seed_words: set[str], excluded_ids: set[int], limit: int) -> list[int]:
    if not seed_words:
        return []
    shared = func.count(ArticleKeyword.keyword_id)
    rows = session.execute(
        select(ArticleKeyword.news_id)
        .join(Keyword, Keyword.id == ArticleKeyword.keyword_id)
        .where(Keyword.word.in_(_stored_variants(seed_words)), ArticleKeyword.news_id.notin_(excluded_ids))
        .group_by(ArticleKeyword.news_id)
        .order_by(shared.desc(), ArticleKeyword.news_id.desc())
        .limit(limit)
    ).all()
    return [int(news_id) for (news_id,) in rows]


def recent_news_ids(session: Session, excluded_ids: set[int], limit: int) -> list[int]:
    return [
        int(news_id)
        for news_id in session.scalars(
            select(News.id).where(News.id.notin_(excluded_ids)).order_by(News.created_at.desc()).limit(limit)
        )
    ]


def _published_or_created(published_at: str | None, created_at: datetime) -> datetime:
    # Bulk imports share one created_at, so freshness must come from the article's own date.
    try:
        published = datetime.fromisoformat(published_at or "")
    except ValueError:
        return created_at
    return published if published.tzinfo else published.replace(tzinfo=KST)


def load_candidates(
    session: Session, news_ids: list[int], keyword_map: dict[int, dict[str, int]]
) -> list[Candidate]:
    if not news_ids:
        return []
    rows = session.execute(
        select(
            News.id,
            News.title,
            News.url,
            News.created_at,
            News.article_data["publishedAt"].astext,
            NewsAnalysis.ad_probability,
            TOP_CATEGORY,
        )
        .outerjoin(NewsAnalysis, NewsAnalysis.news_id == News.id)
        .where(News.id.in_(news_ids))
    ).all()
    return [
        Candidate(
            news_id=int(news_id),
            title=title,
            url=url,
            created_at=_published_or_created(published_at, created_at),
            ad_probability=_ad_probability(ad_probability),
            keywords=keyword_map.get(int(news_id), {}),
            category=category or "",
        )
        for news_id, title, url, created_at, published_at, ad_probability, category in rows
    ]


def record_read(session: Session, user_id: int, news_id: int) -> None:
    now = datetime.now(timezone.utc)
    statement = insert(UserReadHistory).values(
        user_id=user_id, news_id=news_id, read_count=1, first_read_at=now, last_read_at=now
    )
    session.execute(
        statement.on_conflict_do_update(
            constraint="unique_user_news",
            set_={
                "read_count": UserReadHistory.read_count + 1,
                "last_read_at": statement.excluded.last_read_at,
            },
        )
    )


def list_history(session: Session, user_id: int, limit: int, offset: int) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            News.id,
            News.title,
            News.url,
            UserReadHistory.read_count,
            UserReadHistory.last_read_at,
            NewsAnalysis.ad_probability,
        )
        .join(News, News.id == UserReadHistory.news_id)
        .outerjoin(NewsAnalysis, NewsAnalysis.news_id == News.id)
        .where(UserReadHistory.user_id == user_id)
        .order_by(UserReadHistory.last_read_at.desc(), News.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        {
            "newsId": int(news_id),
            "title": title,
            "url": url,
            "readCount": int(read_count),
            "lastReadAt": last_read_at,
            "adProbability": _ad_probability(ad_probability),
        }
        for news_id, title, url, read_count, last_read_at, ad_probability in rows
    ]


def delete_history(session: Session, user_id: int, news_id: int) -> bool:
    result = session.execute(
        delete(UserReadHistory).where(UserReadHistory.user_id == user_id, UserReadHistory.news_id == news_id)
    )
    return result.rowcount > 0


def upsert_preference(session: Session, user_id: int, word: str, preference: str) -> None:
    statement = insert(UserKeywordPreference).values(user_id=user_id, word=word, preference=preference)
    session.execute(
        statement.on_conflict_do_update(
            constraint="unique_user_keyword",
            set_={"preference": statement.excluded.preference},
        )
    )


def delete_preference(session: Session, user_id: int, word: str) -> bool:
    result = session.execute(
        delete(UserKeywordPreference).where(
            UserKeywordPreference.user_id == user_id, UserKeywordPreference.word == word
        )
    )
    return result.rowcount > 0


def update_ad_filter_threshold(session: Session, user_id: int, threshold: float) -> None:
    session.execute(update(AppUser).where(AppUser.id == user_id).values(ad_filter_threshold=threshold))


def topics(session: Session, user_id: int) -> set[str]:
    return set(session.scalars(select(UserInterestTopic.topic).where(UserInterestTopic.user_id == user_id)))


def replace_topics(session: Session, user_id: int, chosen: list[str]) -> None:
    session.execute(delete(UserInterestTopic).where(UserInterestTopic.user_id == user_id))
    if chosen:
        session.execute(insert(UserInterestTopic), [{"user_id": user_id, "topic": topic} for topic in chosen])


def topic_news_ids(session: Session, topic: str, excluded_ids: set[int], limit: int) -> list[int]:
    """Newest articles of one topic, by the article's own date (bulk imports share created_at)."""
    return [
        int(news_id)
        for news_id in session.scalars(
            select(News.id)
            .where(TOP_CATEGORY == topic, News.id.notin_(excluded_ids))
            .order_by(News.article_data["publishedAt"].astext.desc().nulls_last(), News.id.desc())
            .limit(limit)
        )
    ]


def topic_keyword_stats(session: Session) -> tuple[list[tuple[str, str, int, int]], dict[str, int], int]:
    """Inputs for ranking.topic_terms: (topic, word, topic article count, overall article count) rows,
    articles per topic, and the corpus size."""
    known = list(TOPIC_LABELS)
    rows = session.execute(
        select(TOP_CATEGORY, Keyword.word, func.count(), func.max(Keyword.article_count))
        .select_from(ArticleKeyword)
        .join(Keyword, Keyword.id == ArticleKeyword.keyword_id)
        .join(News, News.id == ArticleKeyword.news_id)
        .where(TOP_CATEGORY.in_(known))
        .group_by(TOP_CATEGORY, Keyword.word)
        .having(func.count() >= 3)
    ).all()
    sizes = session.execute(
        select(TOP_CATEGORY, func.count()).where(TOP_CATEGORY.in_(known)).group_by(TOP_CATEGORY)
    ).all()
    return (
        [(topic, word, int(count), int(overall or 0)) for topic, word, count, overall in rows],
        {topic: int(count) for topic, count in sizes},
        total_news_count(session),
    )
