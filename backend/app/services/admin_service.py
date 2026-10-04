"""Admin service — KYC review + user management operations.

All admin actions are audit-logged and (where relevant) trigger user notifications.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.exceptions import AuthorizationError, OrionError, UserNotFoundError, ValidationError
from app.logging_config import get_logger
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.transaction import Transaction
from app.models.user import KycStatus, User, UserRole
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService

log = get_logger(__name__)


class AdminService:
    """Operations an admin (or support-tier) user can perform."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    # ── Stats ─────────────────────────────────────────────────────
    def stats(self) -> dict:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        # SQLite returns naive datetimes — strip tzinfo for comparison.
        if today_start.tzinfo is not None:
            today_naive = today_start.replace(tzinfo=None)
        else:
            today_naive = today_start

        total_users = self.db.query(func.count(User.id)).filter(User.role == UserRole.customer).scalar() or 0
        total_admins = self.db.query(func.count(User.id)).filter(User.role == UserRole.admin).scalar() or 0
        pending_kyc = self.db.query(func.count(User.id)).filter(
            User.kyc_status == KycStatus.in_review
        ).scalar() or 0
        verified_kyc = self.db.query(func.count(User.id)).filter(
            User.kyc_status == KycStatus.verified
        ).scalar() or 0
        rejected_kyc = self.db.query(func.count(User.id)).filter(
            User.kyc_status == KycStatus.rejected
        ).scalar() or 0
        locked_accounts = self.db.query(func.count(User.id)).filter(
            User.is_locked == True  # noqa: E712
        ).scalar() or 0
        total_balance = float(
            self.db.query(func.sum(User.balance)).filter(User.role == UserRole.customer).scalar() or 0
        )
        tx_today = self.db.query(func.count(Transaction.id)).filter(
            Transaction.created_at >= today_naive
        ).scalar() or 0

        return {
            "total_users": total_users,
            "total_admins": total_admins,
            "pending_kyc": pending_kyc,
            "verified_kyc": verified_kyc,
            "rejected_kyc": rejected_kyc,
            "locked_accounts": locked_accounts,
            "total_balance": total_balance,
            "transactions_today": tx_today,
        }

    # ── User listing ──────────────────────────────────────────────
    def list_users(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        role: Optional[UserRole] = None,
        search: Optional[str] = None,
    ) -> tuple[list[User], int]:
        users = self.users.list_users(skip=skip, limit=limit, role=role, search=search)
        total = self.users.count_users(role=role, search=search)
        return users, total

    def get_user(self, user_id: int) -> User:
        u = self.users.get(user_id)
        if u is None:
            raise UserNotFoundError()
        return u

    # ── KYC review ────────────────────────────────────────────────
    def list_pending_kyc(self, *, skip: int = 0, limit: int = 50) -> tuple[list[User], int]:
        """List users with kyc_status == in_review, oldest-first."""
        from sqlalchemy import select

        q = self.db.query(User).filter(User.kyc_status == KycStatus.in_review)
        total = q.count()
        items = q.order_by(User.updated_at.asc()).offset(skip).limit(limit).all()
        return items, total

    def approve_kyc(
        self,
        admin: User,
        target_user_id: int,
        *,
        notes: Optional[str] = None,
    ) -> User:
        target = self.get_user(target_user_id)
        if target.role != UserRole.customer:
            raise ValidationError(
                "Cannot approve KYC for non-customer accounts.",
                error_code="invalid_kyc_target",
            )

        target.kyc_status = KycStatus.verified
        target.kyc_rejection_reason = None
        target.kyc_reviewed_by = admin.id
        target.kyc_reviewed_at = datetime.now(timezone.utc)

        self.audit.log(
            user_id=admin.id,
            action="kyc_approve",
            details=f"Admin approved KYC for user_id={target.id} (account {target.account_number})"
            + (f". Notes: {notes}" if notes else ""),
        )
        # Notify the customer
        self.db.add(
            Notification(
                user_id=target.id,
                title="KYC verified",
                body="Your identity has been verified. Thank you!",
                level="success",
                is_read=False,
            )
        )
        self.db.commit()
        self.db.refresh(target)
        log.info("admin.kyc_approve", admin_id=admin.id, target_user_id=target.id)
        return target

    def reject_kyc(
        self,
        admin: User,
        target_user_id: int,
        *,
        reason: str,
    ) -> User:
        target = self.get_user(target_user_id)
        if target.role != UserRole.customer:
            raise ValidationError(
                "Cannot reject KYC for non-customer accounts.",
                error_code="invalid_kyc_target",
            )

        target.kyc_status = KycStatus.rejected
        target.kyc_rejection_reason = reason.strip()
        target.kyc_reviewed_by = admin.id
        target.kyc_reviewed_at = datetime.now(timezone.utc)

        self.audit.log(
            user_id=admin.id,
            action="kyc_reject",
            details=f"Admin rejected KYC for user_id={target.id}. Reason: {reason}",
        )
        self.db.add(
            Notification(
                user_id=target.id,
                title="KYC needs revision",
                body=f"Your KYC submission was rejected: {reason}. Please update your information and resubmit.",
                level="warn",
                is_read=False,
            )
        )
        self.db.commit()
        self.db.refresh(target)
        log.info("admin.kyc_reject", admin_id=admin.id, target_user_id=target.id)
        return target

    # ── Account lifecycle (lock/unlock) ───────────────────────────
    def lock_account(self, admin: User, target_user_id: int) -> User:
        target = self.get_user(target_user_id)
        if target.role == UserRole.admin:
            raise AuthorizationError("Cannot lock another admin's account.")
        target.is_locked = True
        self.audit.log(
            user_id=admin.id,
            action="admin_lock_account",
            details=f"Admin locked user_id={target.id} (account {target.account_number})",
        )
        self.db.commit()
        self.db.refresh(target)
        return target

    def unlock_account(self, admin: User, target_user_id: int) -> User:
        target = self.get_user(target_user_id)
        target.is_locked = False
        target.failed_login_attempts = 0
        self.audit.log(
            user_id=admin.id,
            action="admin_unlock_account",
            details=f"Admin unlocked user_id={target.id} (account {target.account_number})",
        )
        self.db.commit()
        self.db.refresh(target)
        return target
