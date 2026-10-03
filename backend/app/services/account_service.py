"""Account service — read/update the user's own profile, KYC, balance summary."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.user import KycStatus, User
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService

log = get_logger(__name__)


class AccountService:
    """Operations on the user's own account."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    def get(self, user_id: int) -> User:
        user = self.users.get(user_id)
        if user is None:
            from app.exceptions import UserNotFoundError

            raise UserNotFoundError()
        return user

    def update_profile(self, user: User, *, full_name: Optional[str] = None) -> User:
        if full_name is not None:
            user.full_name = full_name.strip() or user.full_name
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_kyc(
        self,
        user: User,
        *,
        phone: Optional[str] = None,
        address_line: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
        date_of_birth: Optional[datetime] = None,
    ) -> User:
        if phone is not None:
            user.phone = phone
        if address_line is not None:
            user.address_line = address_line
        if city is not None:
            user.city = city
        if country is not None:
            user.country = country
        if date_of_birth is not None:
            user.date_of_birth = date_of_birth
        # If any KYC field was provided, mark KYC as in-review (resets prior rejection).
        if any(v is not None for v in (phone, address_line, city, country, date_of_birth)):
            user.kyc_status = KycStatus.in_review
            user.kyc_rejection_reason = None
            user.kyc_reviewed_by = None
            user.kyc_reviewed_at = None
            self.audit.log(
                user_id=user.id,
                action="kyc_updated",
                details="User submitted KYC information for review",
            )
        self.db.commit()
        self.db.refresh(user)
        return user
