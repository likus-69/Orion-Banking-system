"""API + page routes — thin wrappers around services. No business logic here."""
from __future__ import annotations

from app.routes import (
    accounts,
    admin,
    auth,
    beneficiaries,
    notifications,
    pages,
    scheduled_transfers,
    statements,
    totp,
    transactions,
    webhooks,
)

__all__ = [
    "accounts", "admin", "auth", "beneficiaries", "notifications", "pages",
    "scheduled_transfers", "statements", "totp",
    "transactions", "webhooks",
]
