"""Scheduled transfer service — create, pause/resume/cancel, execute.

Execution reuses TransactionService.transfer() for atomicity + idempotency.
The scheduler (started in main.py lifespan) calls run_due() every 60s.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.exceptions import (
    AccountNotFoundError,
    InsufficientFundsError,
    InvalidAmountError,
    SelfTransferError,
    ValidationError,
)
from app.logging_config import get_logger
from app.models.scheduled_transfer import (
    ExecutionStatus,
    ScheduledTransfer,
    ScheduledTransferExecution,
    ScheduleStatus,
    ScheduleType,
)
from app.models.user import User
from app.repositories.scheduled_transfer_repo import ScheduledTransferRepository
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService

log = get_logger(__name__)


# Maximum consecutive failures before a schedule is auto-paused
MAX_CONSECUTIVE_FAILURES = 3


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _compute_next_run(
    schedule_type: ScheduleType,
    schedule_config: str,
    *,
    from_time: datetime,
) -> datetime:
    """Compute the next run time based on the schedule type + config.

    - 'once': schedule_config is an ISO datetime — return it (single execution)
    - 'daily': schedule_config is an int N — return from_time + N days (rounded to midnight)
    - 'weekly': schedule_config is a day-of-week 0-6 (0=Mon)
    - 'monthly': schedule_config is a day-of-month 1-28
    """
    if schedule_type == ScheduleType.once:
        # Parse the ISO datetime
        dt = datetime.fromisoformat(schedule_config.replace("Z", "+00:00"))
        return dt

    if schedule_type == ScheduleType.daily:
        try:
            days = int(schedule_config)
        except ValueError:
            days = 1
        return (from_time + timedelta(days=days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if schedule_type == ScheduleType.weekly:
        try:
            target_dow = int(schedule_config)
        except ValueError:
            target_dow = 0
        # 0=Monday in Python's weekday()
        current_dow = from_time.weekday()
        days_ahead = (target_dow - current_dow) % 7
        if days_ahead == 0:
            days_ahead = 7  # always next week, not today
        return (from_time + timedelta(days=days_ahead)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if schedule_type == ScheduleType.monthly:
        try:
            target_day = int(schedule_config)
        except ValueError:
            target_day = 1
        target_day = max(1, min(28, target_day))  # cap at 28 to avoid month-length issues
        # Compute next month + target day
        if from_time.day >= target_day:
            # Move to next month
            if from_time.month == 12:
                next_month = from_time.replace(year=from_time.year + 1, month=1, day=target_day)
            else:
                next_month = from_time.replace(month=from_time.month + 1, day=target_day)
        else:
            next_month = from_time.replace(day=target_day)
        return next_month.replace(hour=0, minute=0, second=0, microsecond=0)

    raise ValidationError(f"Unknown schedule type: {schedule_type}")


class ScheduledTransferService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ScheduledTransferRepository(db)
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    # ── Create ───────────────────────────────────────────────────
    def create(
        self,
        user: User,
        *,
        name: str,
        recipient_account_number: str,
        amount: float,
        memo: Optional[str] = None,
        schedule_type: ScheduleType,
        schedule_config: str,
    ) -> ScheduledTransfer:
        # Validate recipient exists + not self
        recipient = self.users.get_by_account_number(recipient_account_number)
        if recipient is None:
            raise AccountNotFoundError()
        if recipient.id == user.id:
            raise SelfTransferError()
        if amount <= 0:
            raise InvalidAmountError()

        # Validate schedule_config for the type
        if schedule_type == ScheduleType.once:
            try:
                start_at = datetime.fromisoformat(schedule_config.replace("Z", "+00:00"))
            except ValueError:
                raise ValidationError("schedule_config for 'once' must be an ISO datetime")
            if start_at <= _now_utc():
                raise ValidationError("Start time must be in the future")
            next_run = start_at
        else:
            next_run = _compute_next_run(
                schedule_type, schedule_config, from_time=_now_utc()
            )

        s = ScheduledTransfer(
            user_id=user.id,
            name=name.strip()[:255],
            recipient_account_number=recipient_account_number,
            amount=amount,
            memo=memo,
            schedule_type=schedule_type,
            schedule_config=schedule_config,
            next_run_at=next_run,
            status=ScheduleStatus.active,
            consecutive_failures=0,
        )
        self.db.add(s)
        self.db.flush()

        self.audit.log(
            user_id=user.id,
            action="scheduled_transfer_created",
            details=f"Created schedule '{s.name}' (id={s.id}) → {recipient_account_number} (${amount}, {schedule_type.value})",
        )
        self.db.commit()
        self.db.refresh(s)
        log.info(
            "scheduled_transfer.created",
            schedule_id=s.id,
            user_id=user.id,
            type=schedule_type.value,
            next_run=str(next_run),
        )
        return s

    # ── Read ─────────────────────────────────────────────────────
    def list_for_user(self, user_id: int) -> list[ScheduledTransfer]:
        return self.repo.list_for_user(user_id)

    def get_for_user(self, user_id: int, schedule_id: int) -> Optional[ScheduledTransfer]:
        return self.repo.get_for_user(user_id, schedule_id)

    def list_executions(self, user_id: int, schedule_id: int) -> Optional[list[ScheduledTransferExecution]]:
        s = self.repo.get_for_user(user_id, schedule_id)
        if s is None:
            return None
        return self.repo.list_executions(schedule_id)

    # ── Pause / Resume / Cancel ──────────────────────────────────
    def pause(self, user_id: int, schedule_id: int) -> Optional[ScheduledTransfer]:
        s = self.repo.get_for_user(user_id, schedule_id)
        if s is None:
            return None
        s.status = ScheduleStatus.paused
        self.audit.log(user_id=user_id, action="scheduled_transfer_paused",
                       details=f"Paused schedule id={schedule_id}")
        self.db.commit()
        self.db.refresh(s)
        return s

    def resume(self, user_id: int, schedule_id: int) -> Optional[ScheduledTransfer]:
        s = self.repo.get_for_user(user_id, schedule_id)
        if s is None:
            return None
        # If next_run is in the past, push it forward
        now = _now_utc()
        # SQLite returns naive datetimes — strip tzinfo from `now` for comparison.
        next_run = s.next_run_at
        compare_now = now.replace(tzinfo=None) if next_run.tzinfo is None and now.tzinfo is not None else now
        if next_run <= compare_now:
            if s.schedule_type == ScheduleType.once:
                # Can't resume a past one-time schedule
                raise ValidationError("Cannot resume a one-time schedule whose time has passed")
            s.next_run_at = _compute_next_run(
                s.schedule_type, s.schedule_config, from_time=now
            )
        s.status = ScheduleStatus.active
        s.consecutive_failures = 0
        self.audit.log(user_id=user_id, action="scheduled_transfer_resumed",
                       details=f"Resumed schedule id={schedule_id}")
        self.db.commit()
        self.db.refresh(s)
        return s

    def cancel(self, user_id: int, schedule_id: int) -> bool:
        s = self.repo.get_for_user(user_id, schedule_id)
        if s is None:
            return False
        s.status = ScheduleStatus.cancelled
        self.audit.log(user_id=user_id, action="scheduled_transfer_cancelled",
                       details=f"Cancelled schedule id={schedule_id}")
        self.db.commit()
        return True

    # ── Execution (called by scheduler) ─────────────────────────
    def run_due(self, now: Optional[datetime] = None) -> int:
        """Find + execute all due schedules. Returns count of executions attempted.

        This is the entry point called by the APScheduler job every 60s.
        Uses self.db session throughout — caller is responsible for session
        lifecycle (in production the scheduler opens a fresh SessionLocal
        per call, in tests we use the test's session).
        """
        from app.services.transaction_service import TransactionService

        now = now or _now_utc()
        due = self.repo.list_due(now)
        if not due:
            return 0
        log.info("scheduled_transfer.run_due", count=len(due))

        executed = 0
        for s in due:
            executed += self._execute_one(s)
        return executed

    def _execute_one(self, schedule: ScheduledTransfer) -> int:
        """Execute one scheduled transfer. Returns 1 if attempted, 0 if skipped."""
        from app.services.transaction_service import TransactionService
        from app.services.webhook_service import WebhookEvents, WebhookService

        db = self.db
        try:
            user = self.users.get(schedule.user_id)
            if user is None or user.is_locked:
                # Account gone/locked — skip this run, advance next_run
                self._record_skip(schedule, "Account locked or not found")
                return 0

            tx_service = TransactionService(db)
            try:
                tx = tx_service.transfer(
                    user,
                    recipient_account_number=schedule.recipient_account_number,
                    amount=float(schedule.amount),
                    memo=schedule.memo or f"Scheduled: {schedule.name}",
                    idempotency_key=f"sched-{schedule.id}-{int(schedule.next_run_at.timestamp())}",
                )
                # Success!
                execution = self.repo.create_execution(
                    scheduled_transfer_id=schedule.id,
                    status=ExecutionStatus.success,
                    transaction_id=tx.id,
                    transaction_reference=tx.reference,
                )
                schedule.last_run_at = _now_utc()
                schedule.last_execution_id = execution.id
                schedule.consecutive_failures = 0

                # Schedule next run (or mark completed for one-time)
                if schedule.schedule_type == ScheduleType.once:
                    schedule.status = ScheduleStatus.completed
                    schedule.next_run_at = schedule.last_run_at  # freeze
                else:
                    schedule.next_run_at = _compute_next_run(
                        schedule.schedule_type,
                        schedule.schedule_config,
                        from_time=_now_utc(),
                    )

                self.audit.log(
                    user_id=user.id,
                    action="scheduled_transfer_executed",
                    details=f"Executed schedule '{schedule.name}' (id={schedule.id}) → ref {tx.reference}",
                )
                db.commit()
                log.info(
                    "scheduled_transfer.executed",
                    schedule_id=schedule.id,
                    user_id=user.id,
                    tx_ref=tx.reference,
                )

                # Fire webhook (synchronously — this runs from the scheduler,
                # not a request, so no BackgroundTasks available).
                try:
                    WebhookService(db).dispatch(
                        WebhookEvents.SCHEDULED_TRANSFER_EXECUTED,
                        user_id=user.id,
                        data={
                            "schedule_id": schedule.id,
                            "schedule_name": schedule.name,
                            "transaction_id": tx.id,
                            "transaction_reference": tx.reference,
                            "amount": float(tx.amount),
                            "recipient_account": schedule.recipient_account_number,
                            "executed_at": execution.executed_at.isoformat(),
                        },
                    )
                except Exception as wh_err:
                    log.warning("scheduled_transfer.webhook_failed",
                                schedule_id=schedule.id, error=str(wh_err))
                return 1

            except (InsufficientFundsError, AccountNotFoundError, SelfTransferError,
                    InvalidAmountError, ValidationError) as exc:
                # Expected failure — record + advance next_run
                execution = self.repo.create_execution(
                    scheduled_transfer_id=schedule.id,
                    status=ExecutionStatus.failed,
                    error_message=f"{type(exc).__name__}: {exc.message}",
                )
                schedule.last_run_at = _now_utc()
                schedule.last_execution_id = execution.id
                schedule.consecutive_failures += 1

                if schedule.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    schedule.status = ScheduleStatus.failed
                    self.audit.log(
                        user_id=user.id,
                        action="scheduled_transfer_auto_failed",
                        details=f"Schedule '{schedule.name}' auto-failed after {schedule.consecutive_failures} consecutive failures",
                    )
                    # Fire webhook for failure
                    try:
                        WebhookService(db).dispatch(
                            WebhookEvents.SCHEDULED_TRANSFER_FAILED,
                            user_id=user.id,
                            data={
                                "schedule_id": schedule.id,
                                "schedule_name": schedule.name,
                                "consecutive_failures": schedule.consecutive_failures,
                                "error": str(exc.message),
                            },
                        )
                    except Exception:
                        pass
                else:
                    # Schedule next run anyway
                    if schedule.schedule_type != ScheduleType.once:
                        schedule.next_run_at = _compute_next_run(
                            schedule.schedule_type,
                            schedule.schedule_config,
                            from_time=_now_utc(),
                        )
                    else:
                        schedule.status = ScheduleStatus.failed

                db.commit()
                log.warning(
                    "scheduled_transfer.execution_failed",
                    schedule_id=schedule.id,
                    error=str(exc.message),
                    consecutive_failures=schedule.consecutive_failures,
                )
                return 1

        except Exception as exc:
            log.error("scheduled_transfer.unexpected_error",
                       schedule_id=schedule.id, error=str(exc))
            db.rollback()
            return 0

    def _record_skip(self, schedule: ScheduledTransfer, reason: str) -> None:
        execution = self.repo.create_execution(
            scheduled_transfer_id=schedule.id,
            status=ExecutionStatus.skipped,
            error_message=reason,
        )
        schedule.last_run_at = _now_utc()
        schedule.last_execution_id = execution.id
        # Advance next_run so we don't keep retrying immediately
        if schedule.schedule_type != ScheduleType.once:
            schedule.next_run_at = _compute_next_run(
                schedule.schedule_type,
                schedule.schedule_config,
                from_time=_now_utc(),
            )
        else:
            schedule.status = ScheduleStatus.failed
        self.db.commit()
