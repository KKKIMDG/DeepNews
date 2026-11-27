from __future__ import annotations

from pydantic import BaseModel


class NaverNewsItem(BaseModel):
    title: str
    description: str
    url: str
    naverUrl: str = ""
    source: str
    publishedAt: str = ""


class NaverNewsResponse(BaseModel):
    query: str
    items: list[NaverNewsItem]
