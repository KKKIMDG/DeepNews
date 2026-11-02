from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, field_validator

from .ranking import TOPIC_LABELS


def _known_topics(values: list[str]) -> list[str]:
    unknown = [value for value in values if value not in TOPIC_LABELS]
    if unknown:
        raise ValueError(f"알 수 없는 관심 분야입니다: {', '.join(unknown)}")
    return list(dict.fromkeys(values))


# BigKinds top-level categories, duplicates dropped; shared with the sign-up request.
TopicList = Annotated[list[str], Field(max_length=len(TOPIC_LABELS) * 2), AfterValidator(_known_topics)]


class RecommendationPayload(BaseModel):
    newsId: int
    title: str
    url: str
    score: float
    reasons: list[str]
    adProbability: float | None = None


class InterestPayload(BaseModel):
    term: str
    weight: float
    source: Literal["history", "manual"]


class ProfilePayload(BaseModel):
    interests: list[InterestPayload]
    excluded: list[str]
    adFilterThreshold: float
    historyCount: int
    topics: list[str] = []
    # How strongly topics steer recommendations now (1.0 for a new account, fading as reads accumulate).
    topicWeight: float = 0.0


class TopicsRequest(BaseModel):
    topics: TopicList


class KeywordPreferenceRequest(BaseModel):
    term: str = Field(min_length=1, max_length=50)
    preference: Literal["include", "exclude"]

    @field_validator("term")
    @classmethod
    def strip_term(cls, value: str) -> str:
        term = value.strip()
        if not term:
            raise ValueError("키워드를 입력해 주세요.")
        return term


class SettingsRequest(BaseModel):
    # 1.0 turns the ad filter off; lower values hide more promotional articles.
    adFilterThreshold: float = Field(ge=0.1, le=1.0)


class HistoryItemPayload(BaseModel):
    newsId: int
    title: str
    url: str
    readCount: int
    lastReadAt: datetime
    adProbability: float | None = None


class HistoryPayload(BaseModel):
    items: list[HistoryItemPayload]
    total: int
