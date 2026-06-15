from __future__ import annotations

from fastapi import APIRouter, Query

from .schemas import InteractionRequest, InteractionResponse, RecommendationResponse
from .service import recommend_for_article, record_interaction

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


@router.get("", response_model=RecommendationResponse)
def get_recommendations(
    news_id: int | None = Query(default=None, alias="newsId"),
    client_user_id: str | None = Query(default=None, alias="clientUserId"),
    limit: int = Query(default=5, ge=1, le=20),
):
    return {
        "items": recommend_for_article(
            current_news_id=news_id,
            client_user_id=client_user_id,
            limit=limit,
        )
    }


@router.post("/interactions", response_model=InteractionResponse)
def create_interaction(payload: InteractionRequest):
    return {
        "recorded": record_interaction(
            client_user_id=payload.clientUserId,
            news_id=payload.newsId,
            url=payload.url,
            interaction_type=payload.interactionType,
        )
    }
