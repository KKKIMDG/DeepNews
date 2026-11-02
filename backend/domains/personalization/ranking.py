"""Keyword-based recommendation scoring. Pure functions only, so it is testable without a DB.

score = article similarity (TF-IDF cosine to the current article)
      + profile similarity (cosine to the user's decayed reading profile)
      + manual interest-keyword bonus + interest-topic bonus + freshness bonus

Interest topics (picked at sign-up or later) fix the cold start: their representative terms seed the
profile and same-category articles get a bonus, both scaled by topic_strength, which fades as reads pile up.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

ARTICLE_WEIGHT = 0.6
PROFILE_WEIGHT = 0.4
INCLUDE_BONUS_PER_WORD = 0.1
INCLUDE_BONUS_MAX = 0.3
FRESHNESS_BONUS = 0.1
FRESHNESS_HALF_LIFE_DAYS = 7.0
PROFILE_HALF_LIFE_DAYS = 14.0
NEAR_DUPLICATE_SIMILARITY = 0.9
# Outlets extract different keywords for one story, so titles catch what keyword cosine misses.
# On the 2026-10 DB, every one of the 17 (of 7,497) pairs at title-bigram Jaccard >= 0.25 was a same-story rewrite.
NEAR_DUPLICATE_TITLE_JACCARD = 0.25
TITLE_NOISE = re.compile(r"\[[^\]]*\]|\([^)]*\)")
TITLE_NON_WORD = re.compile(r"[^0-9A-Za-z가-힣]")

# Regex-analyzer fallbacks store tokens like '안경을' or '있다'. Only particles that almost never end
# a real noun are stripped, and only when 2+ characters remain ('마을', '평가', '회의' stay intact).
SAFE_PARTICLE_SUFFIX = re.compile(r"^(.{2,}?)(으로|에서|에게|께서|까지|부터|을|를)$")
NOUNS_ENDING_IN_EUL = ("마을", "가을", "노을")
# Verb/adjective endings only, so nouns like 캐나다, 플로리다, 최다 survive.
PREDICATE_SUFFIX = re.compile(r"(했|한|된|됐|있|없|겠|였|었|았|졌|렸|냈|는|합니|입니|습니)다$")
# BigKinds top-level categories (extraData.category is "경제>증권_증시"); keys are what the DB stores.
TOPIC_LABELS = {
    "정치": "정치",
    "경제": "경제",
    "사회": "사회",
    "국제": "국제",
    "IT_과학": "IT·과학",
    "문화": "문화·연예",
    "스포츠": "스포츠",
    "지역": "지역",
}
# Reading history outweighs sign-up topics after ~COLD_START_READS reads; the floor keeps later
# topic edits visible for heavy readers too.
COLD_START_READS = 10.0
TOPIC_STRENGTH_FLOOR = 0.3
# Topic terms stay well below manual interests (1.0): on the 2026-11 DB, 0.6 buried a user's own keyword
# under topic articles, while 0.35 interleaves the two.
TOPIC_PROFILE_SCALE = 0.35
TOPIC_BONUS = 0.15
TOPIC_TERMS_PER_TOPIC = 25
# Subtracted per article already picked from the same category, so a newly added topic shows up in the feed.
CATEGORY_REPEAT_PENALTY = 0.06
TOPIC_MIN_ARTICLES = 3

GENERIC_TERMS = frozenset({
    "것으로", "것이", "것을", "것은", "우리", "당시", "경우", "이번", "관련", "통해", "대한", "위한",
    "지난", "이날", "정도", "이후", "현재", "기준", "가장", "매우",
})


@dataclass(frozen=True)
class Candidate:
    news_id: int
    title: str
    url: str
    created_at: datetime
    ad_probability: float | None
    keywords: dict[str, int]
    category: str = ""


@dataclass(frozen=True)
class HistoryEntry:
    keywords: dict[str, int]
    read_count: int
    last_read_at: datetime


@dataclass
class RankedArticle:
    candidate: Candidate
    score: float
    reasons: list[str] = field(default_factory=list)


def idf(article_count: int, total_articles: int) -> float:
    return math.log((total_articles + 1) / (article_count + 1)) + 1.0


def tfidf(keyword_counts: dict[str, int], idf_map: dict[str, float]) -> dict[str, float]:
    return {
        word: (1.0 + math.log(count)) * idf_map.get(word, 1.0)
        for word, count in keyword_counts.items()
        if count > 0
    }


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    dot = sum(value * right.get(word, 0.0) for word, value in left.items())
    if dot == 0.0:
        return 0.0
    norm = math.sqrt(sum(v * v for v in left.values())) * math.sqrt(sum(v * v for v in right.values()))
    return dot / norm


def normalize_term(word: str) -> str | None:
    term = word.strip()
    match = SAFE_PARTICLE_SUFFIX.match(term)
    if match and not term.endswith(NOUNS_ENDING_IN_EUL):
        term = match.group(1)
    if len(term) < 2 or term in GENERIC_TERMS or PREDICATE_SUFFIX.search(term):
        return None
    return term


def normalize_keywords(keyword_counts: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = defaultdict(int)
    for word, count in keyword_counts.items():
        term = normalize_term(word)
        if term:
            merged[term] += count
    return dict(merged)


def title_bigrams(title: str) -> set[str]:
    # Drop tags like [단독] / (종합) and punctuation so outlet styling does not matter.
    text = TITLE_NON_WORD.sub("", TITLE_NOISE.sub(" ", title)).lower()
    return {text[index:index + 2] for index in range(len(text) - 1)}


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _age_days(moment: datetime, now: datetime) -> float:
    return max((now - moment).total_seconds() / 86400.0, 0.0)


def topic_strength(history_size: int) -> float:
    """1.0 for a new account, halved after COLD_START_READS reads, never below the floor."""
    return max(TOPIC_STRENGTH_FLOOR, 1.0 / (1.0 + max(history_size, 0) / COLD_START_READS))


def topic_terms(
    rows: list[tuple[str, str, int, int]],
    topic_sizes: dict[str, int],
    total_articles: int,
    limit: int = TOPIC_TERMS_PER_TOPIC,
) -> dict[str, dict[str, float]]:
    """Representative terms per topic, weights in [0, 1].

    rows: (topic, stored keyword, articles of the topic with it, articles overall with it).
    A term scores by how common it is inside the topic times log(lift over the whole corpus),
    so '경찰' wins for 사회 while '대통령', common everywhere, falls behind.
    """
    pooled: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for topic, word, topic_count, overall_count in rows:
        term = normalize_term(word)
        # Figures like '000원' or '3차' are report boilerplate, not interests.
        if term and not term[0].isdigit() and topic in TOPIC_LABELS:
            pooled[topic][term][0] += topic_count
            pooled[topic][term][1] += overall_count

    terms: dict[str, dict[str, float]] = {}
    for topic, counts in pooled.items():
        size = topic_sizes.get(topic, 0)
        if not size or not total_articles:
            continue
        scored = {}
        for term, (topic_count, overall_count) in counts.items():
            if topic_count < TOPIC_MIN_ARTICLES:
                continue
            share = topic_count / size
            lift = share / (max(overall_count, topic_count) / total_articles)
            if lift > 1.0:
                scored[term] = share * math.log(lift)
        top = sorted(scored.items(), key=lambda item: (-item[1], item[0]))[:limit]
        if top:
            peak = top[0][1]
            terms[topic] = {term: value / peak for term, value in top}
    return terms


def build_profile(
    history: list[HistoryEntry],
    idf_map: dict[str, float],
    include_words: set[str],
    exclude_words: set[str],
    now: datetime,
    topic_profile: dict[str, float] | None = None,
    strength: float = 0.0,
) -> dict[str, float]:
    """Interest weights in [0, 1]. Recent and repeated reads count more; manual interests pin to 1.

    topic_profile (merged topic_terms of the user's topics) is blended in at TOPIC_PROFILE_SCALE * strength.
    """
    raw: dict[str, float] = defaultdict(float)
    for entry in history:
        decay = 0.5 ** (_age_days(entry.last_read_at, now) / PROFILE_HALF_LIFE_DAYS)
        weight = decay * (1.0 + math.log(max(entry.read_count, 1)))
        for word, value in tfidf(entry.keywords, idf_map).items():
            raw[word] += weight * value

    peak = max(raw.values(), default=0.0)
    profile = {word: value / peak for word, value in raw.items()} if peak else {}
    for word, value in (topic_profile or {}).items():
        profile[word] = max(profile.get(word, 0.0), TOPIC_PROFILE_SCALE * strength * value)
    for word in include_words:
        profile[word] = 1.0
    for word in exclude_words:
        profile.pop(word, None)
    return profile


def _top_shared(left: dict[str, float], right: dict[str, float], limit: int) -> list[str]:
    shared = sorted(left.keys() & right.keys(), key=lambda word: (-left[word] * right[word], word))
    return shared[:limit]


def rank_candidates(
    candidates: list[Candidate],
    idf_map: dict[str, float],
    current_keywords: dict[str, int] | None,
    profile: dict[str, float],
    include_words: set[str],
    exclude_words: set[str],
    ad_filter_threshold: float,
    now: datetime,
    limit: int,
    seen_titles: tuple[str, ...] | list[str] = (),
    topics: set[str] | frozenset[str] = frozenset(),
    strength: float = 0.0,
) -> list[RankedArticle]:
    """seen_titles: the current and already-read articles; other outlets' takes on those stories are skipped.
    topics, strength: the user's interest topics and topic_strength(); same-category articles get a bonus."""
    current_vector = tfidf(current_keywords or {}, idf_map)
    cold_start = not current_vector and not profile
    seen_grams = [title_bigrams(title) for title in seen_titles]

    scored: list[tuple[RankedArticle, dict[str, float], set[str]]] = []
    for candidate in candidates:
        if exclude_words & candidate.keywords.keys():
            continue
        grams = title_bigrams(candidate.title)
        if any(jaccard(grams, seen) >= NEAR_DUPLICATE_TITLE_JACCARD for seen in seen_grams):
            continue
        if (
            ad_filter_threshold < 1.0
            and candidate.ad_probability is not None
            and candidate.ad_probability >= ad_filter_threshold
        ):
            continue

        vector = tfidf(candidate.keywords, idf_map)
        article_similarity = cosine(current_vector, vector)
        profile_similarity = cosine(profile, vector)
        if current_vector and profile:
            relevance = ARTICLE_WEIGHT * article_similarity + PROFILE_WEIGHT * profile_similarity
        else:
            relevance = article_similarity or profile_similarity

        matched_includes = sorted(include_words & candidate.keywords.keys())
        topic_match = candidate.category in topics
        if relevance == 0.0 and not matched_includes and not topic_match and not cold_start:
            continue

        age_days = _age_days(candidate.created_at, now)
        score = (
            relevance
            + min(INCLUDE_BONUS_PER_WORD * len(matched_includes), INCLUDE_BONUS_MAX)
            + (TOPIC_BONUS * strength if topic_match else 0.0)
            + FRESHNESS_BONUS * 0.5 ** (age_days / FRESHNESS_HALF_LIFE_DAYS)
        )

        shared_with_current = _top_shared(current_vector, vector, 2)
        mentioned = set(matched_includes) | set(shared_with_current)
        reasons = [f"관심 키워드 '{word}'" for word in matched_includes[:2]]
        reasons += [f"'{word}' 키워드 공통" for word in shared_with_current]
        if topic_match:
            reasons.append(f"관심 분야 '{TOPIC_LABELS[candidate.category]}'")
        reasons += [f"관심사 '{word}'" for word in _top_shared(profile, vector, 3) if word not in mentioned][:1]
        if age_days < 1.0:
            reasons.append("최신 기사")

        scored.append((RankedArticle(candidate, round(score, 4), reasons[:3]), vector, grams))

    scored.sort(key=lambda item: (-item[0].score, -item[0].candidate.news_id))

    # Greedy pick: skip near-duplicates (the same story from several outlets). In the feed (no current
    # article) a category is also discounted each time it is picked, so one topic cannot fill the list;
    # related articles stay ordered by relevance.
    penalty = 0.0 if current_vector else CATEGORY_REPEAT_PENALTY
    picked: list[tuple[RankedArticle, dict[str, float], set[str]]] = []
    category_counts: dict[str, int] = defaultdict(int)
    remaining = scored
    while remaining and len(picked) < limit:
        def adjusted(item: tuple[RankedArticle, dict[str, float], set[str]]) -> float:
            category = item[0].candidate.category
            return item[0].score - (penalty * category_counts[category] if category else 0.0)

        best = max(remaining, key=adjusted)  # max keeps the first of ties, i.e. the sort order
        remaining = [item for item in remaining if item is not best]
        ranked, vector, grams = best
        if any(
            cosine(vector, chosen_vector) >= NEAR_DUPLICATE_SIMILARITY
            or jaccard(grams, chosen_grams) >= NEAR_DUPLICATE_TITLE_JACCARD
            for _, chosen_vector, chosen_grams in picked
        ):
            continue
        picked.append(best)
        category_counts[ranked.candidate.category] += 1
    return [ranked for ranked, _, _ in picked]


def top_profile_terms(profile: dict[str, float], limit: int) -> list[tuple[str, float]]:
    return sorted(profile.items(), key=lambda item: (-item[1], item[0]))[:limit]
