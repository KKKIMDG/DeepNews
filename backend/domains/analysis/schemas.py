from typing import Any

from pydantic import BaseModel


class ArticleRequest(BaseModel):
    url: str
    title: str
    text: str


class AnalysisResponse(BaseModel):
    url: str
    title: str
    is_clickbait: bool
    ad_probability: float
    summary: str
    named_entities: list[Any]
