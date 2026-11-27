"""Live pass-through of the NAVER news search API.

The search API terms (NAVER API 이용약관, 검색 API 특약 2.2-2.4) forbid storing or caching results beyond
short windows, feeding them to AI, and reordering or editing them. So results are fetched per request,
returned in NAVER's order, and never written to the DB, logged, or passed to the analysis models.
"""
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from typing import Callable

NAVER_NEWS_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
REQUEST_TIMEOUT_SECONDS = 5
_TAG = re.compile(r"<[^>]+>")


class NaverSearchUnavailable(Exception):
    """The API keys are missing or NAVER did not answer; the router turns this into 503."""


def plain_text(value: str) -> str:
    # NAVER marks matches with <b> and escapes quotes; only that markup is removed, the wording is kept.
    return html.unescape(_TAG.sub("", value or "")).strip()


def iso_pub_date(value: str) -> str:
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return ""


def http_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value or "")
    return value if parsed.scheme in {"http", "https"} and parsed.hostname else ""


def _is_naver_host(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    return host == "naver.com" or host.endswith(".naver.com")


def parse_items(payload: dict) -> list[dict]:
    items = []
    for item in payload.get("items") or []:
        link = http_url(item.get("link", ""))
        original = http_url(item.get("originallink", "")) or link
        if not original:
            continue
        items.append({
            "title": plain_text(item.get("title", "")),
            "description": plain_text(item.get("description", "")),
            "url": original,
            # The panel opens this one on NAVER pages so readers stay inside 네이버 뉴스.
            "naverUrl": link if _is_naver_host(link) else "",
            "source": urllib.parse.urlparse(original).hostname.removeprefix("www."),
            "publishedAt": iso_pub_date(item.get("pubDate", "")),
        })
    return items


def search_news(
    query: str,
    display: int,
    client_id: str,
    client_secret: str,
    sort: str = "sim",
    opener: Callable = urllib.request.urlopen,
) -> list[dict]:
    if not client_id or not client_secret:
        raise NaverSearchUnavailable("네이버 뉴스 검색이 서버에 설정되지 않았습니다.")

    params = urllib.parse.urlencode({"query": query, "display": display, "sort": sort})
    request = urllib.request.Request(
        f"{NAVER_NEWS_ENDPOINT}?{params}",
        headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
    )
    try:
        with opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise NaverSearchUnavailable(f"네이버 검색 API 오류 ({error.code})") from error
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise NaverSearchUnavailable("네이버 검색 API에 연결할 수 없습니다.") from error
    return parse_items(payload)
