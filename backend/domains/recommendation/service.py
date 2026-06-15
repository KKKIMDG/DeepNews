from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...database import get_session

INTERACTION_WEIGHTS = {
    "VIEW": 1,
    "CLICK": 3,
    "BOOKMARK": 5,
    "DISMISS": 0,
}


def normalize_interaction_type(value: str | None) -> str:
    normalized = (value or "VIEW").strip().upper()
    return normalized if normalized in INTERACTION_WEIGHTS else "VIEW"


def record_interaction(
    client_user_id: str,
    news_id: int | None = None,
    url: str | None = None,
    interaction_type: str | None = "VIEW",
    session: Session | None = None,
) -> bool:
    if not client_user_id or (news_id is None and not url):
        return False

    if session is None:
        with get_session() as managed_session:
            return record_interaction(
                client_user_id=client_user_id,
                news_id=news_id,
                url=url,
                interaction_type=interaction_type,
                session=managed_session,
            )

    resolved_news_id = news_id
    if resolved_news_id is None and url:
        row = session.execute(
            text("select id from news where url = :url"),
            {"url": url},
        ).mappings().first()
        if row:
            resolved_news_id = int(row["id"])

    if resolved_news_id is None:
        return False

    normalized_type = normalize_interaction_type(interaction_type)
    weight = INTERACTION_WEIGHTS[normalized_type]
    session.execute(
        text(
            """
            insert into news_interaction (client_user_id, news_id, interaction_type, weight)
            values (:client_user_id, :news_id, :interaction_type, :weight)
            on conflict (client_user_id, news_id, interaction_type)
            do update set
                weight = greatest(news_interaction.weight, excluded.weight),
                updated_at = now()
            """
        ),
        {
            "client_user_id": client_user_id,
            "news_id": resolved_news_id,
            "interaction_type": normalized_type,
            "weight": weight,
        },
    )
    return True


def recommend_for_article(
    current_news_id: int | None = None,
    client_user_id: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(int(limit or 5), 20))
    recommendations: dict[int, dict[str, Any]] = {}

    with get_session() as session:
        if client_user_id:
            _add_rows(
                recommendations,
                _find_user_cf(session, client_user_id, normalized_limit),
                "MIND-style collaborative filtering: similar readers",
                "USER_CF",
            )

        if len(recommendations) < normalized_limit and current_news_id is not None:
            _add_rows(
                recommendations,
                _find_article_cf(session, current_news_id, client_user_id, normalized_limit * 2),
                "Readers also viewed",
                "ITEM_CF",
            )

        if len(recommendations) < normalized_limit and current_news_id is not None:
            _add_rows(
                recommendations,
                _find_keyword_fallback(session, current_news_id, client_user_id, normalized_limit * 2),
                "Keyword similarity fallback",
                "KEYWORD_FALLBACK",
            )

        if len(recommendations) < normalized_limit:
            _add_rows(
                recommendations,
                _find_latest_fallback(session, current_news_id, normalized_limit * 2),
                "Latest news fallback",
                "LATEST_FALLBACK",
            )

    return list(recommendations.values())[:normalized_limit]


def _add_rows(
    recommendations: dict[int, dict[str, Any]],
    rows: list[dict[str, Any]],
    reason: str,
    source: str,
) -> None:
    for row in rows:
        news_id = int(row["news_id"])
        if news_id in recommendations:
            continue
        recommendations[news_id] = {
            "newsId": news_id,
            "title": str(row["title"]),
            "url": str(row["url"]),
            "score": float(row.get("score") or 0.0),
            "reason": reason,
            "source": source,
        }


def _find_user_cf(session: Session, client_user_id: str, limit: int) -> list[dict[str, Any]]:
    return list(
        session.execute(
            text(
                """
                select
                    n.id as news_id,
                    n.title,
                    n.url,
                    coalesce(sum(my.weight * neighbor_match.weight * candidate.weight), 0) as score
                from news_interaction my
                join news_interaction neighbor_match
                    on neighbor_match.news_id = my.news_id
                    and neighbor_match.client_user_id <> my.client_user_id
                join news_interaction candidate
                    on candidate.client_user_id = neighbor_match.client_user_id
                    and candidate.news_id <> my.news_id
                join news n on n.id = candidate.news_id
                where my.client_user_id = :client_user_id
                    and my.weight > 0
                    and neighbor_match.weight > 0
                    and candidate.weight > 0
                    and not exists (
                        select 1
                        from news_interaction seen
                        where seen.client_user_id = :client_user_id
                            and seen.news_id = n.id
                    )
                group by n.id, n.title, n.url
                order by score desc, max(candidate.updated_at) desc nulls last, n.id desc
                limit :limit
                """
            ),
            {"client_user_id": client_user_id, "limit": limit},
        ).mappings()
    )


def _find_article_cf(
    session: Session,
    current_news_id: int,
    client_user_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    return list(
        session.execute(
            text(
                """
                select
                    n.id as news_id,
                    n.title,
                    n.url,
                    coalesce(sum(i1.weight * i2.weight), 0) as score
                from news_interaction i1
                join news_interaction i2
                    on i2.client_user_id = i1.client_user_id
                    and i2.news_id <> :current_news_id
                join news n on n.id = i2.news_id
                where i1.news_id = :current_news_id
                    and i1.weight > 0
                    and i2.weight > 0
                    and (:client_user_id is null or i2.client_user_id <> :client_user_id)
                    and (
                        :client_user_id is null
                        or not exists (
                            select 1
                            from news_interaction seen
                            where seen.client_user_id = :client_user_id
                                and seen.news_id = n.id
                        )
                    )
                group by n.id, n.title, n.url
                order by score desc, max(i2.updated_at) desc nulls last, n.id desc
                limit :limit
                """
            ),
            {
                "current_news_id": current_news_id,
                "client_user_id": client_user_id,
                "limit": limit,
            },
        ).mappings()
    )


def _find_keyword_fallback(
    session: Session,
    current_news_id: int,
    client_user_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    return list(
        session.execute(
            text(
                """
                select
                    n.id as news_id,
                    n.title,
                    n.url,
                    sum(least(ak.count, target.count)) as score
                from article_keyword target
                join article_keyword ak
                    on ak.keyword_id = target.keyword_id
                    and ak.news_id <> :current_news_id
                join news n on n.id = ak.news_id
                where target.news_id = :current_news_id
                    and (
                        :client_user_id is null
                        or not exists (
                            select 1
                            from news_interaction seen
                            where seen.client_user_id = :client_user_id
                                and seen.news_id = n.id
                        )
                    )
                group by n.id, n.title, n.url
                order by score desc, n.id desc
                limit :limit
                """
            ),
            {
                "current_news_id": current_news_id,
                "client_user_id": client_user_id,
                "limit": limit,
            },
        ).mappings()
    )


def _find_latest_fallback(
    session: Session,
    current_news_id: int | None,
    limit: int,
) -> list[dict[str, Any]]:
    return list(
        session.execute(
            text(
                """
                select
                    id as news_id,
                    title,
                    url,
                    0.0 as score
                from news
                where (:current_news_id is null or id <> :current_news_id)
                order by created_at desc, id desc
                limit :limit
                """
            ),
            {"current_news_id": current_news_id, "limit": limit},
        ).mappings()
    )
