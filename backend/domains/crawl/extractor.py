"""Text processing for article bodies the browser sends. The server never fetches article pages:
Naver forbids automated collection, and fetching user-supplied URLs would expose the shared server (SSRF)."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse


def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


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


def normalize_published_at(value: str | None) -> str:
    """Browser-reported publish time (ISO-8601 or Naver's 'YYYY-MM-DD HH:MM:SS') → ISO string, or '' if unusable."""
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if not 1990 <= parsed.year <= datetime.now(timezone.utc).year + 1:
        return ""
    return parsed.isoformat(timespec="seconds")


class RegexAnalyzer:
    def nouns(self, text: str) -> list[str]:
        return re.findall(r"[가-힣A-Za-z]{2,}", text or "")


NAVER_CANONICAL_HOSTS = {"news.naver.com", "n.news.naver.com", "m.news.naver.com"}
NAVER_SECTION_HOSTS = {"m.sports.naver.com", "sports.naver.com", "m.entertain.naver.com", "entertain.naver.com"}


def canonical_article_url(url: str) -> str:
    """One stored URL per Naver article.

    The same story reaches the extension as /article/ or /mnews/article/, with ?sid= or other
    tracking parameters, or as an old read.naver?oid=&aid= link. Other sites are left untouched
    because their query strings can identify the article (e.g. KBS ?ncd=).
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host in NAVER_CANONICAL_HOSTS:
        match = re.fullmatch(r"/(?:mnews/)?article/(\d+)/(\d+)/?", parsed.path)
        query = parse_qs(parsed.query)
        ids = match.groups() if match else (query.get("oid", [""])[0], query.get("aid", [""])[0])
        if all(part.isdigit() for part in ids):
            return f"https://n.news.naver.com/mnews/article/{ids[0]}/{ids[1]}"
    if host in NAVER_SECTION_HOSTS and re.search(r"/article/\d+/\d+/?$", parsed.path):
        return f"https://{host}{parsed.path.rstrip('/')}"
    return url
