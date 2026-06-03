from __future__ import annotations

import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from ...config import settings


DEFAULT_KEYWORDS = [
    "AI",
    "반도체",
    "경제",
    "정치",
    "사회",
    "IT",
    "과학",
    "주식",
    "전기차",
    "부동산",
    "건강",
    "취업",
    "창업",
    "기후",
    "세계",
]

NAVER_NEWS_API_URL = "https://openapi.naver.com/v1/search/news.json"
NAVER_NEWS_PATH = settings.recommendation_runtime_dir / "naver_news.json"


def clean_text(value: str | None) -> str:
    """Remove Naver highlight tags and normalize HTML entities."""
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def article_key(url: str, title: str, pub_date: str) -> str:
    """Create a stable demo identifier for a collected Naver article."""
    seed = url or f"{title}:{pub_date}"
    return "naver_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def publisher_from_url(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    return host.removeprefix("www.")


def normalize_item(item: dict, keyword: str) -> dict:
    link = item.get("link") or item.get("originallink") or ""
    originallink = item.get("originallink") or ""
    title = clean_text(item.get("title"))
    description = clean_text(item.get("description"))
    pub_date = item.get("pubDate") or ""
    return {
        "news_id": article_key(link or originallink, title, pub_date),
        "title": title,
        "description": description,
        "url": link or originallink,
        "originallink": originallink,
        "publisher": publisher_from_url(originallink or link),
        "pubDate": pub_date,
        "category": keyword,
        "collectedAt": datetime.now(timezone.utc).isoformat(),
    }


def load_collected_news(path: Path = NAVER_NEWS_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_collected_news(items: list[dict], path: Path = NAVER_NEWS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def search_news(query: str, display: int = 100, start: int = 1, sort: str = "date") -> list[dict]:
    """Call the official Naver News Search API."""
    if not settings.naver_client_id or not settings.naver_client_secret:
        raise RuntimeError("NAVER_CLIENT_ID and NAVER_CLIENT_SECRET are required.")

    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    params = {"query": query, "display": display, "start": start, "sort": sort}

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(NAVER_NEWS_API_URL, headers=headers, params=params, timeout=15)
            if response.status_code in {429, 500, 502, 503, 504}:
                time.sleep(1.5 * (attempt + 1))
                continue
            if not response.ok:
                raise RuntimeError(f"Naver API failed: {response.status_code} {response.text[:500]}")
            return response.json().get("items", [])
        except Exception as exception:
            last_error = exception
            time.sleep(1.0 * (attempt + 1))

    raise RuntimeError(f"Naver API request failed after retries: {last_error}")


def collect_naver_news(
    keywords: list[str] | None = None,
    per_keyword: int = 100,
    path: Path = NAVER_NEWS_PATH,
) -> dict:
    """Collect Naver news metadata for demo mapping."""
    keywords = keywords or DEFAULT_KEYWORDS
    existing = load_collected_news(path)
    by_url = {item["url"]: item for item in existing if item.get("url")}

    for keyword in keywords:
        raw_items = search_news(keyword, display=min(per_keyword, 100), start=1, sort="date")
        for raw_item in raw_items[:per_keyword]:
            item = normalize_item(raw_item, keyword)
            if item["url"] and item["url"] not in by_url:
                by_url[item["url"]] = item
        time.sleep(0.2)

    collected = list(by_url.values())
    save_collected_news(collected, path)
    return {
        "keywords": keywords,
        "requestedPerKeyword": per_keyword,
        "total": len(collected),
        "path": str(path),
    }
