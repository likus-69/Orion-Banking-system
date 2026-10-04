"""Scheduled transfer schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.scheduled_transfer import ExecutionStatus, ScheduleStatus, ScheduleType


class ScheduledTransferCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    recipient_account_number: str = Field(..., min_length=14, max_length=14)
    amount: float = Field(..., gt=0)
    memo: Optional[str] = Field(None, max_length=500)
    schedule_type: ScheduleType
    # For 'once': ISO datetime (UTC)
    # For 'daily': integer as string ("1", "7")
    # For 'weekly': day-of-week 0-6 (0=Mon)
    # For 'monthly': day-of-month 1-28
    schedule_config: str = Field(..., min_length=1, max_length=50)


class ScheduledTransferUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    memo: Optional[str] = Field(None, max_length=500)
    amount: Optional[float] = Field(None, gt=0)


class ScheduledTransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    recipient_account_number: str
    amount: float
    memo: Optional[str] = None
    schedule_type: ScheduleType
    schedule_config: str
    next_run_at: datetime
    last_run_at: Optional[datetime] = None
    consecutive_failures: int
    status: ScheduleStatus
    created_at: datetime
    updated_at: datetime


class ScheduledTransferExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheduled_transfer_id: int
    transaction_id: Optional[int] = None
    transaction_reference: Optional[str] = None
    status: ExecutionStatus
    error_message: Optional[str] = None
    executed_at: datetime
