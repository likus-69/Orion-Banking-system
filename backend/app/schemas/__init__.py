"""Schemas index — re-exports for convenience."""
from __future__ import annotations

from app.schemas.admin import (
    AdminStatsOut,
    AdminUserListOut,
    AdminUserOut,
    KycApproveRequest,
    KycRejectRequest,
)
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
from app.schemas.scheduled_transfer import (
    ScheduledTransferCreateRequest,
    ScheduledTransferExecutionOut,
    ScheduledTransferOut,
    ScheduledTransferUpdateRequest,
)
from app.schemas.user import (
    KYCUpdateRequest,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    UserOut,
    UserUpdateRequest,
)
from app.schemas.webhook import (
    WebhookCreateRequest,
    WebhookDeliveryOut,
    WebhookEventTypeInfo,
    WebhookOut,
    WebhookUpdateRequest,
)

__all__ = [
    "AdminStatsOut",
    "AdminUserListOut",
    "AdminUserOut",
    "DepositRequest",
    "KYCUpdateRequest",
    "KycApproveRequest",
    "KycRejectRequest",
    "LoginRequest",
    "NotificationOut",
    "NotificationPreferences",
    "NotificationPreferencesUpdate",
    "RefreshRequest",
    "RegisterRequest",
    "ScheduledTransferCreateRequest",
    "ScheduledTransferExecutionOut",
    "ScheduledTransferOut",
    "ScheduledTransferUpdateRequest",
    "StatementRequest",
    "TokenPair",
    "TransactionOut",
    "TransferRequest",
    "UserOut",
    "UserUpdateRequest",
    "WebhookCreateRequest",
    "WebhookDeliveryOut",
    "WebhookEventTypeInfo",
    "WebhookOut",
    "WebhookUpdateRequest",
    "WithdrawRequest",
]
