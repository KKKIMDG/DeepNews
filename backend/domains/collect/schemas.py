from __future__ import annotations

from pydantic import BaseModel


class PublisherCount(BaseModel):
    publisher: str
    count: int


class CandidateSite(BaseModel):
    publisher: str
    origin: str
    count: int


class CandidateItem(BaseModel):
    newsId: int
    url: str
    title: str
    publisher: str
    publishedAt: str = ""


class CandidatesResponse(BaseModel):
    publishers: list[PublisherCount]
    sites: list[CandidateSite] = []
    items: list[CandidateItem]
    # Articles this account has analyzed from the browser, cached ones included.
    collectedByMe: int
