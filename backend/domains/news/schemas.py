from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalyzeArticleRequest(BaseModel):
    url: str


class KeywordPayload(BaseModel):
    term: str
    count: int


class ArticlePayload(BaseModel):
    title: str
    url: str


class AdLikelihoodPayload(BaseModel):
    label: str
    score: float


class AnalyzeArticleApiResponse(BaseModel):
    newsId: int | None = None
    cached: bool
    article: ArticlePayload
    keywords: list[KeywordPayload]
    summary: str
    recommendations: list[dict[str, str]]
    adLikelihood: AdLikelihoodPayload


class NewsCrawlRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    url: str
    source: str
    content: str
    original_content: str | None = None
    published_at: str | None = None
    token_counts: dict[str, int] = Field(default_factory=dict)
    extraData: dict[str, Any] = Field(default_factory=dict)
