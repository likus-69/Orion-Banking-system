"""User-related Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.config import settings
from app.models.user import KycStatus, UserRole


# ── Auth ──────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    pin: str = Field(..., min_length=settings.pin_min_length, max_length=settings.pin_max_length)


class LoginRequest(BaseModel):
    email: EmailStr
    pin: str = Field(..., min_length=settings.pin_min_length, max_length=settings.pin_max_length)


# ── Account operations ────────────────────────────────────────────
class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0, le=1_000_000_000)
    memo: str | None = Field(None, max_length=500)


class WithdrawRequest(DepositRequest):
    pass


class TransferRequest(BaseModel):
    recipient_account_number: str = Field(..., min_length=14, max_length=14)
    amount: float = Field(..., gt=0, le=1_000_000_000)
    memo: str | None = Field(None, max_length=500)
    idempotency_key: str | None = Field(None, min_length=8, max_length=64)


# ── User responses ────────────────────────────────────────────────
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_number: str
    full_name: str
    email: str
    balance: float  # serialised from DECIMAL — see serializer below
    role: UserRole
    phone: Optional[str] = None
    address_line: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    kyc_status: KycStatus
    kyc_rejection_reason: Optional[str] = None
    email_on_deposit: bool = True
    email_on_withdrawal: bool = True
    email_on_transfer_in: bool = True
    email_on_transfer_out: bool = True
    email_on_kyc_decision: bool = True
    is_active: bool = True
    created_at: datetime


class KYCUpdateRequest(BaseModel):
    phone: Optional[str] = Field(None, max_length=20)
    address_line: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    date_of_birth: Optional[datetime] = None


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)


class NotificationPreferencesUpdate(BaseModel):
    """Update email notification preferences."""

    email_on_deposit: Optional[bool] = None
    email_on_withdrawal: Optional[bool] = None
    email_on_transfer_in: Optional[bool] = None
    email_on_transfer_out: Optional[bool] = None
    email_on_kyc_decision: Optional[bool] = None


class NotificationPreferences(BaseModel):
    """Read-only view of notification preferences."""

    email_on_deposit: bool = True
    email_on_withdrawal: bool = True
    email_on_transfer_in: bool = True
    email_on_transfer_out: bool = True
    email_on_kyc_decision: bool = True
