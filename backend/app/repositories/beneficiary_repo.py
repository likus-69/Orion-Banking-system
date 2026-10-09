"""Beneficiary repository — data access only."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.beneficiary import Beneficiary


class BeneficiaryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(self, owner_user_id: int) -> list[Beneficiary]:
        return (
            self.db.query(Beneficiary)
            .filter(Beneficiary.owner_user_id == owner_user_id)
            .order_by(Beneficiary.created_at.desc())
            .all()
        )

    def get_for_user(self, owner_user_id: int, beneficiary_id: int) -> Optional[Beneficiary]:
        return (
            self.db.query(Beneficiary)
            .filter(
                Beneficiary.id == beneficiary_id,
                Beneficiary.owner_user_id == owner_user_id,
            )
            .first()
        )

    def get_by_account(self, owner_user_id: int, recipient_account_number: str) -> Optional[Beneficiary]:
        return (
            self.db.query(Beneficiary)
            .filter(
                Beneficiary.owner_user_id == owner_user_id,
                Beneficiary.recipient_account_number == recipient_account_number,
            )
            .first()
        )

    def count_for_user(self, owner_user_id: int) -> int:
        return (
            self.db.query(Beneficiary)
            .filter(Beneficiary.owner_user_id == owner_user_id)
            .count()
        )

    def search(self, owner_user_id: int, query: str, *, limit: int = 10) -> list[Beneficiary]:
        """Free-text search across nickname + recipient_name + account number."""
        q = f"%{query.strip().lower()}%"
        return (
            self.db.query(Beneficiary)
            .filter(
                Beneficiary.owner_user_id == owner_user_id,
                or_(
                    Beneficiary.recipient_name.ilike(q),
                    Beneficiary.nickname.ilike(q),
                    Beneficiary.recipient_account_number.ilike(q),
                ),
            )
            .order_by(Beneficiary.created_at.desc())
            .limit(limit)
            .all()
        )
