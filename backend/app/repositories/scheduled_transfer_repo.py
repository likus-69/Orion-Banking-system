"""Scheduled transfer repository — data access only."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.scheduled_transfer import (
    ScheduledTransfer,
    ScheduledTransferExecution,
    ScheduleStatus,
)


class ScheduledTransferRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Subscriptions ────────────────────────────────────────────
    def list_for_user(self, user_id: int) -> list[ScheduledTransfer]:
        return (
            self.db.query(ScheduledTransfer)
            .filter(ScheduledTransfer.user_id == user_id)
            .order_by(ScheduledTransfer.next_run_at.asc())
            .all()
        )

    def get_for_user(self, user_id: int, schedule_id: int) -> Optional[ScheduledTransfer]:
        return (
            self.db.query(ScheduledTransfer)
            .filter(
                ScheduledTransfer.id == schedule_id,
                ScheduledTransfer.user_id == user_id,
            )
            .first()
        )

    def list_due(self, now: datetime, *, limit: int = 100) -> list[ScheduledTransfer]:
        """All active schedules whose next_run_at <= now."""
        # SQLite returns naive datetimes — strip tzinfo for comparison.
        compare_at = now.replace(tzinfo=None) if now.tzinfo is not None else now
        return (
            self.db.query(ScheduledTransfer)
            .filter(
                ScheduledTransfer.status == ScheduleStatus.active,
                ScheduledTransfer.next_run_at <= compare_at,
            )
            .order_by(ScheduledTransfer.next_run_at.asc())
            .limit(limit)
            .all()
        )

    # ── Executions ──────────────────────────────────────────────
    def create_execution(
        self, *, scheduled_transfer_id: int, status, transaction_id: Optional[int] = None,
        transaction_reference: Optional[str] = None, error_message: Optional[str] = None,
    ) -> ScheduledTransferExecution:
        e = ScheduledTransferExecution(
            scheduled_transfer_id=scheduled_transfer_id,
            transaction_id=transaction_id,
            transaction_reference=transaction_reference,
            status=status,
            error_message=error_message,
        )
        self.db.add(e)
        self.db.flush()
        return e

    def list_executions(self, schedule_id: int, *, limit: int = 50) -> list[ScheduledTransferExecution]:
        return (
            self.db.query(ScheduledTransferExecution)
            .filter(ScheduledTransferExecution.scheduled_transfer_id == schedule_id)
            .order_by(ScheduledTransferExecution.executed_at.desc())
            .limit(limit)
            .all()
        )
