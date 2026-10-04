"""Beneficiary schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.beneficiary import BeneficiaryCategory


class BeneficiaryCreateRequest(BaseModel):
    recipient_account_number: str = Field(..., min_length=14, max_length=14)
    nickname: Optional[str] = Field(None, max_length=100)
    category: BeneficiaryCategory = BeneficiaryCategory.other


class BeneficiaryUpdateRequest(BaseModel):
    nickname: Optional[str] = Field(None, max_length=100)
    category: Optional[BeneficiaryCategory] = None


class BeneficiaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_user_id: int
    recipient_account_number: str
    recipient_name: str
    nickname: Optional[str] = None
    category: BeneficiaryCategory
    created_at: datetime
    updated_at: datetime


class BeneficiarySearchOut(BaseModel):
    """Lighter shape for the typeahead dropdown."""

    id: int
    recipient_account_number: str
    recipient_name: str
    nickname: Optional[str] = None
    category: BeneficiaryCategory


class BeneficiarySaveFromTransferRequest(BaseModel):
    """Body for POST /api/beneficiaries/save-from-transfer — opportunistic save."""

    recipient_account_number: str = Field(..., min_length=14, max_length=14)
    nickname: Optional[str] = Field(None, max_length=100)
