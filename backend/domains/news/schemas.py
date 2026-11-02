from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator
from urllib.parse import urlparse

from ..personalization.schemas import RecommendationPayload


class AnalyzeArticleRequest(BaseModel):
    # news.url is varchar(512); a longer URL would fail at insert time.
    url: str = Field(max_length=512)
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=100, max_length=100000)
    publishedAt: str = Field(default="", max_length=64)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("HTTP(S) 기사 URL을 입력해 주세요.")
        return value

    @model_validator(mode="after")
    def validate_browser_article(self):
        if not self.title.strip() or len(self.content.strip()) < 100:
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
    recommendations: list[RecommendationPayload]
    adLikelihood: AdLikelihoodPayload
    contentOrigin: str = ""
    # A cached result built from text someone else submitted (or imported); the panel offers a report button.
    sharedFromOther: bool = False
    reportCount: int = 0
    reportedByMe: bool = False


class ReportRequest(BaseModel):
    reason: str = Field(default="", max_length=300)


class ReportResponse(BaseModel):
    reportCount: int
    reportedByMe: bool
    reanalysis: bool
