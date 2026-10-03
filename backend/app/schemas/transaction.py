"""Transaction-related schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.transaction import TransactionCategory, TransactionStatus, TransactionType


class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0, le=1_000_000_000)
    memo: Optional[str] = Field(None, max_length=500)


class WithdrawRequest(DepositRequest):
    pass


class TransferRequest(BaseModel):
    recipient_account_number: str = Field(..., min_length=14, max_length=14)
    amount: float = Field(..., gt=0, le=1_000_000_000)
    memo: Optional[str] = Field(None, max_length=500)
    idempotency_key: Optional[str] = Field(None, min_length=8, max_length=64)


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    type: TransactionType
    amount: float
    memo: Optional[str] = None
    category: TransactionCategory
    status: TransactionStatus
    created_at: datetime
    direction: str  # "incoming" | "outgoing"
    counterparty_name: Optional[str] = None
    counterparty_account_number: Optional[str] = None


class StatementRequest(BaseModel):
    """Body for POST /statements/export — date range for PDF."""

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
