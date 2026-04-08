from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import pandas as pd
import psycopg2
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from newspaper import Article, Config
from psycopg2.extras import Json


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

SEARCH_URL_TEMPLATE = (
    "https://search.naver.com/search.naver?"
    "where=news&sm=tab_pge&query={query}&start={start}"
)
NAVER_NEWS_DOMAINS = {"news.naver.com", "n.news.naver.com"}
SOURCE_NAME = "naver_news"


@dataclass
class ArticleRecord:
    title: str
    url: str
    original_content: str
    content: str
    published_at: str
    token_counts: dict[str, int]
    keywords: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Naver news, extract tokens, save locally, and upload to Postgres."
    )
    parser.add_argument("--query", default="AI", help="Naver news search query")
    parser.add_argument("--limit", type=int, default=50, help="Number of articles to collect")
    parser.add_argument("--output-dir", default="output", help="Directory for local output files")
    parser.add_argument(
        "--skip-db-upload",
        action="store_true",
        help="Collect and save locally without uploading to Postgres",
    )
    return parser.parse_args()


def build_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(DEFAULT_HEADERS)
    return session


def is_naver_news_link(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.lower() in NAVER_NEWS_DOMAINS


def collect_naver_news_links(
    query: str,
    limit: int,
    sleep_seconds: float = 0.4,
) -> list[str]:
    session = build_session()
    links: list[str] = []
    seen: set[str] = set()
    start = 1

    while len(links) < limit:
        url = SEARCH_URL_TEMPLATE.format(query=quote_plus(query), start=start)
        response = session.get(url, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        page_links = extract_naver_links_from_search_page(soup)
        if not page_links:
            break

        for link in page_links:
            if link in seen:
                continue
            seen.add(link)
            links.append(link)
            if len(links) >= limit:
                break

        start += 10
        time.sleep(sleep_seconds)

    return links[:limit]


def extract_naver_links_from_search_page(soup: BeautifulSoup) -> list[str]:
    candidates: list[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href.startswith("http"):
            continue
        if is_naver_news_link(href) and "/article/" in urlparse(href).path:
            candidates.append(href)

    deduped: list[str] = []
    seen: set[str] = set()
    for link in candidates:
        if link not in seen:
            seen.add(link)
            deduped.append(link)
    return deduped


def get_article_config() -> Config:
    config = Config()
    config.browser_user_agent = DEFAULT_HEADERS["User-Agent"]
    config.request_timeout = 20
    config.fetch_images = False
    config.memoize_articles = False
    config.language = "ko"
    config.proxies = {}
    return config


def extract_article(url: str, config: Config) -> tuple[str, str, str]:
    session = build_session()
    response = session.get(url, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    article = Article(url=url, language="ko", config=config)
    article.set_html(response.text)
    article.parse()

    title = (article.title or "").strip()
    original_content = normalize_text(article.text or "")
    published_at = format_publish_datetime(article.publish_date)

    if is_invalid_article_text(original_content):
        title, original_content, published_at = extract_from_naver_html(
            soup=soup,
            fallback_title=title,
            fallback_published_at=published_at,
        )

    return title, original_content, published_at


def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def is_invalid_article_text(text: str) -> bool:
    stripped = normalize_text(text)
    invalid_markers = (
        "기사 섹션 분류 안내",
        "이전 페이지",
        "다음 페이지",
    )
    return len(stripped) < 80 or any(marker in stripped for marker in invalid_markers)


def extract_from_naver_html(
    soup: BeautifulSoup,
    fallback_title: str,
    fallback_published_at: str,
) -> tuple[str, str, str]:
    title = fallback_title
    title_node = soup.select_one("#title_area") or soup.select_one("meta[property='og:title']")
    if title_node:
        if title_node.name == "meta":
            title = title_node.get("content", "").strip()
        else:
            title = title_node.get_text(" ", strip=True)

    body_text = ""
    body_node = soup.select_one("#dic_area")
    if body_node:
        body_copy = BeautifulSoup(str(body_node), "html.parser")
        for selector in [
            "script",
            "style",
            "em.img_desc",
            "span.end_photo_org",
            ".media_end_summary",
            ".byline_s",
        ]:
            for node in body_copy.select(selector):
                node.decompose()
        body_text = normalize_text(body_copy.get_text("\n", strip=True))

    published_at = fallback_published_at
    date_node = soup.select_one("span._ARTICLE_DATE_TIME")
    if date_node and date_node.get("data-date-time"):
        published_at = date_node["data-date-time"].strip()

    return title, body_text, published_at


def format_publish_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def clean_article_text(text: str) -> str:
    cleaned = normalize_text(text)
    patterns = [
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " "),
        (
            r"\b[가-힣]{2,5}\s?(기자|특파원|인턴기자|객원기자|논설위원|위원|앵커)\b",
            " ",
        ),
        (
            r"\b[가-힣]{2,5}\s?(?:기자|특파원)\s*=\s*[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            " ",
        ),
        (r"(무단전재|재배포\s*금지|저작권자\s*[^.]{0,50})", " "),
        (r"\[[^\]]+\]", " "),
        (r"\([^)]+\)", " "),
        (r"<[^>]+>", " "),
        (r"[▶△▲▷◇◆■□★☆☎☞◎※●○=]+", " "),
        (r"[^0-9A-Za-z가-힣\s.,!?]", " "),
        (r"\s{2,}", " "),
    ]
    for pattern, replacement in patterns:
        cleaned = re.sub(pattern, replacement, cleaned)
    return cleaned.strip()


def get_konlpy_analyzer():
    try:
        from konlpy.tag import Mecab

        return Mecab(), "Mecab"
    except Exception:
        from konlpy.tag import Okt

        return Okt(), "Okt"


def extract_token_counts(text: str, analyzer) -> dict[str, int]:
    nouns = analyzer.nouns(text)
    filtered = [noun.strip() for noun in nouns if len(noun.strip()) >= 2]
    counts = Counter(filtered)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def build_records(urls: list[str]) -> tuple[list[ArticleRecord], list[dict[str, str]], str]:
    config = get_article_config()
    analyzer, analyzer_name = get_konlpy_analyzer()
    print(f"[INFO] Analyzer: {analyzer_name}")

    records: list[ArticleRecord] = []
    failures: list[dict[str, str]] = []

    for index, url in enumerate(urls, start=1):
        try:
            title, original_content, published_at = extract_article(url, config)
            if not original_content:
                raise ValueError("Empty article content")

            cleaned_content = clean_article_text(original_content)
            token_counts = extract_token_counts(cleaned_content, analyzer)
            if not token_counts:
                raise ValueError("No noun tokens extracted")

            records.append(
                ArticleRecord(
                    title=title,
                    url=url,
                    original_content=original_content,
                    content=cleaned_content,
                    published_at=published_at,
                    token_counts=token_counts,
                    keywords=list(token_counts.keys()),
                )
            )
            print(f"[OK] {index}/{len(urls)} {title[:60]}")
        except Exception as exc:
            failures.append({"url": url, "reason": str(exc)})
            print(f"[FAIL] {index}/{len(urls)} {url} -> {exc}")

    return records, failures, analyzer_name


def build_payload(records: list[ArticleRecord], crawl_time: datetime) -> dict[str, Any]:
    return {
        "crawl_time": crawl_time.isoformat(timespec="seconds"),
        "source": SOURCE_NAME,
        "articles": [
            {
                "title": record.title,
                "url": record.url,
                "content": record.content,
                "published_at": to_iso_datetime(record.published_at),
                "token_counts": record.token_counts,
                "keywords": record.keywords,
            }
            for record in records
        ],
    }


def records_to_dataframe(records: list[ArticleRecord], crawl_time: datetime) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "crawl_time": crawl_time.isoformat(timespec="seconds"),
                "source": SOURCE_NAME,
                "title": record.title,
                "url": record.url,
                "content": record.content,
                "published_at": to_iso_datetime(record.published_at),
                "token_counts": json.dumps(record.token_counts, ensure_ascii=False),
                "keywords": json.dumps(record.keywords, ensure_ascii=False),
            }
            for record in records
        ]
    )


def to_iso_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").isoformat(timespec="seconds")
    except ValueError:
        return value


def save_outputs(
    payload: dict[str, Any],
    dataframe: pd.DataFrame,
    output_dir: Path,
    query: str,
    failures: list[dict[str, str]],
) -> tuple[Path, Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_query = re.sub(r"[^0-9A-Za-z가-힣]+", "_", query).strip("_") or "query"

    json_path = output_dir / f"naver_news_{safe_query}_{timestamp}.json"
    csv_path = output_dir / f"naver_news_{safe_query}_{timestamp}.csv"
    failure_path = output_dir / f"naver_news_{safe_query}_{timestamp}_failures.json"

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    dataframe.to_csv(csv_path, index=False, encoding="utf-8-sig")

    saved_failure_path: Path | None = None
    if failures:
        failure_path.write_text(
            json.dumps(failures, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        saved_failure_path = failure_path

    return json_path, csv_path, saved_failure_path


def load_database_config() -> dict[str, str]:
    load_dotenv()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return {"dsn": database_url}

    required_keys = {
        "host": os.getenv("DB_HOST", "").strip(),
        "port": os.getenv("DB_PORT", "").strip(),
        "dbname": os.getenv("DB_NAME", "").strip(),
        "user": os.getenv("DB_USER", "").strip(),
        "password": os.getenv("DB_PASSWORD", "").strip(),
        "sslmode": os.getenv("DB_SSLMODE", "require").strip(),
    }
    missing = [key for key, value in required_keys.items() if not value]
    if missing:
        raise RuntimeError(f"Missing DB settings: {', '.join(missing)}")
    return required_keys


def get_db_connection():
    config = load_database_config()
    if "dsn" in config:
        return psycopg2.connect(config["dsn"])
    return psycopg2.connect(**config)


def ensure_tables_exist(connection) -> None:
    statements = [
        """
        create table if not exists news_article (
            article_id bigserial primary key,
            source text not null,
            crawl_time timestamptz not null,
            title text not null,
            url text not null unique,
            content text not null,
            original_content text,
            published_at timestamptz,
            token_counts jsonb not null default '{}'::jsonb,
            keywords jsonb not null default '[]'::jsonb,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        )
        """,
        """
        create table if not exists keyword (
            keyword_id bigserial primary key,
            word text not null unique,
            total_count integer not null default 0,
            article_count integer not null default 0,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        )
        """,
        """
        create table if not exists article_keyword (
            article_id bigint not null references news_article(article_id) on delete cascade,
            keyword_id bigint not null references keyword(keyword_id) on delete cascade,
            count integer not null,
            created_at timestamptz not null default now(),
            primary key (article_id, keyword_id)
        )
        """,
    ]
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    connection.commit()


def upsert_articles_to_db(
    connection,
    records: list[ArticleRecord],
    crawl_time: datetime,
) -> None:
    touched_words: set[str] = set()

    with connection.cursor() as cursor:
        for record in records:
            article_id = upsert_article(cursor, record, crawl_time)
            cursor.execute(
                "delete from article_keyword where article_id = %s",
                (article_id,),
            )

            for word, count in record.token_counts.items():
                keyword_id = get_or_create_keyword(cursor, word)
                cursor.execute(
                    """
                    insert into article_keyword (article_id, keyword_id, count)
                    values (%s, %s, %s)
                    on conflict (article_id, keyword_id)
                    do update set count = excluded.count
                    """,
                    (article_id, keyword_id, count),
                )
                touched_words.add(word)

        refresh_keyword_stats(cursor, touched_words)

    connection.commit()


def upsert_article(cursor, record: ArticleRecord, crawl_time: datetime) -> int:
    published_at = None
    if record.published_at:
        published_at = datetime.strptime(record.published_at, "%Y-%m-%d %H:%M:%S")

    cursor.execute(
        """
        insert into news_article (
            source,
            crawl_time,
            title,
            url,
            content,
            original_content,
            published_at,
            token_counts,
            keywords,
            updated_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        on conflict (url)
        do update set
            source = excluded.source,
            crawl_time = excluded.crawl_time,
            title = excluded.title,
            content = excluded.content,
            original_content = excluded.original_content,
            published_at = excluded.published_at,
            token_counts = excluded.token_counts,
            keywords = excluded.keywords,
            updated_at = now()
        returning article_id
        """,
        (
            SOURCE_NAME,
            crawl_time,
            record.title,
            record.url,
            record.content,
            record.original_content,
            published_at,
            Json(record.token_counts),
            Json(record.keywords),
        ),
    )
    return cursor.fetchone()[0]


def get_or_create_keyword(cursor, word: str) -> int:
    cursor.execute(
        """
        insert into keyword (word)
        values (%s)
        on conflict (word) do update set updated_at = now()
        returning keyword_id
        """,
        (word,),
    )
    return cursor.fetchone()[0]


def refresh_keyword_stats(cursor, words: set[str]) -> None:
    if not words:
        return

    cursor.execute(
        """
        with stats as (
            select
                k.keyword_id,
                coalesce(sum(ak.count), 0)::integer as total_count,
                count(ak.article_id)::integer as article_count
            from keyword k
            left join article_keyword ak on ak.keyword_id = k.keyword_id
            where k.word = any(%s)
            group by k.keyword_id
        )
        update keyword k
        set
            total_count = stats.total_count,
            article_count = stats.article_count,
            updated_at = now()
        from stats
        where k.keyword_id = stats.keyword_id
        """,
        (list(words),),
    )


def main() -> None:
    for proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(proxy_key, None)

    args = parse_args()
    output_dir = Path(args.output_dir)
    crawl_time = datetime.now()

    print(f"[INFO] Query: {args.query}")
    urls = collect_naver_news_links(query=args.query, limit=args.limit)
    print(f"[INFO] Collected links: {len(urls)}")
    if not urls:
        raise RuntimeError("No Naver news links collected.")

    records, failures, analyzer_name = build_records(urls)
    payload = build_payload(records, crawl_time)
    dataframe = records_to_dataframe(records, crawl_time)
    json_path, csv_path, failure_path = save_outputs(
        payload=payload,
        dataframe=dataframe,
        output_dir=output_dir,
        query=args.query,
        failures=failures,
    )

    print(f"[DONE] JSON saved: {json_path}")
    print(f"[DONE] CSV saved: {csv_path}")
    print(f"[INFO] Analyzer used: {analyzer_name}")
    if failure_path:
        print(f"[WARN] Failures saved: {failure_path}")

    if args.skip_db_upload:
        print("[INFO] DB upload skipped by flag.")
        return

    with get_db_connection() as connection:
        ensure_tables_exist(connection)
        upsert_articles_to_db(connection, records, crawl_time)
    print("[DONE] Database upload completed.")


if __name__ == "__main__":
    main()
