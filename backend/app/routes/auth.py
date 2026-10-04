"""Auth API routes."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, get_request_meta
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.schemas.user import UserOut
from app.services.auth_service import AuthService
from app.services.email_service import EmailService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    meta = get_request_meta(request)
    service = AuthService(db)
    user = service.register(
        full_name=payload.full_name,
        email=payload.email,
        pin=payload.pin,
        **meta,
    )
    # Fire-and-forget welcome email
    EmailService(db, background_tasks=background_tasks).send_welcome(user)
    return user


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    meta = get_request_meta(request)
    service = AuthService(db)
    _, access, refresh, expires_in = service.login(
        email=payload.email,
        pin=payload.pin,
        **meta,
    )
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    service = AuthService(db)
    access, new_refresh, expires_in = service.refresh(payload.refresh_token)
    return TokenPair(
        access_token=access,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    service.logout(current_user)
    return None
