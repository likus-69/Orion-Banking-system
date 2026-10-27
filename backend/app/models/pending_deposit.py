"""PendingDeposit model — tracks mobile money deposits awaiting confirmation."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PendingDepositStatus(str, enum.Enum):
    """Lifecycle of a mobile money deposit."""

    pending = "pending"        # payment prompt sent, awaiting user approval
    completed = "completed"    # provider confirmed payment, account credited
    failed = "failed"          # user declined, timed out, or provider error
    expired = "expired"        # no response within 24h


class PendingDeposit(Base):
    """A mobile money deposit that's been initiated but not yet confirmed.

    Created when a user calls /api/deposit/initiate.
    Updated to 'completed' when the provider's webhook callback confirms payment.
    """

    __tablename__ = "pending_deposits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Our internal reference (e.g. DEP-AB12-CD34)
    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    # Provider's transaction reference (from MTN/Airtel API response)
    provider_reference: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    # Which provider: "stub" | "mtn_momo" | "airtel_money"
    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    # Amount + phone
    amount: Mapped[float] = mapped_column(Integer, nullable=False)  # stored as cents to avoid float issues... actually keep as float for simplicity
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # The transaction ID once the deposit is completed (FK to transactions table)
    transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[PendingDepositStatus] = mapped_column(
        Enum(PendingDepositStatus, name="pending_deposit_status"),
        default=PendingDepositStatus.pending,
        nullable=False,
        index=True,
    )

    # Provider's callback payload (raw JSON, for debugging)
    callback_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # created_at + 24h
