"""Pydantic schemas for request/response validation."""
from __future__ import annotations

from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.schemas.notification import NotificationOut
from app.schemas.transaction import (
    DepositRequest,
    StatementRequest,
    TransactionOut,
    TransferRequest,
    WithdrawRequest,
)
from app.schemas.user import (
    KYCUpdateRequest,
    NotificationPreferences,
    UserOut,
    UserUpdateRequest,
)

__all__ = [
    "DepositRequest",
    "KYCUpdateRequest",
    "LoginRequest",
    "NotificationOut",
    "NotificationPreferences",
    "RefreshRequest",
    "RegisterRequest",
    "StatementRequest",
    "TokenPair",
    "TransactionOut",
    "TransferRequest",
    "UserOut",
    "UserUpdateRequest",
    "WithdrawRequest",
]
