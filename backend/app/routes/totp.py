"""2FA / TOTP API routes — setup, verify, disable, regenerate backup codes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import (
    TotpDisableRequest,
    TotpRegenerateBackupRequest,
    TotpRegenerateBackupResponse,
    TotpSetupResponse,
    TotpStatusResponse,
    TotpVerifySetupRequest,
    TotpVerifySetupResponse,
)
from app.services.totp_service import TotpService

router = APIRouter(prefix="/api/2fa", tags=["2fa"])


@router.get("/status", response_model=TotpStatusResponse)
def get_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Count backup codes remaining
    backup_remaining = 0
    if current_user.totp_backup_codes_hashed:
        backup_remaining = len([
            c for c in current_user.totp_backup_codes_hashed.split(",")
            if c.strip()
        ])
    return TotpStatusResponse(
        enabled=current_user.totp_enabled,
        setup_at=current_user.totp_setup_at.isoformat() if current_user.totp_setup_at else None,
        backup_codes_remaining=backup_remaining,
    )


@router.post("/setup", response_model=TotpSetupResponse)
def begin_setup(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Step 1: generate a TOTP secret + QR code. User must call /verify
    with a valid 6-digit code from their authenticator app to enable 2FA."""
    service = TotpService(db)
    return service.begin_setup(current_user)


@router.post("/verify", response_model=TotpVerifySetupResponse)
def complete_setup(
    payload: TotpVerifySetupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Step 2: verify the first TOTP code and enable 2FA. Returns 10 backup codes
    — these are shown ONCE and must be saved by the user."""
    service = TotpService(db)
    return service.complete_setup(current_user, code=payload.code)


@router.post("/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable(
    payload: TotpDisableRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disable 2FA — requires either a current TOTP code or a backup code."""
    service = TotpService(db)
    service.disable(current_user, code=payload.code, backup_code=payload.backup_code)
    return None


@router.post("/regenerate-backup-codes", response_model=TotpRegenerateBackupResponse)
def regenerate_backup_codes(
    payload: TotpRegenerateBackupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a fresh set of 10 backup codes (invalidates the old ones).
    Requires either a current TOTP code or a backup code."""
    service = TotpService(db)
    return service.regenerate_backup_codes(
        current_user, code=payload.code, backup_code=payload.backup_code
    )
