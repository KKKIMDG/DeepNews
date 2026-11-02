import logging

from fastapi import APIRouter, Depends, HTTPException

from ..analysis.service import AnalysisUnavailable
from ..auth.dependencies import CurrentUser, get_current_user
from .schemas import AnalyzeArticleApiResponse, AnalyzeArticleRequest, ReportRequest, ReportResponse
from .service import analyze_or_get, report_news

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/news", tags=["news"])


@router.post("/analyze", response_model=AnalyzeArticleApiResponse)
def analyze_article_api(req: AnalyzeArticleRequest, user: CurrentUser = Depends(get_current_user)):
    # Login is required because the result becomes shared data; the submitter is recorded with it.
    try:
        return analyze_or_get(req.url, req.title, req.content, user, req.publishedAt)
    except HTTPException:
        raise
    except AnalysisUnavailable as exception:
        raise HTTPException(status_code=503, detail=str(exception)) from exception
    except Exception as exception:
        # Details (SQL, paths) stay in the server log.
        logger.exception("기사 분석 실패: %s", req.url)
        raise HTTPException(status_code=500, detail="기사 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.") from exception


@router.post("/{news_id}/report", response_model=ReportResponse)
def report_article(news_id: int, req: ReportRequest, user: CurrentUser = Depends(get_current_user)):
    return report_news(news_id, user, req.reason)
