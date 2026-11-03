from __future__ import annotations

from sqlalchemy import Boolean, String, func, select
from sqlalchemy.orm import Session

from ..news.models import News

EXTRA = News.article_data["extraData"]
PUBLISHER = func.coalesce(EXTRA["publisher"].astext, "")
PUBLISHED_AT = News.article_data["publishedAt"].astext
# BigKinds rows still holding only the 200-character lead; analyzing one in the browser clears the flag.
IS_PARTIAL = func.coalesce(EXTRA["content_partial"].astext.cast(Boolean), False)


def publisher_counts(session: Session) -> list[tuple[str, int]]:
    count = func.count()
    rows = session.execute(
        select(PUBLISHER, count).where(IS_PARTIAL).group_by(PUBLISHER).order_by(count.desc(), PUBLISHER)
    ).all()
    return [(publisher, int(total)) for publisher, total in rows]


def candidates(session: Session, publisher: str, limit: int, offset: int) -> list[tuple]:
    statement = select(News.id, News.url, News.title, PUBLISHER, PUBLISHED_AT).where(IS_PARTIAL)
    if publisher:
        statement = statement.where(PUBLISHER == publisher)
    statement = statement.order_by(PUBLISHED_AT.desc().nulls_last(), News.id.desc()).limit(limit).offset(offset)
    return list(session.execute(statement).all())


def collected_by(session: Session, user_id: int) -> int:
    return int(session.scalar(
        select(func.count()).select_from(News).where(EXTRA["submitted_by"].astext == func.cast(user_id, String))
    ) or 0)
