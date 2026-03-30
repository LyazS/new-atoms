from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.schemas.auth import AuthResponse, UserAuthRequest, UserPublic
from app.services.auth import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _build_auth_response(user: UserPublic) -> AuthResponse:
    token, expires_in = auth_service.create_access_token(user_id=user.id)
    return AuthResponse(access_token=token, expires_in=expires_in, user=user)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(request: UserAuthRequest) -> AuthResponse:
    user = auth_service.create_user(username=request.username, password=request.password)
    return _build_auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(request: UserAuthRequest) -> AuthResponse:
    user = auth_service.authenticate_user(username=request.username, password=request.password)
    return _build_auth_response(user)


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return current_user
