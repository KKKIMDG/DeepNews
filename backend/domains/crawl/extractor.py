from __future__ import annotations

import os
import re
from collections import Counter
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from newspaper import Article, Config

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

NAVER_NEWS_DOMAINS = {"news.naver.com", "n.news.naver.com"}


def clear_proxy_env() -> None:
    for proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(proxy_key, None)


def build_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(DEFAULT_HEADERS)
    return session


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
    clear_proxy_env()
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
        title = (
            title_node.get("content", "").strip()
            if title_node.name == "meta"
            else title_node.get_text(" ", strip=True)
        )

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
        try:
            from konlpy.tag import Okt

            return Okt(), "Okt"
        except Exception:
            return RegexAnalyzer(), "Regex"


def extract_token_counts(text: str, analyzer) -> dict[str, int]:
    nouns = analyzer.nouns(text)
    filtered = [noun.strip() for noun in nouns if len(noun.strip()) >= 2]
    counts = Counter(filtered)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def to_iso_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").isoformat(timespec="seconds")
    except ValueError:
        return value


class RegexAnalyzer:
    def nouns(self, text: str) -> list[str]:
        return re.findall(r"[가-힣A-Za-z]{2,}", text or "")
