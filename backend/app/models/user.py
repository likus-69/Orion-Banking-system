"""User model — includes KYC fields, role, and supporting models."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DECIMAL, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    """User role for authorization. Defaults to 'customer'."""

    customer = "customer"
    support = "support"
    admin = "admin"


class KycStatus(str, enum.Enum):
    """KYC review lifecycle."""

    pending = "pending"       # account just created, no KYC submitted
    in_review = "in_review"   # user submitted KYC info, awaiting admin review
    verified = "verified"     # admin approved
    rejected = "rejected"     # admin rejected (see kyc_rejection_reason)


class User(Base):
    """A banking customer or staff member. PIN is stored as a bcrypt hash."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_number: Mapped[str] = mapped_column(String(14), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Balance stored as DECIMAL(15,2) — never compare via float.
    balance: Mapped[float] = mapped_column(DECIMAL(precision=15, scale=2), default=0, nullable=False)

    # ── Role ─────────────────────────────────────────────────────
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        default=UserRole.customer,
        nullable=False,
        index=True,
    )

    # ── KYC fields (user-submitted) ─────────────────────────────
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    address_line: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    date_of_birth: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    kyc_status: Mapped[KycStatus] = mapped_column(
        Enum(KycStatus, name="kyc_status"),
        default=KycStatus.pending,
        nullable=False,
        index=True,
    )

    # ── KYC review (admin-set) ───────────────────────────────────
    kyc_reviewed_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kyc_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    kyc_rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Lifecycle ────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    sent_transactions: Mapped[list["Transaction"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Transaction",
        back_populates="sender",
        foreign_keys="Transaction.from_account_id",
    )
    received_transactions: Mapped[list["Transaction"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Transaction",
        back_populates="receiver",
        foreign_keys="Transaction.to_account_id",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="user", foreign_keys="AuditLog.user_id"
    )
    # Self-referential FK for KYC reviewer (admin who reviewed this user)
    reviewed_kyc: Mapped[list["User"]] = relationship(
        "User",
        back_populates="reviewer_of",
        foreign_keys=[kyc_reviewed_by],
        remote_side="User.id",
    )
    reviewer_of: Mapped[list["User"]] = relationship(
        "User", back_populates="reviewed_kyc", foreign_keys=[kyc_reviewed_by]
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )

    # ── Helpers ──────────────────────────────────────────────────
    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.admin

    @property
    def is_support(self) -> bool:
        return self.role in (UserRole.support, UserRole.admin)


class RefreshToken(Base):
    """Persisted refresh tokens so they can be revoked."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
