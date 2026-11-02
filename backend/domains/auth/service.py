from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...config import settings
from .models import AppUser, UserSession
from .rate_limit import SlidingWindowLimiter
from .security import DUMMY_PASSWORD_HASH, hash_password, hash_session_token, new_session_token, verify_password

SESSION_TTL = timedelta(days=30)
LOGIN_FAILURES = SlidingWindowLimiter(limit=5, window_seconds=15 * 60)
SIGNUPS = SlidingWindowLimiter(limit=30, window_seconds=60 * 60)


def create_session(session: Session, user_id: int) -> str:
    token = new_session_token()
    session.add(
        UserSession(
            user_id=user_id,
            token_hash=hash_session_token(token),
            expires_at=datetime.now(timezone.utc) + SESSION_TTL,
        )
    )
    session.flush()
    return token


def signup(session: Session, email: str, password: str, invite_code: str = "") -> tuple[AppUser, str]:
    if SIGNUPS.blocked("all"):
        raise HTTPException(status_code=429, detail="회원가입 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
    SIGNUPS.record("all")
    required = settings.signup_invite_code
    if required and not hmac.compare_digest(invite_code.strip().encode(), required.encode()):
        raise HTTPException(status_code=403, detail="초대 코드가 올바르지 않습니다.")
    if session.scalar(select(AppUser.id).where(AppUser.email == email)) is not None:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

    user = AppUser(email=email, password_hash=hash_password(password))
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exception:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.") from exception
    return user, create_session(session, user.id)


def login(session: Session, email: str, password: str) -> tuple[AppUser, str]:
    if LOGIN_FAILURES.blocked(email):
        raise HTTPException(status_code=429, detail="로그인 실패가 너무 많습니다. 15분 뒤 다시 시도해 주세요.")
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    if not verify_password(password, user.password_hash if user else DUMMY_PASSWORD_HASH) or user is None:
        LOGIN_FAILURES.record(email)
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    LOGIN_FAILURES.reset(email)

    # Opportunistic cleanup: expired sessions of every user, not only this one's.
    session.execute(delete(UserSession).where(UserSession.expires_at <= datetime.now(timezone.utc)))
    return user, create_session(session, user.id)


def resolve_user(session: Session, token: str) -> AppUser | None:
    return session.scalar(
        select(AppUser)
        .join(UserSession, UserSession.user_id == AppUser.id)
        .where(
            UserSession.token_hash == hash_session_token(token),
            UserSession.expires_at > datetime.now(timezone.utc),
        )
    )


def logout(session: Session, token: str) -> None:
    session.execute(delete(UserSession).where(UserSession.token_hash == hash_session_token(token)))


def change_password(session: Session, user_id: int, current_token: str, current_password: str, new_password: str) -> None:
    user = session.get(AppUser, user_id)
    if user is None or not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=403, detail="현재 비밀번호가 올바르지 않습니다.")
    user.password_hash = hash_password(new_password)
    # Other devices must sign in again with the new password; this one stays signed in.
    session.execute(
        delete(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.token_hash != hash_session_token(current_token),
        )
    )


def delete_account(session: Session, user_id: int, password: str) -> None:
    user = session.get(AppUser, user_id)
    if user is None or not verify_password(password, user.password_hash):
        # 403, not 401: a mistyped password must not sign the client out.
        raise HTTPException(status_code=403, detail="비밀번호가 올바르지 않습니다.")
    # Sessions, reading history and keyword preferences go with it (on delete cascade); shared articles stay.
    session.execute(delete(AppUser).where(AppUser.id == user_id))
