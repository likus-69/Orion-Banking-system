"""Auth-related schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.config import settings


class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    pin: str = Field(..., min_length=settings.pin_min_length, max_length=settings.pin_max_length)


class LoginRequest(BaseModel):
    email: EmailStr
    pin: str = Field(..., min_length=settings.pin_min_length, max_length=settings.pin_max_length)


class VerifyTotpRequest(BaseModel):
    challenge_token: str
    code: Optional[str] = Field(None, min_length=6, max_length=6)
    backup_code: Optional[str] = Field(None, min_length=8, max_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str


class LoginResponse(BaseModel):
    """Response shape for /login — one of two modes:
      - Standard:  access_token + refresh_token + token_type + expires_in
      - 2FA mode:   needs_totp=True + challenge_token
    """

    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: Optional[int] = None
    needs_totp: bool = False
    challenge_token: Optional[str] = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access_token expires


# ── 2FA ───────────────────────────────────────────────────────────
class TotpSetupResponse(BaseModel):
    secret: str
    qr_png_base64: str
    provisioning_uri: str
    issuer: str
    account: str


class TotpVerifySetupRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class TotpVerifySetupResponse(BaseModel):
    enabled: bool
    backup_codes: list[str]


class TotpDisableRequest(BaseModel):
    code: Optional[str] = Field(None, min_length=6, max_length=6)
    backup_code: Optional[str] = Field(None, min_length=8, max_length=8)


class TotpRegenerateBackupRequest(TotpDisableRequest):
    pass


class TotpRegenerateBackupResponse(BaseModel):
    backup_codes: list[str]


class TotpStatusResponse(BaseModel):
    enabled: bool
    setup_at: Optional[str] = None
    backup_codes_remaining: int
