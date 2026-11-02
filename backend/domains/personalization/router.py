from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ...database import get_session
from ..auth.dependencies import CurrentUser, get_current_user
from . import service
from .schemas import (
    HistoryPayload,
    KeywordPreferenceRequest,
    ProfilePayload,
    RecommendationPayload,
    SettingsRequest,
    TopicsRequest,
)

router = APIRouter(prefix="/api/v1/me", tags=["personalization"])


@router.get("/profile", response_model=ProfilePayload)
def get_profile(user: CurrentUser = Depends(get_current_user)):
    with get_session() as session:
        return service.get_profile(session, user)


@router.put("/keywords", response_model=ProfilePayload)
def set_keyword(req: KeywordPreferenceRequest, user: CurrentUser = Depends(get_current_user)):
    with get_session() as session:
        service.set_keyword_preference(session, user, req.term, req.preference)
        session.flush()
        return service.get_profile(session, user)


@router.delete("/keywords", response_model=ProfilePayload)
def delete_keyword(
    # A query parameter, not a path segment, so terms like '5G/6G' can still be removed.
    term: str = Query(min_length=1, max_length=50),
    user: CurrentUser = Depends(get_current_user),
):
    with get_session() as session:
        if not service.delete_keyword_preference(session, user, term.strip()):
            raise HTTPException(status_code=404, detail="설정되지 않은 키워드입니다.")
        return service.get_profile(session, user)


@router.put("/topics", response_model=ProfilePayload)
def set_topics(req: TopicsRequest, user: CurrentUser = Depends(get_current_user)):
    with get_session() as session:
        service.set_topics(session, user.id, req.topics)
        session.flush()
        return service.get_profile(session, user)


@router.put("/settings", response_model=ProfilePayload)
def update_settings(req: SettingsRequest, user: CurrentUser = Depends(get_current_user)):
    with get_session() as session:
        service.update_ad_filter(session, user, req.adFilterThreshold)
        updated = replace(user, ad_filter_threshold=round(req.adFilterThreshold, 2))
        return service.get_profile(session, updated)


@router.get("/history", response_model=HistoryPayload)
def get_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(get_current_user),
):
    with get_session() as session:
        return service.list_history(session, user, limit, offset)


@router.delete("/history/{news_id}", status_code=204)
def delete_history(news_id: int, user: CurrentUser = Depends(get_current_user)):
    with get_session() as session:
        if not service.delete_history(session, user, news_id):
            raise HTTPException(status_code=404, detail="읽은 기록에 없는 기사입니다.")
    return Response(status_code=204)


@router.get("/recommendations", response_model=list[RecommendationPayload])
def get_recommendations(
    limit: int = Query(default=10, ge=1, le=30),
    user: CurrentUser = Depends(get_current_user),
):
    with get_session() as session:
        return service.recommend(session, user, current_news_id=None, limit=limit)


@router.get("/export")
def export_my_data(user: CurrentUser = Depends(get_current_user)):
    with get_session() as session:
        return service.export_user_data(session, user)
