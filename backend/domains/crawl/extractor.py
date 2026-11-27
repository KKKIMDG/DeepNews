"""Text processing for article bodies the browser sends. The server never fetches article pages:
Naver forbids automated collection, and fetching user-supplied URLs would expose the shared server (SSRF)."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import parse_qs, urlparse


def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


# Publisher footers the extractor sometimes picks up. A masthead is recognised by several
# registration fields close together; on a title-only page (e.g. a [속보]) it is all that is left.
MASTHEAD_FIELD = re.compile(
    r"인터넷신문\s?등록번호|사업자\s?등록번호|등록일자|발행일자|발행인|편집인|청소년\s?보호\s?책임자|All Rights Reserved",
    re.IGNORECASE,
)
MASTHEAD_SPAN = 400
# Copyright, collection and reader-tip lines; only cut when they sit near the end of the body.
TRAILING_NOTICE = re.compile(
    r"GoodNews paper|당신의 제보가 뉴스가 됩니다|Copyright\s?(?:[ⓒ©]|\(c\)|\d{4}|.{0,60}?All Rights Reserved)"
    r"|저작권자\s?[ⓒ©(]|무단\s?전재\s?(?:및|,|·)|AI\s?학습\s?(?:및\s?활용\s?|이용\s?)*금지",
    re.IGNORECASE,
)
TRAILING_WINDOW = 400


def strip_publisher_footer(text: str) -> str:
    fields = list(MASTHEAD_FIELD.finditer(text))
    for index, first in enumerate(fields):
        nearby = {
            re.sub(r"\s", "", match.group(0)).lower()
            for match in fields[index:]
            if match.start() - first.start() <= MASTHEAD_SPAN
        }
        if len(nearby) >= 3:
            title = text.rfind("제호", max(0, first.start() - 150), first.start())
            text = text[: title if title >= 0 else first.start()]
            break
    notice = TRAILING_NOTICE.search(text, max(0, len(text) - TRAILING_WINDOW))
    return text[: notice.start()] if notice else text


def clean_article_text(text: str) -> str:
    cleaned = strip_publisher_footer(normalize_text(text))
    patterns = [
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " "),
        (r"\b[가-힣]{2,5}\s?(기자|특파원|인턴기자|객원기자|논설위원|위원|앵커)\b", " "),
        (
            r"\b[가-힣]{2,5}\s?(?:기자|특파원)\s*=\s*[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            " ",
        ),
        (r"(무단전재|재배포\s*금지|저작권자\s*[^.]{0,50})", " "),
        (r"\[[^\]]+\]", " "),
        (r"\([^)]+\)", ""),  # "에쓰오일(S-OIL)은" -> "에쓰오일은", not "에쓰오일 은"
        (r"<[^>]+>", " "),
        (r"[▶△▲▷◇◆■□★☆☎☞◎※●○=]+", " "),
        # Keep what changes meaning or readability: 11.8%, 5·18, quotes, ranges, 李·與 and similar.
        (r"[^0-9A-Za-z가-힣一-鿿\s.,!?%·'\"‘’“”~\-/:…]", " "),
        (r"\s{2,}", " "),
    ]

    for pattern, replacement in patterns:
        cleaned = re.sub(pattern, replacement, cleaned)
    return cleaned.strip()


@lru_cache(maxsize=1)
def get_analyzer():
    """Kiwi (no JVM; keeps 소비자물가·상승률·김영익 whole, where Okt split them into 상+승률 or misread 보이다 as a noun).
    A plain regex where kiwipiepy is not installed."""
    try:
        from kiwipiepy import Kiwi

        return KiwiAnalyzer(Kiwi()), "Kiwi"
    except Exception:
        return RegexAnalyzer(), "Regex"


def extract_token_counts(text: str, analyzer) -> dict[str, int]:
    nouns = analyzer.nouns(text)
    filtered = [noun.strip() for noun in nouns if len(noun.strip()) >= 2]
    counts = Counter(filtered)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


class KiwiAnalyzer:
    # NNG/NNP nouns and SL Latin letters (AI반도체) chain; XSN noun suffixes (률·류·화) attach to the noun before them,
    # except the plural 들 (전문가들) and the adjectival 적 (본격적), which would make a new word of every noun.
    CHAIN_TAGS = frozenset({"NNG", "NNP", "SL"})
    LOOSE_SUFFIXES = frozenset({"들", "적"})
    NOUN_TAGS = frozenset({"NNG", "NNP"})

    def __init__(self, kiwi):
        self.kiwi = kiwi

    def nouns(self, text: str) -> list[str]:
        """Noun phrases: nouns written without a space between them form one term (소비자+물가 → 소비자물가).

        Numbers break a phrase, so every term appears verbatim in the text and can be highlighted there.
        """
        terms: list[str] = []
        run: list = []
        end = -1
        for token in self.kiwi.tokenize(text or ""):
            if run and token.start == end and (token.tag in self.CHAIN_TAGS or (token.tag == "XSN" and token.form not in self.LOOSE_SUFFIXES)):
                run.append(token)
            else:
                self._flush(run, terms)
                run = [token] if token.tag in self.CHAIN_TAGS else []
            end = token.start + token.len
        self._flush(run, terms)
        return terms

    def _flush(self, run: list, terms: list[str]) -> None:
        if any(token.tag in self.NOUN_TAGS for token in run):
            terms.append("".join(token.form for token in run))


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
