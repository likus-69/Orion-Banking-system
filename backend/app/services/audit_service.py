"""Audit service — wraps AuditLogRepository with business semantics."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.repositories.audit_repo import AuditLogRepository


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuditLogRepository(db)

    def log(
        self,
        *,
        user_id: Optional[int],
        action: str,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> None:
        self.repo.add_log(
            user_id=user_id,
            action=action,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
