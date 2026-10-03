"""API routes — thin wrappers around services. No business logic here."""
from __future__ import annotations

from app.routes import accounts, auth, notifications, pages, statements, transactions

__all__ = ["accounts", "auth", "notifications", "pages", "statements", "transactions"]
