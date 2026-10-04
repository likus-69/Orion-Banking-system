"""Accounts API routes — current user info, KYC, profile updates."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.user import (
    KYCUpdateRequest,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    UserOut,
    UserUpdateRequest,
)
from app.services.account_service import AccountService

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("/me", response_model=UserOut)
def get_my_account(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
def update_my_account(
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AccountService(db)
    return service.update_profile(current_user, full_name=payload.full_name)


@router.put("/me/kyc", response_model=UserOut)
def update_kyc(
    payload: KYCUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AccountService(db)
    return service.update_kyc(
        current_user,
        phone=payload.phone,
        address_line=payload.address_line,
        city=payload.city,
        country=payload.country,
        date_of_birth=payload.date_of_birth,
    )


@router.get("/me/notification-prefs", response_model=NotificationPreferences)
def get_notification_prefs(current_user: User = Depends(get_current_user)):
    return NotificationPreferences(
        email_on_deposit=current_user.email_on_deposit,
        email_on_withdrawal=current_user.email_on_withdrawal,
        email_on_transfer_in=current_user.email_on_transfer_in,
        email_on_transfer_out=current_user.email_on_transfer_out,
        email_on_kyc_decision=current_user.email_on_kyc_decision,
    )


@router.put("/me/notification-prefs", response_model=UserOut)
def update_notification_prefs(
    payload: NotificationPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AccountService(db)
    return service.update_notification_preferences(
        current_user,
        email_on_deposit=payload.email_on_deposit,
        email_on_withdrawal=payload.email_on_withdrawal,
        email_on_transfer_in=payload.email_on_transfer_in,
        email_on_transfer_out=payload.email_on_transfer_out,
        email_on_kyc_decision=payload.email_on_kyc_decision,
    )
