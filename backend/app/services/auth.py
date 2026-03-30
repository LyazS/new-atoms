from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select

from app.config.settings import settings
from app.db.models import UserModel
from app.db.session import SessionLocal
from app.schemas.auth import UserPublic


class AuthService:
    def hash_password(self, password: str, *, salt: str | None = None) -> str:
        salt_value = salt or secrets.token_hex(16)
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_value.encode("utf-8"), 100_000)
        return f"{salt_value}${base64.urlsafe_b64encode(derived).decode('utf-8')}"

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            salt, expected = password_hash.split("$", 1)
        except ValueError:
            return False
        candidate = self.hash_password(password, salt=salt)
        return hmac.compare_digest(candidate, f"{salt}${expected}")

    def create_access_token(self, *, user_id: str) -> tuple[str, int]:
        expires_in = settings.access_token_expire_minutes * 60
        payload = {
            "sub": user_id,
            "exp": int((datetime.now(timezone.utc) + timedelta(seconds=expires_in)).timestamp()),
        }
        body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("utf-8")
        signature = hmac.new(
            settings.auth_secret_key.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{body}.{signature}", expires_in

    def verify_access_token(self, token: str) -> str:
        try:
            body, signature = token.split(".", 1)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token") from exc

        expected = hmac.new(
            settings.auth_secret_key.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token")

        try:
            payload = json.loads(base64.urlsafe_b64decode(body.encode("utf-8")).decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token") from exc

        exp = payload.get("exp")
        user_id = payload.get("sub")
        if not isinstance(exp, int) or not isinstance(user_id, str):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token")
        if exp <= int(datetime.now(timezone.utc).timestamp()):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="access token expired")
        return user_id

    def create_user(self, *, username: str, password: str) -> UserPublic:
        normalized = username.strip()
        if not normalized:
            raise HTTPException(status_code=400, detail="username is required")
        with SessionLocal() as db:
            existing = db.scalar(select(UserModel).where(UserModel.username == normalized))
            if existing is not None:
                raise HTTPException(status_code=409, detail="username already exists")
            user = UserModel(username=normalized, password_hash=self.hash_password(password))
            db.add(user)
            db.commit()
            db.refresh(user)
            return self._to_public(user)

    def authenticate_user(self, *, username: str, password: str) -> UserPublic:
        with SessionLocal() as db:
            user = db.scalar(select(UserModel).where(UserModel.username == username.strip()))
            if user is None or not self.verify_password(password, user.password_hash):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password")
            return self._to_public(user)

    def get_user_by_id(self, user_id: str) -> UserPublic:
        with SessionLocal() as db:
            user = db.get(UserModel, user_id)
            if user is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
            return self._to_public(user)

    def _to_public(self, user: UserModel) -> UserPublic:
        return UserPublic(id=user.id, username=user.username, created_at=user.created_at)


auth_service = AuthService()
