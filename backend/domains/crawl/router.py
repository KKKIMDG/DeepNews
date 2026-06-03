from fastapi import APIRouter, Query

from .schemas import CrawlResponse
from .service import crawl_article

router = APIRouter(prefix="/crawl", tags=["crawl"])


@router.post("/article", response_model=CrawlResponse)
def crawl_article_endpoint(url: str = Query(..., description="크롤링할 기사 URL")):
    return crawl_article(url)
