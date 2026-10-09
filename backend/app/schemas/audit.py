"""Audit log schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    user_email: Optional[str] = None  # joined for display
    user_full_name: Optional[str] = None
    action: str
    details: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    """Paginated response with total count for the admin UI."""

    items: list[AuditLogOut]
    total: int
    skip: int
    limit: int
