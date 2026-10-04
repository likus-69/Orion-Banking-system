"""Schemas index — re-exports for convenience."""
from __future__ import annotations

from app.schemas.admin import (
    AdminStatsOut,
    AdminUserListOut,
    AdminUserOut,
    KycApproveRequest,
    KycRejectRequest,
)
from app.schemas.audit import AuditLogListResponse, AuditLogOut
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    VerifyTotpRequest,
)
from app.schemas.beneficiary import (
    BeneficiaryCreateRequest,
    BeneficiaryOut,
    BeneficiarySaveFromTransferRequest,
    BeneficiarySearchOut,
    BeneficiaryUpdateRequest,
)
from app.schemas.notification import NotificationOut
from app.schemas.scheduled_transfer import (
    ScheduledTransferCreateRequest,
    ScheduledTransferExecutionOut,
    ScheduledTransferOut,
    ScheduledTransferUpdateRequest,
)
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
    "AuditLogListResponse",
    "AuditLogOut",
    "BeneficiaryCreateRequest",
    "BeneficiaryOut",
    "BeneficiarySaveFromTransferRequest",
    "BeneficiarySearchOut",
    "BeneficiaryUpdateRequest",
    "DepositRequest",
    "KYCUpdateRequest",
    "KycApproveRequest",
    "KycRejectRequest",
    "LoginRequest",
    "LoginResponse",
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
    "VerifyTotpRequest",
    "WebhookCreateRequest",
    "WebhookDeliveryOut",
    "WebhookEventTypeInfo",
    "WebhookOut",
    "WebhookUpdateRequest",
    "WithdrawRequest",
]
