from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    pin: str = Field(..., min_length=4, max_length=4)


class UserLogin(BaseModel):
    email: EmailStr
    pin: str = Field(..., min_length=4, max_length=4)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_number: str
    full_name: str
    email: str
    balance: float


class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0)
    memo: str | None = None


class TransferRequest(BaseModel):
    recipient_account_number: str
    amount: float = Field(..., gt=0)
    memo: str | None = None


class TransactionRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    amount: float
    memo: str | None = None
    status: str
    created_at: datetime
    direction: str
    counterparty_name: str | None = None
    counterparty_account_number: str | None = None
