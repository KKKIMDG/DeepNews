from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .schemas import (
    BuildMappingRequest,
    BuildMindSvdRequest,
    CollectNaverNewsRequest,
    DemoUserResponse,
    MindSvdRecommendationResponse,
)
from .service import (
    build_mapping,
    build_svd_model,
    collect_demo_naver_news,
    get_demo_user,
    recommend_naver_news,
)

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


@router.post("/naver/collect")
def collect_naver_news_api(payload: CollectNaverNewsRequest):
    try:
        return collect_demo_naver_news(payload.keywords, payload.per_keyword)
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception)) from exception


@router.post("/mind-svd/build")
def build_mind_svd_api(payload: BuildMindSvdRequest):
    try:
        return build_svd_model(payload.max_behaviors, payload.n_components)
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception)) from exception


@router.post("/mind-svd/mapping/build")
def build_mapping_api(payload: BuildMappingRequest):
    try:
        return build_mapping(payload.limit_mind_items)
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception)) from exception


@router.get("/mind-svd/demo-user", response_model=DemoUserResponse)
def demo_user_api():
    try:
        return get_demo_user()
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception)) from exception


@router.get("/mind-svd", response_model=MindSvdRecommendationResponse)
def recommend_mind_svd_api(
    user_id: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
):
    try:
        return recommend_naver_news(user_id=user_id, limit=limit)
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception)) from exception
