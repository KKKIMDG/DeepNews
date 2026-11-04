from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, TYPE_CHECKING

import psycopg2
from psycopg2.extras import Json, execute_values

from ..config import settings

if TYPE_CHECKING:
    from .bigkinds import BigKindsArticle


@contextmanager
def connect(database_url: str | None = None) -> Iterator["psycopg2.extensions.connection"]:
    """Commit on success, roll back on error, and always close.

    `with psycopg2.connect()` alone only ends the transaction; the connection would stay open.
    """
    connection = psycopg2.connect(database_url or settings.database_url)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def import_bigkinds_articles(
    articles: list["BigKindsArticle"], import_time: str, database_url: str | None = None
) -> int:
    """Insert new URLs only. Existing rows may hold full text from the extension and must not be
    overwritten by a 200-character BigKinds lead."""
    if not articles:
        return 0
    with connect(database_url) as connection:
        with connection.cursor() as cursor:
            inserted = execute_values(
                cursor,
                """
                insert into news (title, url, article_data)
                values %s
                on conflict (url) do nothing
                returning id, url
                """,
                [(article.title, article.url, Json(article.article_data(import_time))) for article in articles],
                template="(%s, %s, %s)",
                fetch=True,
            )
            url_to_news_id = {url: news_id for news_id, url in inserted}
            new_articles = [article for article in articles if article.url in url_to_news_id]

            words = sorted({word for article in new_articles for word in article.token_counts})
            upsert_keywords(cursor, words)
            keyword_map = get_keyword_ids(cursor, words)
            mapping_values = [
                (url_to_news_id[article.url], keyword_map[word], count)
                for article in new_articles
                for word, count in article.token_counts.items()
            ]
            if mapping_values:
                execute_values(
                    cursor,
                    """
                    insert into article_keyword (news_id, keyword_id, count)
                    values %s
                    on conflict (news_id, keyword_id) do update set count = excluded.count
                    """,
                    mapping_values,
                    template="(%s, %s, %s)",
                )
            refresh_keyword_stats(cursor, {keyword_id for _, keyword_id, _ in mapping_values})
            mark_collect_skips(cursor)
    return len(new_articles)


# Candidates the 수집 도우미 should not offer. Rows are only flagged (extraData.collect_skip), never
# deleted, so removing the key undoes it. Rows with full text or an analysis are left alone.
_SKIPPABLE = """
    coalesce((n.article_data->'extraData'->>'content_partial')::boolean, false)
    and not (coalesce(n.article_data->'extraData', '{}'::jsonb) ? 'collect_skip')
    and not exists (select 1 from news_analysis na where na.news_id = n.id)
"""


def mark_collect_skips(cursor) -> dict[str, int]:
    # Same publisher, same title (programme closings, notice boards, photo series): keep one, preferring
    # a row that already has full text, then the newest. Only punctuation is ignored: "①…"/"②…" parts
    # and "(10/26)"-dated issues are different articles.
    cursor.execute(
        f"""
        with titled as (
            select id, coalesce(article_data->'extraData'->>'publisher', '') as publisher,
                   regexp_replace(title, '[^0-9A-Za-z가-힣①-⑳]', '', 'g') as title_key,
                   coalesce((article_data->'extraData'->>'content_partial')::boolean, false) as partial,
                   article_data->>'publishedAt' as published_at
            from news
        ), ranked as (
            select id, first_value(id) over w as keep_id, row_number() over w as position
            from titled
            where length(title_key) >= 8
            window w as (partition by publisher, title_key
                         order by partial, published_at desc nulls last, id desc)
        )
        update news n
        set article_data = jsonb_set(
            n.article_data, '{{extraData}}',
            coalesce(n.article_data->'extraData', '{{}}'::jsonb)
                || jsonb_build_object('collect_skip', 'duplicate', 'duplicate_of', r.keep_id))
        from ranked r
        where r.id = n.id and r.position > 1 and {_SKIPPABLE}
        """
    )
    duplicates = cursor.rowcount
    # Breaking-news flashes and leads under 60 characters are usually title-only pages (422 on analysis).
    cursor.execute(
        f"""
        update news n
        set article_data = jsonb_set(
            n.article_data, '{{extraData}}',
            coalesce(n.article_data->'extraData', '{{}}'::jsonb) || '{{"collect_skip": "no_body"}}'::jsonb)
        where {_SKIPPABLE}
          and (n.title ~ '^\\s*\\[(속보|1보|2보)\\]' or length(coalesce(n.article_data->>'content', '')) < 60)
        """
    )
    return {"duplicate": duplicates, "no_body": cursor.rowcount}


def fetch_unanalyzed_news(database_url: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    # Rows analyzed while the models were missing hold placeholder results (ad_probability < 0)
    # and are queued again. Partial (BigKinds 200-character) content would yield meaningless
    # summaries and ad scores, so it is skipped. Random order keeps a permanently failing row
    # from occupying the head of the queue on every run.
    query = """
    select n.id, n.title, n.url, n.article_data
    from news n
    left join news_analysis na on na.news_id = n.id
    where (na.id is null or na.ad_probability < 0)
      and coalesce((n.article_data->'extraData'->>'content_partial')::boolean, false) = false
    order by random()
    limit %s
    """
    with connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()

    results: list[dict[str, Any]] = []
    for news_id, title, url, article_data in rows:
        payload = article_data or {}
        extra_data = payload.get("extraData") or {}
        results.append(
            {
                "news_id": news_id,
                "title": title,
                "url": url,
                "content": payload.get("content", ""),
                "published_at": payload.get("publishedAt", ""),
                "article_data": payload,
                "token_counts": extra_data.get("token_counts", {}),
            }
        )
    return results


def upsert_news_analysis_results(rows: list[dict[str, Any]], database_url: str | None = None) -> int:
    if not rows:
        return 0

    analyzed_at = datetime.now(timezone.utc)
    values = [
        (
            row["news_id"],
            row["summary"],
            round(float(row["ad_probability"]), 2),
            bool(row["is_clickbait"]),
            analyzed_at,
            Json(row.get("named_entities", [])),
        )
        for row in rows
    ]

    query = """
    insert into news_analysis (
        news_id,
        summary,
        ad_probability,
        is_clickbait,
        analyzed_at,
        named_entities
    ) values %s
    on conflict (news_id)
    do update set
        summary = excluded.summary,
        ad_probability = excluded.ad_probability,
        is_clickbait = excluded.is_clickbait,
        analyzed_at = excluded.analyzed_at,
        named_entities = excluded.named_entities
    """

    with connect(database_url) as connection:
        with connection.cursor() as cursor:
            execute_values(cursor, query, values, template="(%s, %s, %s, %s, %s, %s)")

    return len(rows)


def upsert_keywords(cursor, words: list[str]) -> None:
    if not words:
        return
    execute_values(
        cursor,
        """
        insert into keyword (word)
        values %s
        on conflict (word)
        do update set updated_at = now()
        """,
        [(word,) for word in words],
        template="(%s)",
    )


def get_keyword_ids(cursor, words: list[str]) -> dict[str, int]:
    if not words:
        return {}
    cursor.execute("select id, word from keyword where word = any(%s)", (words,))
    return {word: keyword_id for keyword_id, word in cursor.fetchall()}


def refresh_keyword_stats(cursor, keyword_ids: set[int]) -> None:
    if not keyword_ids:
        return

    cursor.execute(
        """
        with stats as (
            select
                k.id as keyword_id,
                coalesce(sum(ak.count), 0)::int as total_count,
                count(ak.news_id)::int as article_count
            from keyword k
            left join article_keyword ak on ak.keyword_id = k.id
            where k.id = any(%s)
            group by k.id
        )
        update keyword k
        set
            total_count = stats.total_count,
            article_count = stats.article_count,
            updated_at = now()
        from stats
        where k.id = stats.keyword_id
        """,
        (list(keyword_ids),),
    )
