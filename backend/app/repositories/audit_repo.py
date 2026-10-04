"""Audit log repository."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    model = AuditLog

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self._db = db

    def add_log(
        self,
        *,
        user_id: Optional[int],
        action: str,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> AuditLog:
        log = AuditLog(
            user_id=user_id,
            action=action,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        self._db.add(log)
        self._db.flush()
        return log

    # ── Filtered listing (admin view) ────────────────────────────
    def list_filtered(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[AuditLog]:
        """Paginated audit log query with filters. Newest first."""
        q = self._db.query(AuditLog)
        if user_id is not None:
            q = q.filter(AuditLog.user_id == user_id)
        if action:
            # Substring match on action — e.g. "login" matches login_success, login_failed, etc.
            q = q.filter(AuditLog.action.ilike(f"%{action.lower()}%"))
        if search:
            like = f"%{search.strip().lower()}%"
            q = q.filter(
                or_(
                    AuditLog.details.ilike(like),
                    AuditLog.action.ilike(like),
                    AuditLog.ip_address.ilike(like),
                    AuditLog.request_id.ilike(like),
                )
            )
        if start_date is not None:
            # SQLite returns naive datetimes — strip tzinfo from filter for comparison.
            sd = start_date.replace(tzinfo=None) if start_date.tzinfo is not None else start_date
            q = q.filter(AuditLog.created_at >= sd)
        if end_date is not None:
            ed = end_date.replace(tzinfo=None) if end_date.tzinfo is not None else end_date
            q = q.filter(AuditLog.created_at <= ed)
        return (
            q.order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_filtered(
        self,
        *,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        q = self._db.query(AuditLog)
        if user_id is not None:
            q = q.filter(AuditLog.user_id == user_id)
        if action:
            q = q.filter(AuditLog.action.ilike(f"%{action.lower()}%"))
        if search:
            like = f"%{search.strip().lower()}%"
            q = q.filter(
                or_(
                    AuditLog.details.ilike(like),
                    AuditLog.action.ilike(like),
                    AuditLog.ip_address.ilike(like),
                    AuditLog.request_id.ilike(like),
                )
            )
        if start_date is not None:
            sd = start_date.replace(tzinfo=None) if start_date.tzinfo is not None else start_date
            q = q.filter(AuditLog.created_at >= sd)
        if end_date is not None:
            ed = end_date.replace(tzinfo=None) if end_date.tzinfo is not None else end_date
            q = q.filter(AuditLog.created_at <= ed)
        return q.count()
