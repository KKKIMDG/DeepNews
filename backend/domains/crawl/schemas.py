from pydantic import BaseModel


class CrawlResponse(BaseModel):
    title: str
    url: str
    content: str
    published_at: str
    token_counts: dict[str, int]
    keywords: list[str]
