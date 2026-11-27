from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from ..personalization.schemas import TopicList

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not EMAIL_PATTERN.match(email):
            raise ValueError("올바른 이메일 주소를 입력해 주세요.")
        return email


class SignupRequest(LoginRequest):
    password: str = Field(min_length=8, max_length=128)
    inviteCode: str = Field(default="", max_length=128)
    # Initial interests for the cold start; both can be changed later in the panel.
    topics: TopicList = []
    keywords: list[Annotated[str, Field(max_length=50)]] = Field(default=[], max_length=10)


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=128)
    newPassword: str = Field(min_length=8, max_length=128)


class UserPayload(BaseModel):
    id: int
    email: str


class AuthResponse(BaseModel):
    token: str
    user: UserPayload
