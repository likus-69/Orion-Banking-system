"""Notifications API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.notification_repo import NotificationRepository

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[dict])
def list_notifications(
    unread_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = NotificationRepository(db)
    items = repo.list_for_user(current_user.id, unread_only=unread_only)
    return [
        {
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "level": n.level,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat(),
        }
        for n in items
    ]


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = NotificationRepository(db)
    repo.mark_read(notification_id, current_user.id)
    db.commit()
    return None


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = NotificationRepository(db)
    repo.mark_all_read(current_user.id)
    db.commit()
    return None
