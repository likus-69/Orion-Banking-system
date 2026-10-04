"""Admin schemas — KYC review + user management."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import KycStatus, UserRole


class AdminUserOut(BaseModel):
    """Admin-facing user view — exposes more fields than the customer UserOut."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_number: str
    full_name: str
    email: str
    role: UserRole
    balance: float
    phone: Optional[str] = None
    address_line: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    kyc_status: KycStatus
    kyc_reviewed_by: Optional[int] = None
    kyc_reviewed_at: Optional[datetime] = None
    kyc_rejection_reason: Optional[str] = None
    is_active: bool
    is_locked: bool
    failed_login_attempts: int
    created_at: datetime


class AdminUserListOut(BaseModel):
    """Lighter list view for the admin user-management page."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_number: str
    full_name: str
    email: str
    role: UserRole
    balance: float
    kyc_status: KycStatus
    is_active: bool
    is_locked: bool
    created_at: datetime


class KycApproveRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=500)


class KycRejectRequest(BaseModel):
    reason: str = Field(..., min_length=4, max_length=500)


class AdminStatsOut(BaseModel):
    """Dashboard summary for admins."""

    total_users: int
    total_admins: int
    pending_kyc: int
    verified_kyc: int
    rejected_kyc: int
    locked_accounts: int
    total_balance: float
    transactions_today: int
