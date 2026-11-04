from __future__ import annotations

from sqlalchemy import Boolean, String, and_, func, not_, select, text
from sqlalchemy.orm import Session

from ..news.models import News

EXTRA = News.article_data["extraData"]
PUBLISHER = func.coalesce(EXTRA["publisher"].astext, "")
PUBLISHED_AT = News.article_data["publishedAt"].astext
ORIGIN = func.coalesce(func.substring(News.url, r"^https?://[^/]+"), "")
# BigKinds rows still holding only the 200-character lead; analyzing one in the browser clears the flag.
IS_PARTIAL = func.coalesce(EXTRA["content_partial"].astext.cast(Boolean), False)
# Repeats and title-only flashes flagged at import (batch.storage.mark_collect_skips).
IS_CANDIDATE = and_(IS_PARTIAL, not_(func.coalesce(EXTRA, text("'{}'::jsonb")).has_key("collect_skip")))


# One row per (publisher, site): the collector asks for every site's permission in one prompt.
def candidate_sites(session: Session) -> list[tuple[str, str, int]]:
    count = func.count()
    rows = session.execute(
        select(PUBLISHER, ORIGIN, count).where(IS_CANDIDATE).group_by(PUBLISHER, ORIGIN).order_by(count.desc())
    ).all()
    return [(publisher, origin, int(total)) for publisher, origin, total in rows]


def candidates(session: Session, publisher: str, limit: int, offset: int) -> list[tuple]:
    statement = select(News.id, News.url, News.title, PUBLISHER, PUBLISHED_AT).where(IS_CANDIDATE)
    if publisher:
        statement = statement.where(PUBLISHER == publisher)
    statement = statement.order_by(PUBLISHED_AT.desc().nulls_last(), News.id.desc()).limit(limit).offset(offset)
    return list(session.execute(statement).all())


def collected_by(session: Session, user_id: int) -> int:
    return int(session.scalar(
        select(func.count()).select_from(News).where(EXTRA["submitted_by"].astext == func.cast(user_id, String))
    ) or 0)
