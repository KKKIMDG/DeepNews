from fastapi import APIRouter, Depends, Response

from ...database import get_session
from ..personalization import service as personalization_service
from . import service
from .dependencies import CurrentUser, get_bearer_token, get_current_user
from .schemas import AuthResponse, ChangePasswordRequest, DeleteAccountRequest, LoginRequest, SignupRequest, UserPayload

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(req: SignupRequest):
    with get_session() as session:
        user, token = service.signup(session, req.email, req.password, req.inviteCode)
        personalization_service.set_initial_interests(session, user.id, req.topics, req.keywords)
        return AuthResponse(token=token, user=UserPayload(id=user.id, email=user.email))


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest):
    with get_session() as session:
        user, token = service.login(session, req.email, req.password)
        return AuthResponse(token=token, user=UserPayload(id=user.id, email=user.email))


@router.post("/logout", status_code=204)
def logout(token: str | None = Depends(get_bearer_token)):
    if token:
        with get_session() as session:
            service.logout(session, token)
    return Response(status_code=204)


@router.get("/me", response_model=UserPayload)
def me(user: CurrentUser = Depends(get_current_user)):
    return UserPayload(id=user.id, email=user.email)


@router.put("/password", status_code=204)
def change_password(
    req: ChangePasswordRequest,
    user: CurrentUser = Depends(get_current_user),
    token: str | None = Depends(get_bearer_token),
):
    with get_session() as session:
        service.change_password(session, user.id, token or "", req.currentPassword, req.newPassword)
    return Response(status_code=204)


@router.delete("/me", status_code=204)
def delete_me(req: DeleteAccountRequest, user: CurrentUser = Depends(get_current_user)):
    with get_session() as session:
        service.delete_account(session, user.id, req.password)
    return Response(status_code=204)
