from __future__ import annotations

from pydantic import BaseModel, Field


class CollectNaverNewsRequest(BaseModel):
    keywords: list[str] | None = None
    per_keyword: int = Field(default=100, ge=1, le=100)


class BuildMindSvdRequest(BaseModel):
    max_behaviors: int = Field(default=100_000, ge=1)
    n_components: int = Field(default=64, ge=2, le=256)


class BuildMappingRequest(BaseModel):
    limit_mind_items: int | None = Field(default=None, ge=1)


class NaverRecommendationItem(BaseModel):
    newsId: str
    title: str
    url: str
    description: str = ""
    publisher: str = ""
    pubDate: str = ""
    category: str = ""
    score: float
    reason: str


class MindSvdRecommendationResponse(BaseModel):
    userId: str
    source: str = "mind_svd_mock_mapping"
    items: list[NaverRecommendationItem]


class DemoUserResponse(BaseModel):
    userId: str
    interactionCount: int
