"""Beneficiary service — saved recipients with validation."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.exceptions import (
    AccountNotFoundError,
    OrionError,
    SelfTransferError,
    ValidationError,
)
from app.logging_config import get_logger
from app.models.beneficiary import Beneficiary, BeneficiaryCategory
from app.models.user import User
from app.repositories.beneficiary_repo import BeneficiaryRepository
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService

log = get_logger(__name__)


# Hard cap on beneficiaries per user — protects against accidental DoS via
# mass creation, and is plenty for personal banking use.
MAX_BENEFICIARIES_PER_USER = 50


class BeneficiaryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = BeneficiaryRepository(db)
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    # ── Create ───────────────────────────────────────────────────
    def create(
        self,
        owner: User,
        *,
        recipient_account_number: str,
        nickname: Optional[str] = None,
        category: BeneficiaryCategory = BeneficiaryCategory.other,
    ) -> Beneficiary:
        # 1. Validate recipient exists
        recipient = self.users.get_by_account_number(recipient_account_number)
        if recipient is None:
            raise AccountNotFoundError("Recipient account not found — verify the number.")

        # 2. Reject self
        if recipient.id == owner.id:
            raise SelfTransferError("You cannot add yourself as a beneficiary.")

        # 3. Reject duplicates (same owner + recipient)
        existing = self.repo.get_by_account(owner.id, recipient_account_number)
        if existing is not None:
            raise ValidationError(
                f"You've already saved this recipient as '{existing.nickname or existing.recipient_name}'.",
                error_code="beneficiary_already_exists",
            )

        # 4. Enforce per-user cap
        count = self.repo.count_for_user(owner.id)
        if count >= MAX_BENEFICIARIES_PER_USER:
            raise ValidationError(
                f"You've reached the maximum of {MAX_BENEFICIARIES_PER_USER} beneficiaries. "
                "Delete one before adding another.",
                error_code="beneficiary_limit_reached",
            )

        b = Beneficiary(
            owner_user_id=owner.id,
            recipient_account_number=recipient_account_number,
            recipient_name=recipient.full_name,
            nickname=nickname.strip()[:100] if nickname else None,
            category=category,
        )
        self.db.add(b)
        self.db.flush()
        self.audit.log(
            user_id=owner.id,
            action="beneficiary_created",
            details=f"Saved beneficiary '{b.nickname or b.recipient_name}' "
                    f"(account {b.recipient_account_number})",
        )
        self.db.commit()
        self.db.refresh(b)
        log.info("beneficiary.created", beneficiary_id=b.id, owner_id=owner.id)
        return b

    # ── Read ─────────────────────────────────────────────────────
    def list_for_user(self, owner_user_id: int) -> list[Beneficiary]:
        return self.repo.list_for_user(owner_user_id)

    def get_for_user(self, owner_user_id: int, beneficiary_id: int) -> Optional[Beneficiary]:
        return self.repo.get_for_user(owner_user_id, beneficiary_id)

    def search(self, owner_user_id: int, query: str) -> list[Beneficiary]:
        if not query or len(query.strip()) < 1:
            return self.repo.list_for_user(owner_user_id)[:10]
        return self.repo.search(owner_user_id, query.strip(), limit=10)

    # ── Update ────────────────────────────────────────────────────
    def update(
        self,
        owner_user_id: int,
        beneficiary_id: int,
        *,
        nickname: Optional[str] = None,
        category: Optional[BeneficiaryCategory] = None,
    ) -> Optional[Beneficiary]:
        b = self.repo.get_for_user(owner_user_id, beneficiary_id)
        if b is None:
            return None
        if nickname is not None:
            b.nickname = nickname.strip()[:100] if nickname.strip() else None
        if category is not None:
            b.category = category
        self.audit.log(
            user_id=owner_user_id,
            action="beneficiary_updated",
            details=f"Updated beneficiary id={beneficiary_id}",
        )
        self.db.commit()
        self.db.refresh(b)
        return b

    # ── Delete ───────────────────────────────────────────────────
    def delete(self, owner_user_id: int, beneficiary_id: int) -> bool:
        b = self.repo.get_for_user(owner_user_id, beneficiary_id)
        if b is None:
            return False
        self.audit.log(
            user_id=owner_user_id,
            action="beneficiary_deleted",
            details=f"Deleted beneficiary '{b.nickname or b.recipient_name}' (id={beneficiary_id})",
        )
        self.db.delete(b)
        self.db.commit()
        return True

    # ── Auto-save after transfer ─────────────────────────────────
    def maybe_save_after_transfer(
        self,
        owner: User,
        *,
        recipient_account_number: str,
    ) -> Optional[Beneficiary]:
        """Called after a successful transfer — saves the recipient if not already saved.

        Returns the Beneficiary if created, None if already existed or skipped.
        """
        existing = self.repo.get_by_account(owner.id, recipient_account_number)
        if existing is not None:
            return None
        try:
            return self.create(
                owner,
                recipient_account_number=recipient_account_number,
                category=BeneficiaryCategory.other,
            )
        except OrionError:
            # Swallow — this is opportunistic, not user-initiated.
            return None
