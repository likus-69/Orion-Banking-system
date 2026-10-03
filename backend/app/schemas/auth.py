"""Auth-related schemas."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.config import settings


class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    pin: str = Field(..., min_length=settings.pin_min_length, max_length=settings.pin_max_length)


class LoginRequest(BaseModel):
    email: EmailStr
    pin: str = Field(..., min_length=settings.pin_min_length, max_length=settings.pin_max_length)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access_token expires
