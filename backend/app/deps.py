"""FastAPI dependencies shared across routes."""
from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User
from app.services.token_service import get_current_user_from_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)


def get_db() -> Session:
    """Yields a scoped DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the user from the access token in the Authorization header."""
    user = get_current_user_from_token(token, db)

    # Stash the user on request.state so audit logs can pick it up.
    request.state.current_user = user
    return user


def get_request_meta(request: Request) -> dict[str, str | None]:
    """Extract client IP + User-Agent for audit logging."""
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
    return {
        "ip_address": ip,
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }
