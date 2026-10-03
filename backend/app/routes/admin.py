"""Admin API routes — KYC review + user management + stats.

All routes require admin role (via get_admin_user dependency).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_admin_user, get_db
from app.models.user import KycStatus, UserRole, User
from app.schemas.admin import (
    AdminStatsOut,
    AdminUserListOut,
    AdminUserOut,
    KycApproveRequest,
    KycRejectRequest,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_admin_user)])


@router.get("/stats", response_model=AdminStatsOut)
def get_stats(db: Session = Depends(get_db)):
    service = AdminService(db)
    return service.stats()


@router.get("/users", response_model=list[AdminUserListOut])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    role: UserRole | None = Query(None),
    search: str | None = Query(None, max_length=100),
    db: Session = Depends(get_db),
):
    service = AdminService(db)
    items, _ = service.list_users(skip=skip, limit=limit, role=role, search=search)
    return items


@router.get("/users/{user_id}", response_model=AdminUserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    service = AdminService(db)
    return service.get_user(user_id)


@router.post("/users/{user_id}/lock", response_model=AdminUserOut)
def lock_user(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    service = AdminService(db)
    return service.lock_account(admin, user_id)


@router.post("/users/{user_id}/unlock", response_model=AdminUserOut)
def unlock_user(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    service = AdminService(db)
    return service.unlock_account(admin, user_id)


# ── KYC review ────────────────────────────────────────────────────
@router.get("/kyc/pending", response_model=list[AdminUserListOut])
def list_pending_kyc(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    service = AdminService(db)
    items, _ = service.list_pending_kyc(skip=skip, limit=limit)
    return items


@router.post("/kyc/{user_id}/approve", response_model=AdminUserOut)
def approve_kyc(
    user_id: int,
    payload: KycApproveRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    service = AdminService(db)
    return service.approve_kyc(admin, user_id, notes=payload.notes)


@router.post("/kyc/{user_id}/reject", response_model=AdminUserOut)
def reject_kyc(
    user_id: int,
    payload: KycRejectRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    service = AdminService(db)
    return service.reject_kyc(admin, user_id, reason=payload.reason)
