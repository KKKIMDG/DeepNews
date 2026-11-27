from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from ...database import get_session
from . import service


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str
    ad_filter_threshold: float


def get_bearer_token(authorization: str | None = Header(default=None)) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="인증 형식이 올바르지 않습니다.")
    return token.strip()


def get_optional_user(token: str | None = Depends(get_bearer_token)) -> CurrentUser | None:
    """Anonymous callers get None; a supplied but invalid token is rejected so clients re-login."""
    if token is None:
        return None
    with get_session() as session:
        user = service.resolve_user(session, token)
        if user is None:
            raise HTTPException(status_code=401, detail="로그인이 만료되었습니다. 다시 로그인해 주세요.")
        return CurrentUser(id=user.id, email=user.email, ad_filter_threshold=float(user.ad_filter_threshold))


def get_current_user(user: CurrentUser | None = Depends(get_optional_user)) -> CurrentUser:
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user
