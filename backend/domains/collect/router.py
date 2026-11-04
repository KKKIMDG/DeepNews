from fastapi import APIRouter, Depends, Query

from ...database import get_session
from ..auth.dependencies import CurrentUser, get_current_user
from . import repository
from .schemas import CandidatesResponse

router = APIRouter(prefix="/api/v1/collect", tags=["collect"])


@router.get("/candidates", response_model=CandidatesResponse)
def list_candidates(
    publisher: str = Query(default="", max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(get_current_user),
):
    """BigKinds articles still waiting for their full text; a person opens each one to analyze it."""
    with get_session() as session:
        rows = repository.candidates(session, publisher.strip(), limit, offset)
        sites = repository.candidate_sites(session)
        return {
            "publishers": publisher_totals(sites),
            "sites": [{"publisher": name, "origin": origin, "count": count} for name, origin, count in sites if origin],
            "items": [
                {"newsId": news_id, "url": url, "title": title, "publisher": name, "publishedAt": published_at or ""}
                for news_id, url, title, name, published_at in rows
            ],
            "collectedByMe": repository.collected_by(session, user.id),
        }


def publisher_totals(sites: list[tuple[str, str, int]]) -> list[dict]:
    totals: dict[str, int] = {}
    for name, _, count in sites:
        totals[name] = totals.get(name, 0) + count
    return [{"publisher": name, "count": count} for name, count in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))]
