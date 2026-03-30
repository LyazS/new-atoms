from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserAuthRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class UserPublic(BaseModel):
    id: str
    username: str
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic
