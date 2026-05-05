from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING
from urllib.parse import quote_plus

import psycopg2
from psycopg2.extras import Json, execute_values

if TYPE_CHECKING:
    from .pipeline import BatchResult


def sync_news_batch_to_supabase(batch: "BatchResult", database_url: str | None = None) -> None:
    dsn = database_url or _database_url_from_env()
    with psycopg2.connect(dsn) as connection:
        with connection.cursor() as cursor:
            url_to_news_id = upsert_news_rows(cursor, batch)
            refresh_article_keyword_mappings(cursor, batch, url_to_news_id)
        connection.commit()


def fetch_unanalyzed_news(database_url: str, limit: int) -> list[dict[str, Any]]:
    query = """
    select n.id, n.title, n.url, n.article_data
    from news n
    left join news_analysis na on na.news_id = n.id
    where na.id is null
    order by n.created_at asc
    limit %s
    """
    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()

    results: list[dict[str, Any]] = []
    for news_id, title, url, article_data in rows:
        payload = article_data or {}
        results.append(
            {
                "news_id": news_id,
                "title": title,
                "url": url,
                "content": payload.get("content", ""),
                "published_at": payload.get("published_at", ""),
                "article_data": payload,
            }
        )
    return results


def upsert_news_analysis_results(database_url: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    values = [
        (
            row["news_id"],
            row["summary"],
            round(float(row["ad_probability"]), 2),
            bool(row["is_clickbait"]),
            datetime.utcnow(),
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

    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            execute_values(cursor, query, values, template="(%s, %s, %s, %s, %s, %s)")
        connection.commit()

    return len(rows)


def upsert_news_rows(cursor, batch: "BatchResult") -> dict[str, int]:
    values = [
        (
            article.title,
            article.url,
            Json(article.article_data(batch.crawl_time)),
        )
        for article in batch.articles
    ]

    query = """
    insert into news (title, url, article_data)
    values %s
    on conflict (url)
    do update set
        title = excluded.title,
        article_data = excluded.article_data
    """
    execute_values(cursor, query, values, template="(%s, %s, %s)")

    urls = [article.url for article in batch.articles]
    cursor.execute("select id, url from news where url = any(%s)", (urls,))
    return {url: news_id for news_id, url in cursor.fetchall()}


def refresh_article_keyword_mappings(cursor, batch: "BatchResult", url_to_news_id: dict[str, int]) -> None:
    news_ids = [url_to_news_id[article.url] for article in batch.articles if article.url in url_to_news_id]
    if not news_ids:
        return

    affected_keyword_ids = collect_existing_keyword_ids(cursor, news_ids)
    cursor.execute("delete from article_keyword where news_id = any(%s)", (news_ids,))

    unique_words = sorted(
        {
            word
            for article in batch.articles
            for word in article.token_counts.keys()
        }
    )
    upsert_keywords(cursor, unique_words)
    keyword_map = get_keyword_ids(cursor, unique_words)

    mapping_values = []
    for article in batch.articles:
        news_id = url_to_news_id[article.url]
        for word, count in article.token_counts.items():
            keyword_id = keyword_map[word]
            mapping_values.append((news_id, keyword_id, count))
            affected_keyword_ids.add(keyword_id)

    if mapping_values:
        execute_values(
            cursor,
            """
            insert into article_keyword (news_id, keyword_id, count)
            values %s
            on conflict (news_id, keyword_id)
            do update set count = excluded.count
            """,
            mapping_values,
            template="(%s, %s, %s)",
        )

    refresh_keyword_stats(cursor, affected_keyword_ids)


def collect_existing_keyword_ids(cursor, news_ids: list[int]) -> set[int]:
    cursor.execute("select keyword_id from article_keyword where news_id = any(%s)", (news_ids,))
    return {row[0] for row in cursor.fetchall()}


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


def _database_url_from_env() -> str:
    os_module = __import__("os")
    database_url = os_module.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return database_url

    host = os_module.environ.get("DB_HOST", "").strip()
    port = os_module.environ.get("DB_PORT", "").strip()
    name = os_module.environ.get("DB_NAME", "").strip()
    user = os_module.environ.get("DB_USER", "").strip()
    password = os_module.environ.get("DB_PASSWORD", "").strip()
    sslmode = os_module.environ.get("DB_SSLMODE", "require").strip()

    if not all([host, port, name, user, password]):
        raise RuntimeError("DATABASE_URL or DB_* environment variables are required for Supabase sync.")

    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{name}?sslmode={quote_plus(sslmode)}"
    )
