from fastapi import APIRouter, HTTPException

from .schemas import AnalyzeArticleApiResponse, AnalyzeArticleRequest, NewsCrawlRequest
from .service import analyze_or_get, bulk_save_crawled_news, save_crawled_news

router = APIRouter(prefix="/api/v1/news", tags=["news"])


@router.post("/crawl")
def receive_crawl(payload: NewsCrawlRequest):
    try:
        news_id = save_crawled_news(payload)
        return {"message": f"뉴스 수집 및 분석 요청 완료 (ID: {news_id})", "newsId": news_id}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=f"뉴스 저장 실패: {exception}") from exception


@router.post("/crawl/bulk")
def receive_bulk_crawl(payloads: list[NewsCrawlRequest]):
    return bulk_save_crawled_news(payloads)


@router.post("/analyze", response_model=AnalyzeArticleApiResponse)
def analyze_article_api(req: AnalyzeArticleRequest):
    try:
        return analyze_or_get(req.url)
    except HTTPException:
        raise
    except Exception as exception:
        raise HTTPException(status_code=500, detail=f"기사 분석 실패: {exception}") from exception
