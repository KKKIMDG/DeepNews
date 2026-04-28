from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from newspaper import Article, Config

from .storage import sync_news_batch_to_supabase


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
SUMMARY_MAX_LENGTH = 280


@dataclass
class ArticleRecord:
    title: str
    url: str
    source: str
    original_content: str
    content: str
    published_at: str
    token_counts: dict[str, int]
    keywords: list[str]
    summary: str
    ad_probability: float = 0.0
    is_clickbait: bool = False
    named_entities: list[dict[str, Any]] = field(default_factory=list)

    def article_data(self, crawl_time: str) -> dict[str, Any]:
        return {
            "source": self.source,
            "content": self.content,
            "original_content": self.original_content,
            "published_at": to_iso_datetime(self.published_at),
            "crawl_time": crawl_time,
            "token_counts": self.token_counts,
            "keywords": self.keywords,
        }

    def payload_item(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "published_at": to_iso_datetime(self.published_at),
            "token_counts": self.token_counts,
            "keywords": self.keywords,
        }


@dataclass
class BatchResult:
    query: str
    crawl_time: str
    analyzer_name: str
    articles: list[ArticleRecord] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return {
            "crawl_time": self.crawl_time,
            "source": SOURCE_NAME,
            "articles": [article.payload_item() for article in self.articles],
        }

    def dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "crawl_time": self.crawl_time,
                    "source": SOURCE_NAME,
                    "title": article.title,
                    "url": article.url,
                    "content": article.content,
                    "published_at": to_iso_datetime(article.published_at),
                    "token_counts": json.dumps(article.token_counts, ensure_ascii=False),
                    "keywords": json.dumps(article.keywords, ensure_ascii=False),
                    "summary": article.summary,
                    "ad_probability": article.ad_probability,
                    "is_clickbait": article.is_clickbait,
                    "named_entities": json.dumps(article.named_entities, ensure_ascii=False),
                }
                for article in self.articles
            ]
        )

    def artifact(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "crawl_time": self.crawl_time,
            "analyzer_name": self.analyzer_name,
            "articles": [
                {
                    "title": article.title,
                    "url": article.url,
                    "source": article.source,
                    "original_content": article.original_content,
                    "content": article.content,
                    "published_at": article.published_at,
                    "token_counts": article.token_counts,
                    "keywords": article.keywords,
                    "summary": article.summary,
                    "ad_probability": article.ad_probability,
                    "is_clickbait": article.is_clickbait,
                    "named_entities": article.named_entities,
                }
                for article in self.articles
            ],
            "failures": self.failures,
        }

    @classmethod
    def from_artifact(cls, data: dict[str, Any]) -> "BatchResult":
        return cls(
            query=data["query"],
            crawl_time=data["crawl_time"],
            analyzer_name=data.get("analyzer_name", ""),
            articles=[
                ArticleRecord(
                    title=item["title"],
                    url=item["url"],
                    source=item.get("source", SOURCE_NAME),
                    original_content=item.get("original_content", ""),
                    content=item["content"],
                    published_at=item.get("published_at", ""),
                    token_counts=dict(item.get("token_counts", {})),
                    keywords=list(item.get("keywords", [])),
                    summary=item.get("summary", ""),
                    ad_probability=float(item.get("ad_probability", 0.0)),
                    is_clickbait=bool(item.get("is_clickbait", False)),
                    named_entities=list(item.get("named_entities", [])),
                )
                for item in data.get("articles", [])
            ],
            failures=list(data.get("failures", [])),
        )


def run_ingestion_pipeline(
    query: str,
    limit: int,
    output_dir: Path,
    skip_db_sync: bool = False,
    database_url: str | None = None,
) -> dict[str, Any]:
    batch = collect_news_batch(query=query, limit=limit)
    output_paths = save_batch_outputs(batch, output_dir)

    db_sync = False
    if not skip_db_sync:
        sync_news_batch_to_supabase(batch, database_url=database_url)
        db_sync = True

    return {
        "article_count": len(batch.articles),
        "json_path": str(output_paths["json_path"]),
        "csv_path": str(output_paths["csv_path"]),
        "failure_path": str(output_paths["failure_path"]) if output_paths["failure_path"] else None,
        "analyzer_name": batch.analyzer_name,
        "db_sync": db_sync,
    }


def collect_news_batch(query: str, limit: int) -> BatchResult:
    clear_proxy_env()
    crawl_time = datetime.now().isoformat(timespec="seconds")
    urls = collect_naver_news_links(query=query, limit=limit)
    if not urls:
        raise RuntimeError("No Naver news links collected.")

    articles, failures, analyzer_name = build_records(urls)
    return BatchResult(
        query=query,
        crawl_time=crawl_time,
        analyzer_name=analyzer_name,
        articles=articles,
        failures=failures,
    )


def save_batch_outputs(batch: BatchResult, output_dir: Path) -> dict[str, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_query = slugify_query(batch.query)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"naver_news_{safe_query}_{timestamp}.json"
    csv_path = output_dir / f"naver_news_{safe_query}_{timestamp}.csv"
    failure_path = output_dir / f"naver_news_{safe_query}_{timestamp}_failures.json"

    json_path.write_text(json.dumps(batch.payload(), ensure_ascii=False, indent=2), encoding="utf-8")
    batch.dataframe().to_csv(csv_path, index=False, encoding="utf-8-sig")

    saved_failure_path: Path | None = None
    if batch.failures:
        failure_path.write_text(json.dumps(batch.failures, ensure_ascii=False, indent=2), encoding="utf-8")
        saved_failure_path = failure_path

    return {
        "json_path": json_path,
        "csv_path": csv_path,
        "failure_path": saved_failure_path,
    }


def save_batch_artifact(batch: BatchResult, artifact_dir: Path) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / (
        f"naver_news_{slugify_query(batch.query)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.artifact.json"
    )
    artifact_path.write_text(json.dumps(batch.artifact(), ensure_ascii=False, indent=2), encoding="utf-8")
    return artifact_path


def load_batch_artifact(artifact_path: Path) -> BatchResult:
    return BatchResult.from_artifact(json.loads(artifact_path.read_text(encoding="utf-8")))


def clear_proxy_env() -> None:
    for proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(proxy_key, None)


def build_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(DEFAULT_HEADERS)
    return session


def collect_naver_news_links(query: str, limit: int, sleep_seconds: float = 0.4) -> list[str]:
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


def is_naver_news_link(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.lower() in NAVER_NEWS_DOMAINS


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

    title = normalize_text(article.title or "")
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
        title = title_node.get("content", "").strip() if title_node.name == "meta" else title_node.get_text(" ", strip=True)

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
        (r"\b[가-힣]{2,5}\s?(기자|특파원|인턴기자|객원기자|논설위원|위원|앵커)\b", " "),
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


def build_summary(text: str, max_length: int = SUMMARY_MAX_LENGTH) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def build_records(urls: list[str]) -> tuple[list[ArticleRecord], list[dict[str, str]], str]:
    config = get_article_config()
    analyzer, analyzer_name = get_konlpy_analyzer()

    articles: list[ArticleRecord] = []
    failures: list[dict[str, str]] = []

    for index, url in enumerate(urls, start=1):
        try:
            title, original_content, published_at = extract_article(url, config)
            if not original_content:
                raise ValueError("Empty article content")

            content = clean_article_text(original_content)
            token_counts = extract_token_counts(content, analyzer)
            if not token_counts:
                raise ValueError("No noun tokens extracted")

            articles.append(
                ArticleRecord(
                    title=title,
                    url=url,
                    source=SOURCE_NAME,
                    original_content=original_content,
                    content=content,
                    published_at=published_at,
                    token_counts=token_counts,
                    keywords=list(token_counts.keys()),
                    summary=build_summary(content),
                )
            )
            print(f"[OK] {index}/{len(urls)} {title[:60]}")
        except Exception as exc:
            failures.append({"url": url, "reason": str(exc)})
            print(f"[FAIL] {index}/{len(urls)} {url} -> {exc}")

    return articles, failures, analyzer_name


def slugify_query(query: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "_", query).strip("_") or "query"


def to_iso_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").isoformat(timespec="seconds")
    except ValueError:
        return value
