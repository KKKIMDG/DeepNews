from fastapi import APIRouter

from .schemas import AnalysisResponse, ArticleRequest
from .service import analyze_article

router = APIRouter(prefix="/ai", tags=["analysis"])


@router.post("/analyze", response_model=AnalysisResponse)
def analyze(req: ArticleRequest):
    return analyze_article(req.url, req.title, req.text)
