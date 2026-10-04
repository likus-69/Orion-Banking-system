"""Notification repository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    model = Notification

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self._db = db

    def list_for_user(self, user_id: int, *, unread_only: bool = False) -> list[Notification]:
        q = self._db.query(Notification).filter(Notification.user_id == user_id)
        if unread_only:
            q = q.filter(Notification.is_read == False)  # noqa: E712
        return q.order_by(Notification.created_at.desc()).limit(50).all()

    def mark_read(self, notification_id: int, user_id: int) -> bool:
        n = (
            self._db.query(Notification)
            .filter(Notification.id == notification_id, Notification.user_id == user_id)
            .first()
        )
        if n is None:
            return False
        n.is_read = True
        self._db.flush()
        return True

    def mark_all_read(self, user_id: int) -> int:
        result = (
            self._db.query(Notification)
            .filter(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
            .update({Notification.is_read: True})
        )
        return int(result)
