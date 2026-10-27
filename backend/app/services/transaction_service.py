"""Transaction service — deposit, withdraw, transfer.

All balance mutations are concurrency-safe via SELECT FOR UPDATE row locks
and an explicit DB transaction. Idempotency keys prevent duplicate transfers.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import (
    AccountNotFoundError,
    DailyLimitExceededError,
    InsufficientFundsError,
    InvalidAmountError,
    KycRequiredError,
    SelfTransferError,
    TransactionLimitExceededError,
    TransactionNotFoundError,
)
from app.logging_config import get_logger
from app.models.transaction import Transaction, TransactionCategory, TransactionStatus, TransactionType
from app.models.user import KycStatus, User
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.notification_repo import NotificationRepository
from app.repositories.transaction_repo import TransactionRepository
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService

log = get_logger(__name__)


def _to_decimal(amount: float) -> Decimal:
    """Always use Decimal for money — never float arithmetic."""
    return Decimal(str(amount)).quantize(Decimal("0.01"))


def _generate_reference() -> str:
    """ORX-XXXX-XXXX format transaction reference."""
    p1 = secrets.token_hex(2).upper()
    p2 = secrets.token_hex(2).upper()
    return f"ORX-{p1}-{p2}"


class TransactionService:
    """Atomic money movement operations."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.tx_repo = TransactionRepository(db)
        self.audit = AuditService(db)
        self.notifications = NotificationRepository(db)

    # ── Deposit ───────────────────────────────────────────────────
    def deposit(
        self,
        user: User,
        amount: float,
        *,
        memo: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Transaction:
        if amount <= 0:
            raise InvalidAmountError()
        amt = _to_decimal(amount)

        # ── Transaction limits ───────────────────────────────────
        self._check_limits(user, amount, "deposit")

        # ── KYC requirement ──────────────────────────────────────
        if settings.require_kyc_for_deposit and user.kyc_status != KycStatus.verified:
            raise KycRequiredError()

        # Lock the row for the duration of this transaction.
        locked_user = self.users.get_for_update(user.id)
        if locked_user is None:
            raise AccountNotFoundError("Account not found.")

        new_balance = Decimal(str(locked_user.balance)) + amt
        locked_user.balance = new_balance

        tx = Transaction(
            reference=_generate_reference(),
            from_account_id=None,
            to_account_id=locked_user.id,
            type=TransactionType.deposit,
            amount=amt,
            memo=memo,
            category=TransactionCategory.general,
            status=TransactionStatus.completed,
        )
        self.db.add(tx)
        self.db.flush()

        self.audit.log(
            user_id=locked_user.id,
            action="deposit",
            details=f"Deposited {amt} via API (ref={tx.reference})",
            ip_address=ip_address,
            request_id=request_id,
        )
        self.db.add(self._mk_notification(locked_user.id, "Deposit", f"Deposited {amt}"))
        self.db.commit()
        self.db.refresh(tx)
        log.info("tx.deposit", user_id=locked_user.id, amount=str(amt), ref=tx.reference)
        return tx

    # ── Withdraw ───────────────────────────────────────────────────
    def withdraw(
        self,
        user: User,
        amount: float,
        *,
        memo: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Transaction:
        if amount <= 0:
            raise InvalidAmountError()
        amt = _to_decimal(amount)

        # ── Transaction limits ───────────────────────────────────
        self._check_limits(user, amount, "withdrawal")

        locked_user = self.users.get_for_update(user.id)
        if locked_user is None:
            raise AccountNotFoundError("Account not found.")

        current_balance = Decimal(str(locked_user.balance))
        fee = self._calculate_fee(amt)
        total_deduction = amt + fee
        if total_deduction > current_balance:
            raise InsufficientFundsError(
                f"Insufficient funds (need ${float(total_deduction):.2f} including ${float(fee):.2f} fee, "
                f"balance is ${float(current_balance):.2f})"
            )

        locked_user.balance = current_balance - total_deduction

        tx = Transaction(
            reference=_generate_reference(),
            from_account_id=locked_user.id,
            to_account_id=None,
            type=TransactionType.withdrawal,
            amount=amt,
            memo=memo,
            category=TransactionCategory.general,
            status=TransactionStatus.completed,
        )
        self.db.add(tx)
        self.db.flush()

        self.audit.log(
            user_id=locked_user.id,
            action="withdrawal",
            details=f"Withdrew {amt} via API (ref={tx.reference})",
            ip_address=ip_address,
            request_id=request_id,
        )
        self.db.add(self._mk_notification(locked_user.id, "Withdrawal", f"Withdrew {amt}"))
        self.db.commit()
        self.db.refresh(tx)
        log.info("tx.withdrawal", user_id=locked_user.id, amount=str(amt), ref=tx.reference)
        return tx

    # ── Transfer ───────────────────────────────────────────────────
    def transfer(
        self,
        sender: User,
        *,
        recipient_account_number: str,
        amount: float,
        memo: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Transaction:
        if idempotency_key:
            existing = self.tx_repo.get_by_idempotency_key(idempotency_key)
            if existing:
                log.info("tx.idempotent_replay", key=idempotency_key, ref=existing.reference)
                return existing

        if amount <= 0:
            raise InvalidAmountError()
        amt = _to_decimal(amount)

        # ── Transaction limits ───────────────────────────────────
        self._check_limits(sender, amount, "transfer")

        # Resolve recipient FIRST (before locking sender) to avoid holding two locks too long.
        recipient = self.users.get_by_account_number(recipient_account_number)
        if recipient is None:
            raise AccountNotFoundError()
        if recipient.id == sender.id:
            raise SelfTransferError()
        # Admins can't receive transfers — they're staff, not customers.
        from app.models.user import UserRole
        if recipient.role == UserRole.admin:
            raise AccountNotFoundError("Recipient account not found.")

        # Lock both rows in deterministic order to avoid deadlocks.
        first_id, second_id = sorted([sender.id, recipient.id])
        self.users.get_for_update(first_id)
        self.users.get_for_update(second_id)

        # Re-fetch with current state.
        locked_sender = self.users.get_for_update(sender.id)
        locked_recipient = self.users.get_for_update(recipient.id)
        if locked_sender is None or locked_recipient is None:
            raise AccountNotFoundError("Account disappeared during transfer.")

        sender_balance = Decimal(str(locked_sender.balance))
        fee = self._calculate_fee(amt)
        total_deduction = amt + fee
        if total_deduction > sender_balance:
            raise InsufficientFundsError(
                f"Insufficient funds (need ${float(total_deduction):.2f} including ${float(fee):.2f} fee, "
                f"balance is ${float(sender_balance):.2f})"
            )

        locked_sender.balance = sender_balance - total_deduction
        locked_recipient.balance = Decimal(str(locked_recipient.balance)) + amt

        tx = Transaction(
            reference=_generate_reference(),
            from_account_id=locked_sender.id,
            to_account_id=locked_recipient.id,
            type=TransactionType.transfer,
            amount=amt,
            memo=memo,
            category=TransactionCategory.transfer,
            status=TransactionStatus.completed,
            idempotency_key=idempotency_key,
        )
        self.db.add(tx)
        self.db.flush()

        self.audit.log(
            user_id=locked_sender.id,
            action="transfer_outgoing",
            details=f"Transferred {amt} to {locked_recipient.account_number} (ref={tx.reference})",
            ip_address=ip_address,
            request_id=request_id,
        )
        self.audit.log(
            user_id=locked_recipient.id,
            action="transfer_incoming",
            details=f"Received {amt} from {locked_sender.account_number} (ref={tx.reference})",
            ip_address=ip_address,
            request_id=request_id,
        )
        # Notify recipient
        self.db.add(
            self._mk_notification(
                locked_recipient.id,
                "Incoming transfer",
                f"Received {amt} from {locked_sender.full_name}",
            )
        )
        self.db.commit()
        self.db.refresh(tx)
        log.info(
            "tx.transfer",
            from_id=locked_sender.id,
            to_id=locked_recipient.id,
            amount=str(amt),
            ref=tx.reference,
        )
        return tx

    # ── History ────────────────────────────────────────────────────
    def list_history(
        self,
        user: User,
        *,
        skip: int = 0,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[Transaction]:
        return self.tx_repo.list_for_user(
            user.id,
            skip=skip,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )

    # ── Single transaction detail ─────────────────────────────────
    def get_for_user(self, user: User, tx_id: int) -> Transaction:
        tx = self.tx_repo.get(tx_id)
        if tx is None:
            raise TransactionNotFoundError()
        if tx.from_account_id != user.id and tx.to_account_id != user.id:
            # Don't leak existence — return 404 instead of 403.
            raise TransactionNotFoundError()
        return tx

    # ── Internal helpers ──────────────────────────────────────────
    def _mk_notification(self, user_id: int, title: str, body: str):
        from app.models.notification import Notification

        return Notification(
            user_id=user_id,
            title=title,
            body=body,
            level="info",
            is_read=False,
        )

    def _check_limits(self, user: User, amount: float, tx_type: str) -> None:
        """Check per-transaction + daily cumulative limits.

        Raises TransactionLimitExceededError or DailyLimitExceededError.
        """
        # Per-transaction limit
        if tx_type == "deposit":
            per_tx_limit = settings.max_deposit_per_transaction
            daily_limit = settings.max_daily_deposit
        elif tx_type == "withdrawal":
            per_tx_limit = settings.max_withdrawal_per_transaction
            daily_limit = settings.max_daily_withdrawal
        else:  # transfer
            per_tx_limit = settings.max_transfer_per_transaction
            daily_limit = settings.max_daily_transfer

        if amount > per_tx_limit:
            raise TransactionLimitExceededError(
                f"This {tx_type} of ${amount:,.2f} exceeds the per-transaction limit of ${per_tx_limit:,.2f}."
            )

        # Daily cumulative limit — sum all transactions of this type today
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        if today_start.tzinfo is not None:
            today_start = today_start.replace(tzinfo=None)  # SQLite naive

        tx_type_enum = {
            "deposit": TransactionType.deposit,
            "withdrawal": TransactionType.withdrawal,
            "transfer": TransactionType.transfer,
        }.get(tx_type)

        if tx_type_enum:
            daily_total = (
                self.db.query(Transaction)
                .filter(
                    Transaction.type == tx_type_enum,
                    Transaction.from_account_id == user.id if tx_type != "deposit" else Transaction.to_account_id == user.id,
                    Transaction.created_at >= today_start,
                    Transaction.status == TransactionStatus.completed,
                )
                .with_entities(func.sum(Transaction.amount))
                .scalar()
            ) or 0
            daily_total = float(daily_total)
            if daily_total + amount > daily_limit:
                remaining = max(0, daily_limit - daily_total)
                raise DailyLimitExceededError(
                    f"You have reached your daily {tx_type} limit of ${daily_limit:,.2f}. "
                    f"You've used ${daily_total:,.2f} today; remaining: ${remaining:,.2f}."
                )

    def _calculate_fee(self, amount: Decimal) -> Decimal:
        """Calculate transaction fee based on the configured percentage."""
        if settings.transaction_fee_percent <= 0:
            return Decimal("0")
        fee = (amount * Decimal(str(settings.transaction_fee_percent))).quantize(Decimal("0.01"))
        return fee
