from __future__ import annotations

from pydantic import BaseModel, Field


class RecommendationItem(BaseModel):
    newsId: int
    title: str
    url: str
    score: float = 0.0
    reason: str
    source: str


class RecommendationResponse(BaseModel):
    items: list[RecommendationItem]


class InteractionRequest(BaseModel):
    clientUserId: str
    newsId: int | None = None
    url: str | None = None
    interactionType: str = Field(default="VIEW")


class InteractionResponse(BaseModel):
    recorded: bool
