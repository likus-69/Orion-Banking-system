"""Beneficiary model — saved recipients for quick transfers."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BeneficiaryCategory(str, enum.Enum):
    """User-defined category for grouping beneficiaries."""

    family = "family"
    friend = "friend"
    business = "business"
    utility = "utility"
    other = "other"


class Beneficiary(Base):
    """A saved recipient — owned by a user, private to them."""

    __tablename__ = "beneficiaries"
    __table_args__ = (
        # A user can save a given recipient account only once.
        UniqueConstraint("owner_user_id", "recipient_account_number", name="uq_beneficiary_owner_recipient"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Snapshot of recipient info at the time of save — name from their User record
    recipient_account_number: Mapped[str] = mapped_column(String(14), nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # User-set fields
    nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category: Mapped[BeneficiaryCategory] = mapped_column(
        Enum(BeneficiaryCategory, name="beneficiary_category"),
        default=BeneficiaryCategory.other,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )
