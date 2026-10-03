"""Transaction repository — data access for Transaction model."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.repositories.base import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    model = Transaction

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self._db = db

    def get_by_reference(self, reference: str) -> Optional[Transaction]:
        return (
            self._db.query(Transaction)
            .filter(Transaction.reference == reference)
            .first()
        )

    def get_by_idempotency_key(self, key: str) -> Optional[Transaction]:
        return (
            self._db.query(Transaction)
            .filter(Transaction.idempotency_key == key)
            .first()
        )

    def list_for_user(
        self,
        user_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[Transaction]:
        q = self._db.query(Transaction).filter(
            or_(
                Transaction.from_account_id == user_id,
                Transaction.to_account_id == user_id,
            )
        )
        if start_date is not None:
            q = q.filter(Transaction.created_at >= start_date)
        if end_date is not None:
            q = q.filter(Transaction.created_at <= end_date)
        return (
            q.order_by(Transaction.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
