"""PIN hashing + JWT issuance + refresh token management.

Pure utilities + a TokenService class for refresh-token rotation.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import AuthenticationError
from app.models.user import RefreshToken, User
from app.repositories.user_repo import UserRepository

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── PIN helpers ────────────────────────────────────────────────────
def hash_pin(pin: str) -> str:
    return pwd_context.hash(pin)


def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    return pwd_context.verify(plain_pin, hashed_pin)


def is_weak_pin(pin: str) -> bool:
    """Reject sequential (1234) or all-same (1111) PINs."""
    if len(pin) < settings.pin_min_length:
        return True
    digits = [int(c) for c in pin]
    if len(set(digits)) == 1:
        return True
    diffs = {digits[i + 1] - digits[i] for i in range(len(digits) - 1)}
    if diffs == {1} or diffs == {-1}:
        return True
    return False


# ── Token helpers ──────────────────────────────────────────────────
def _create_token(subject: str, *, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_delta,
        "type": token_type,
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: str) -> str:
    return _create_token(
        subject,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(
        subject,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise AuthenticationError("Invalid or expired token.") from exc

    if payload.get("type") != expected_type:
        raise AuthenticationError(f"Expected {expected_type} token, got {payload.get('type')!r}.")
    return payload


def hash_token(token: str) -> str:
    """SHA-256 of refresh token for DB storage (we never store raw tokens)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenService:
    """Issue + verify access/refresh tokens; persist refresh tokens for revocation."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)

    def issue_token_pair(self, user: User) -> tuple[str, str, int]:
        access = create_access_token(subject=user.email)
        refresh = create_refresh_token(subject=user.email)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        self.users.store_refresh_token(
            user_id=user.id,
            token_hash=hash_token(refresh),
            expires_at=expires_at,
        )
        return access, refresh, settings.access_token_expire_minutes * 60

    def rotate_refresh_token(self, refresh_token: str) -> tuple[str, str, int]:
        payload = decode_token(refresh_token, expected_type="refresh")
        email = payload.get("sub")
        if email is None:
            raise AuthenticationError("Malformed refresh token.")

        user = self.users.get_by_email(email)
        if user is None:
            raise AuthenticationError("User not found.")

        stored = self.users.get_refresh_token(hash_token(refresh_token))
        if stored is None or stored.revoked or stored.expires_at < datetime.now(timezone.utc):
            raise AuthenticationError("Refresh token is invalid or expired.")

        self.users.revoke_refresh_token(hash_token(refresh_token))
        return self.issue_token_pair(user)

    def revoke_all_for_user(self, user_id: int) -> None:
        self.users.revoke_all_refresh_tokens(user_id)


def get_current_user_from_token(token: str, db: Session) -> User:
    """Verify an access token and return the User instance."""
    payload = decode_token(token, expected_type="access")
    email = payload.get("sub")
    if email is None:
        raise AuthenticationError("Malformed access token.")

    user = UserRepository(db).get_by_email(email)
    if user is None:
        raise AuthenticationError("User not found.")
    if not user.is_active or user.is_locked:
        raise AuthenticationError("Account is disabled or locked.")
    return user
