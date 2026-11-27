import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from ...config import settings
from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.rate_limit import SlidingWindowLimiter
from .schemas import NaverNewsResponse
from .service import NaverSearchUnavailable, search_news

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/naver", tags=["naver-search"])

# The search API allows 25,000 calls a day per key; one account cannot use up the team's share.
# One analyzed article makes up to five calls (a personalized query, its fallback, three interest lists).
search_limiter = SlidingWindowLimiter(limit=60, window_seconds=600)


@router.get("/news", response_model=NaverNewsResponse)
def naver_news(
    query: str = Query(min_length=1, max_length=100),
    display: int = Query(default=5, ge=1, le=10),
    # NAVER's own orderings: relevance or newest first.
    sort: str = Query(default="sim", pattern="^(sim|date)$"),
    user: CurrentUser = Depends(get_current_user),
):
    query = query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="검색어를 입력해 주세요.")
    key = f"user:{user.id}"
    if search_limiter.blocked(key):
        raise HTTPException(status_code=429, detail="네이버 검색 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
    search_limiter.record(key)
    try:
        items = search_news(query, display, settings.naver_client_id, settings.naver_client_secret, sort)
    except NaverSearchUnavailable as exception:
        # Only the reason is logged; results and queries are not kept.
        logger.warning("네이버 검색 실패: %s", exception)
        raise HTTPException(status_code=503, detail=str(exception)) from exception
    return {"query": query, "items": items}
