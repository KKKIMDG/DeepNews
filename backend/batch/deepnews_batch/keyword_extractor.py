from __future__ import annotations

import json
import re
import sys
from collections import Counter
from typing import Any


KEYWORD_LIMIT = 12
MIN_TOKEN_LENGTH = 2
STOPWORDS = {
    "기자",
    "뉴스",
    "기사",
    "사진",
    "영상",
    "제공",
    "관련",
    "이번",
    "지난",
    "오늘",
    "내일",
    "오전",
    "오후",
    "무단",
    "전재",
    "재배포",
    "금지",
    "네이버",
    "본문",
    "내용",
    "결과",
    "통해",
    "대해",
    "위해",
    "대한",
    "있다",
    "했다",
    "한다",
    "되는",
    "됐다",
    "기반",
    "사용",
    "서비스",
    "것으로",
    "것은",
    "것이",
    "워드",
}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    raw_input = decode_stdin(sys.stdin.buffer.read())
    payload = json.loads(raw_input or "{}")
    title = str(payload.get("title") or "")
    content = str(payload.get("content") or "")

    token_counts = extract_keywords(title=title, content=content, limit=KEYWORD_LIMIT)
    print(json.dumps({"token_counts": token_counts, "keywords": list(token_counts.keys())}, ensure_ascii=False))


def decode_stdin(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_keywords(title: str, content: str, limit: int) -> dict[str, int]:
    analyzer = get_analyzer()
    scores: Counter[str] = Counter()

    add_scores(scores, title, analyzer=analyzer, weight=3)
    add_scores(scores, content, analyzer=analyzer, weight=1)

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return dict(ranked[:limit])


def get_analyzer() -> Any | None:
    try:
        from konlpy.tag import Mecab

        return Mecab()
    except Exception:
        try:
            from konlpy.tag import Okt

            return Okt()
        except Exception:
            return None


def add_scores(scores: Counter[str], text: str, analyzer: Any | None, weight: int) -> None:
    for token in extract_candidate_tokens(text, analyzer):
        normalized = normalize_token(token)
        if is_useful_token(normalized):
            scores[normalized] += weight

    for phrase in extract_compound_phrases(text):
        if is_useful_token(phrase):
            scores[phrase] += weight + 1


def extract_candidate_tokens(text: str, analyzer: Any | None) -> list[str]:
    cleaned = clean_text(text)
    if analyzer is None:
        return re.findall(r"[가-힣A-Za-z0-9]{2,}", cleaned)

    try:
        nouns = [token for token in analyzer.nouns(cleaned) if token]
        plain_tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", cleaned)
        return nouns + plain_tokens
    except Exception:
        return re.findall(r"[가-힣A-Za-z0-9]{2,}", cleaned)


def extract_compound_phrases(text: str) -> list[str]:
    cleaned = clean_text(text)
    words = [normalize_token(token) for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", cleaned)]
    words = [word for word in words if is_useful_token(word)]

    phrases: list[str] = []
    for index in range(len(words) - 1):
        left = words[index]
        right = words[index + 1]
        if len(left) + len(right) <= 14:
            phrases.append(f"{left} {right}")
    return phrases


def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"[^\w가-힣\s]", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def normalize_token(token: str) -> str:
    token = (token or "").strip().lower()
    suffixes = (
        "으로부터",
        "했습니다",
        "됩니다",
        "합니다",
        "입니다",
        "였다",
        "했다",
        "된다",
        "한다",
        "이다",
        "에게서",
        "에서는",
        "으로써",
        "로부터",
        "이라는",
        "라는",
        "에서",
        "에게",
        "까지",
        "부터",
        "으로",
        "라고",
        "하고",
        "보다",
        "처럼",
        "마다",
        "이며",
        "이고",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "의",
        "에",
        "와",
        "과",
        "도",
        "로",
        "만",
    )

    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if len(token) > len(suffix) + 1 and token.endswith(suffix):
                token = token[: -len(suffix)]
                changed = True
                break
    return token


def is_useful_token(token: str) -> bool:
    if len(token) < MIN_TOKEN_LENGTH or len(token) > 24:
        return False
    if token.isdigit():
        return False
    if token in STOPWORDS:
        return False
    return True


if __name__ == "__main__":
    main()
