"""Transaction model + categories."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DECIMAL, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TransactionType(str, enum.Enum):
    deposit = "deposit"
    withdrawal = "withdrawal"
    transfer = "transfer"
    fee = "fee"
    interest = "interest"
    refund = "refund"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    reversed = "reversed"


class TransactionCategory(str, enum.Enum):
    """User-defined or auto-detected category for analytics."""

    general = "general"
    salary = "salary"
    groceries = "groceries"
    utilities = "utilities"
    rent = "rent"
    dining = "dining"
    transport = "transport"
    entertainment = "entertainment"
    shopping = "shopping"
    health = "health"
    transfer = "transfer"
    other = "other"


class Transaction(Base):
    """Money movement between two accounts (or one account + external for deposit/withdrawal)."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    from_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    to_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="tx_type"), nullable=False
    )
    amount: Mapped[float] = mapped_column(DECIMAL(precision=15, scale=2), nullable=False)
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[TransactionCategory] = mapped_column(
        Enum(TransactionCategory, name="tx_category"),
        default=TransactionCategory.general,
        nullable=False,
    )
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="tx_status"),
        default=TransactionStatus.completed,
        nullable=False,
    )

    # Idempotency key supplied by client (optional but recommended for transfers).
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    sender: Mapped[Optional["User"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        back_populates="sent_transactions",
        foreign_keys=[from_account_id],
    )
    receiver: Mapped[Optional["User"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        back_populates="received_transactions",
        foreign_keys=[to_account_id],
    )
