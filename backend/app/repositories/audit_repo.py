"""Audit log repository."""
from __future__ import annotations

from typing import Optional

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
