from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser
from ..auth.models import AppUser
from . import repository
from .ranking import (
    TOPIC_LABELS,
    HistoryEntry,
    build_profile,
    normalize_term,
    rank_candidates,
    top_profile_terms,
    topic_strength,
    topic_terms,
)
from .schemas import HistoryItemPayload, HistoryPayload, InterestPayload, ProfilePayload, RecommendationPayload

DEFAULT_AD_FILTER_THRESHOLD = 0.8
HISTORY_PROFILE_LIMIT = 200
PROFILE_SEED_TERMS = 15
CANDIDATE_LIMIT = 300
RECENT_FALLBACK_LIMIT = 50
PROFILE_INTEREST_LIMIT = 15
SEEN_STORY_LIMIT = 50
TOPIC_CANDIDATES_PER_TOPIC = 40
INITIAL_KEYWORD_LIMIT = 10
# Topic terms come from the whole corpus and shift only with large imports, so one query per process and TTL.
TOPIC_TERMS_TTL_SECONDS = 6 * 60 * 60
_topic_terms_lock = threading.Lock()
_topic_terms_cache: tuple[float, dict[str, dict[str, float]]] = (0.0, {})


def _topic_terms(session: Session) -> dict[str, dict[str, float]]:
    global _topic_terms_cache
    with _topic_terms_lock:
        loaded_at, cached = _topic_terms_cache
        if not cached or time.monotonic() - loaded_at > TOPIC_TERMS_TTL_SECONDS:
            cached = topic_terms(*repository.topic_keyword_stats(session))
            _topic_terms_cache = (time.monotonic(), cached)
        return cached


def _topic_profile(session: Session, chosen: set[str]) -> dict[str, float]:
    if not chosen:
        return {}
    merged: dict[str, float] = {}
    terms = _topic_terms(session)
    for topic in chosen:
        for word, weight in terms.get(topic, {}).items():
            merged[word] = max(merged.get(word, 0.0), weight)
    return merged


def _history_entries(session: Session, user_id: int) -> tuple[list[HistoryEntry], set[str], list[int]]:
    rows = repository.history_rows(session, user_id, HISTORY_PROFILE_LIMIT)
    news_ids = [news_id for news_id, _, _ in rows]
    keyword_map = repository.keyword_counts_for_news(session, news_ids)
    entries = [
        HistoryEntry(keywords=keyword_map.get(news_id, {}), read_count=read_count, last_read_at=last_read_at)
        for news_id, read_count, last_read_at in rows
    ]
    words = {word for entry in entries for word in entry.keywords}
    return entries, words, news_ids


def recommend(
    session: Session,
    user: CurrentUser | None,
    current_news_id: int | None = None,
    limit: int = 5,
) -> list[RecommendationPayload]:
    now = datetime.now(timezone.utc)
    total = repository.total_news_count(session)

    current_keywords: dict[str, int] = {}
    if current_news_id is not None:
        current_keywords = repository.keyword_counts_for_news(session, [current_news_id]).get(current_news_id, {})

    include, exclude, history, history_words, read_ids, chosen = set(), set(), [], set(), set(), set()
    recent_read_ids: list[int] = []
    if user is not None:
        include, exclude = repository.preferences(session, user.id)
        history, history_words, recent_read_ids = _history_entries(session, user.id)
        read_ids = repository.read_news_ids(session, user.id)
        chosen = repository.topics(session, user.id)
    seen_ids = recent_read_ids[:SEEN_STORY_LIMIT] + ([current_news_id] if current_news_id is not None else [])

    strength = topic_strength(len(history))
    topic_profile = _topic_profile(session, chosen)
    idf_map = repository.idf_for_words(
        session, set(current_keywords) | history_words | include | topic_profile.keys(), total
    )
    profile = build_profile(history, idf_map, include, exclude, now, topic_profile, strength)

    excluded_ids = read_ids | ({current_news_id} if current_news_id is not None else set())
    seeds = set(current_keywords) | {word for word, _ in top_profile_terms(profile, PROFILE_SEED_TERMS)}
    candidate_ids = repository.candidate_news_ids(session, seeds - exclude, excluded_ids, CANDIDATE_LIMIT)
    # Category matches reach articles whose keywords never overlap the seeds (e.g. a new account's feed).
    for topic in sorted(chosen):
        candidate_ids += repository.topic_news_ids(
            session, topic, excluded_ids | set(candidate_ids), TOPIC_CANDIDATES_PER_TOPIC
        )
    if len(candidate_ids) < limit:
        candidate_ids += repository.recent_news_ids(
            session, excluded_ids | set(candidate_ids), RECENT_FALLBACK_LIMIT
        )

    candidate_keywords = repository.keyword_counts_for_news(session, candidate_ids)
    unseen_words = {word for counts in candidate_keywords.values() for word in counts} - idf_map.keys()
    idf_map.update(repository.idf_for_words(session, unseen_words, total))
    candidates = repository.load_candidates(session, candidate_ids, candidate_keywords)

    ranked = rank_candidates(
        candidates=candidates,
        idf_map=idf_map,
        current_keywords=current_keywords,
        profile=profile,
        include_words=include,
        exclude_words=exclude,
        ad_filter_threshold=user.ad_filter_threshold if user else DEFAULT_AD_FILTER_THRESHOLD,
        now=now,
        limit=limit,
        seen_titles=repository.news_titles(session, seen_ids),
        topics=chosen,
        strength=strength,
    )
    return [
        RecommendationPayload(
            newsId=item.candidate.news_id,
            title=item.candidate.title,
            url=item.candidate.url,
            score=item.score,
            reasons=item.reasons,
            adProbability=item.candidate.ad_probability,
            publisher=item.candidate.publisher,
        )
        for item in ranked
    ]


def record_read(session: Session, user: CurrentUser, news_id: int) -> None:
    repository.record_read(session, user.id, news_id)


def get_profile(session: Session, user: CurrentUser) -> ProfilePayload:
    total = repository.total_news_count(session)
    include, exclude = repository.preferences(session, user.id)
    history, history_words, _ = _history_entries(session, user.id)
    idf_map = repository.idf_for_words(session, history_words, total)
    learned = build_profile(history, idf_map, set(), exclude, datetime.now(timezone.utc))
    chosen = repository.topics(session, user.id)

    interests = [InterestPayload(term=term, weight=1.0, source="manual") for term in sorted(include)]
    interests += [
        InterestPayload(term=term, weight=round(weight, 3), source="history")
        for term, weight in top_profile_terms(learned, PROFILE_INTEREST_LIMIT)
        if term not in include
    ]
    history_count = repository.history_count(session, user.id)
    return ProfilePayload(
        interests=interests,
        excluded=sorted(exclude),
        adFilterThreshold=user.ad_filter_threshold,
        historyCount=history_count,
        topics=[topic for topic in TOPIC_LABELS if topic in chosen],
        topicWeight=round(topic_strength(history_count), 3) if chosen else 0.0,
    )


def set_topics(session: Session, user_id: int, chosen: list[str]) -> None:
    repository.replace_topics(session, user_id, chosen)


def set_initial_interests(session: Session, user_id: int, chosen: list[str], keywords: list[str]) -> None:
    """Sign-up interests. Keywords that could never match an article are dropped instead of failing sign-up."""
    set_topics(session, user_id, chosen)
    terms = dict.fromkeys(term for word in keywords if (term := normalize_term(word)))
    for term in list(terms)[:INITIAL_KEYWORD_LIMIT]:
        repository.upsert_preference(session, user_id, term, "include")


def set_keyword_preference(session: Session, user: CurrentUser, term: str, preference: str) -> None:
    # Store the same form recommendations match on, so '안경을' and '안경' are one setting.
    normalized = normalize_term(term)
    if normalized is None:
        # Such a setting could never match an article, so refuse it instead of storing a no-op.
        raise HTTPException(status_code=422, detail=f"'{term}'은(는) 기사 키워드로 쓰이지 않는 단어입니다.")
    repository.upsert_preference(session, user.id, normalized, preference)


def delete_keyword_preference(session: Session, user: CurrentUser, term: str) -> bool:
    normalized = normalize_term(term) or term
    return repository.delete_preference(session, user.id, normalized) or (
        normalized != term and repository.delete_preference(session, user.id, term)
    )


def update_ad_filter(session: Session, user: CurrentUser, threshold: float) -> None:
    repository.update_ad_filter_threshold(session, user.id, round(threshold, 2))


def list_history(session: Session, user: CurrentUser, limit: int, offset: int) -> HistoryPayload:
    items = [HistoryItemPayload(**row) for row in repository.list_history(session, user.id, limit, offset)]
    return HistoryPayload(items=items, total=repository.history_count(session, user.id))


def delete_history(session: Session, user: CurrentUser, news_id: int) -> bool:
    return repository.delete_history(session, user.id, news_id)


def export_user_data(session: Session, user: CurrentUser) -> dict[str, Any]:
    """Everything stored about the user, for the 내 데이터 내보내기 download."""
    account = session.get(AppUser, user.id)
    include, exclude = repository.preferences(session, user.id)
    total = repository.history_count(session, user.id)
    return {
        "exportedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "account": {
            "email": user.email,
            "createdAt": account.created_at.isoformat() if account and account.created_at else None,
            "adFilterThreshold": user.ad_filter_threshold,
        },
        "keywordPreferences": {"include": sorted(include), "exclude": sorted(exclude)},
        "interestTopics": sorted(repository.topics(session, user.id)),
        "readingHistory": repository.list_history(session, user.id, limit=max(total, 1), offset=0),
    }
