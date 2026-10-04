"""Beneficiary API routes — CRUD + search/suggest + opportunistic save."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.exceptions import OrionError
from app.models.beneficiary import BeneficiaryCategory
from app.models.user import User
from app.schemas.beneficiary import (
    BeneficiaryCreateRequest,
    BeneficiaryOut,
    BeneficiarySaveFromTransferRequest,
    BeneficiarySearchOut,
    BeneficiaryUpdateRequest,
)
from app.services.beneficiary_service import BeneficiaryService

router = APIRouter(prefix="/api/beneficiaries", tags=["beneficiaries"])


@router.get("", response_model=list[BeneficiaryOut])
def list_my_beneficiaries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = BeneficiaryService(db)
    return service.list_for_user(current_user.id)


@router.post("", response_model=BeneficiaryOut, status_code=status.HTTP_201_CREATED)
def create_beneficiary(
    payload: BeneficiaryCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = BeneficiaryService(db)
    try:
        return service.create(
            current_user,
            recipient_account_number=payload.recipient_account_number,
            nickname=payload.nickname,
            category=payload.category,
        )
    except OrionError as exc:
        raise HTTPException(status_code=exc.status_code, detail={
            "error": {"code": exc.error_code, "message": exc.message}
        })


@router.get("/search", response_model=list[BeneficiarySearchOut])
def search_beneficiaries(
    q: str = Query("", max_length=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Typeahead search — used by the transfer + scheduled-transfer forms."""
    service = BeneficiaryService(db)
    return service.search(current_user.id, q)


@router.get("/{beneficiary_id}", response_model=BeneficiaryOut)
def get_beneficiary(
    beneficiary_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = BeneficiaryService(db)
    b = service.get_for_user(current_user.id, beneficiary_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    return b


@router.patch("/{beneficiary_id}", response_model=BeneficiaryOut)
def update_beneficiary(
    beneficiary_id: int,
    payload: BeneficiaryUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = BeneficiaryService(db)
    b = service.update(
        current_user.id,
        beneficiary_id,
        nickname=payload.nickname,
        category=payload.category,
    )
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    return b


@router.delete("/{beneficiary_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_beneficiary(
    beneficiary_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = BeneficiaryService(db)
    if not service.delete(current_user.id, beneficiary_id):
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    return None


@router.post("/save-from-transfer", response_model=BeneficiaryOut)
def save_from_transfer(
    payload: BeneficiarySaveFromTransferRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Opportunistic save — called from the UI after a successful transfer.

    If the recipient is already saved, returns the existing beneficiary (200).
    Otherwise creates a new one (200, not 201 — caller shouldn't care).
    """
    service = BeneficiaryService(db)
    existing = service.repo.get_by_account(current_user.id, payload.recipient_account_number)
    if existing is not None:
        return existing
    try:
        return service.create(
            current_user,
            recipient_account_number=payload.recipient_account_number,
            nickname=payload.nickname,
            category=BeneficiaryCategory.other,
        )
    except OrionError as exc:
        raise HTTPException(status_code=exc.status_code, detail={
            "error": {"code": exc.error_code, "message": exc.message}
        })
