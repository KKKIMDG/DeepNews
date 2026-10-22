from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from urllib.parse import urlparse


class AnalyzeArticleRequest(BaseModel):
    url: str = Field(max_length=4096)
    title: str | None = Field(default=None, max_length=500)
    content: str | None = Field(default=None, min_length=100, max_length=100000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("HTTP(S) 기사 URL을 입력해 주세요.")
        return value

    @model_validator(mode="after")
    def validate_browser_article(self):
        if self.content is not None:
            if not self.title or not self.title.strip() or len(self.content.strip()) < 100:
                raise ValueError("기사 제목과 100자 이상의 본문이 필요합니다.")
        return self


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
