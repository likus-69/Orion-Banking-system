"""Scheduled transfer + execution models."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DECIMAL, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScheduleType(str, enum.Enum):
    """How often the scheduled transfer fires."""

    once = "once"          # one-time future execution
    daily = "daily"        # every N days
    weekly = "weekly"      # specific day of week (0=Mon ... 6=Sun)
    monthly = "monthly"    # specific day of month (1-28; 28 = last day if month shorter)


class ScheduleStatus(str, enum.Enum):
    """Lifecycle of a scheduled transfer."""

    active = "active"
    paused = "paused"
    completed = "completed"   # one-time schedule that has executed
    cancelled = "cancelled"
    failed = "failed"         # too many consecutive failures


class ExecutionStatus(str, enum.Enum):
    """Outcome of a single scheduled execution attempt."""

    success = "success"
    failed = "failed"
    skipped = "skipped"       # e.g. account locked / insufficient funds on retry


class ScheduledTransfer(Base):
    """A user's recurring transfer rule."""

    __tablename__ = "scheduled_transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_account_number: Mapped[str] = mapped_column(String(14), nullable=False)
    amount: Mapped[float] = mapped_column(DECIMAL(precision=15, scale=2), nullable=False)
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Schedule
    schedule_type: Mapped[ScheduleType] = mapped_column(
        Enum(ScheduleType, name="schedule_type"), nullable=False
    )
    # For 'once': ISO datetime of when to execute
    # For 'daily': interval in days as string (e.g. "1", "7")
    # For 'weekly': day-of-week (0=Mon ... 6=Sun)
    # For 'monthly': day-of-month (1-28)
    schedule_config: Mapped[str] = mapped_column(String(50), nullable=False)

    # Execution state
    next_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_execution_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("scheduled_transfer_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[ScheduleStatus] = mapped_column(
        Enum(ScheduleStatus, name="schedule_status"),
        default=ScheduleStatus.active,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    executions: Mapped[list["ScheduledTransferExecution"]] = relationship(
        back_populates="scheduled_transfer",
        cascade="all, delete-orphan",
        foreign_keys="ScheduledTransferExecution.scheduled_transfer_id",
    )


class ScheduledTransferExecution(Base):
    """Record of one execution attempt of a scheduled transfer."""

    __tablename__ = "scheduled_transfer_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scheduled_transfer_id: Mapped[int] = mapped_column(
        ForeignKey("scheduled_transfers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The transaction created (null if execution failed)
    transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    transaction_reference: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, name="execution_status"),
        default=ExecutionStatus.success,
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False, index=True)

    scheduled_transfer: Mapped[ScheduledTransfer] = relationship(
        back_populates="executions",
        foreign_keys=[scheduled_transfer_id],
    )
