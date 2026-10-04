"""Admin API routes — KYC review + user management + stats + audit logs.

All routes require admin role (via get_admin_user dependency).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_admin_user, get_db
from app.models.audit_log import AuditLog
from app.models.user import KycStatus, UserRole, User
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.user_repo import UserRepository
from app.schemas.admin import (
    AdminStatsOut,
    AdminUserListOut,
    AdminUserOut,
    KycApproveRequest,
    KycRejectRequest,
)
from app.schemas.audit import AuditLogListResponse, AuditLogOut
from app.services.admin_service import AdminService
from app.services.email_service import EmailService
from app.services.totp_service import TotpService
from app.services.webhook_service import WebhookEvents, WebhookService

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


@router.post("/users/{user_id}/disable-2fa", response_model=AdminUserOut)
def admin_disable_2fa(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Admin force-disables 2FA on a user (e.g. user lost their authenticator).

    All TOTP data (secret, backup codes, enabled flag) is cleared.
    """
    admin_service = AdminService(db)
    target = admin_service.get_user(user_id)
    TotpService(db).admin_disable(admin, target)
    db.refresh(target)
    return target


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
    background_tasks: BackgroundTasks,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    service = AdminService(db)
    target = service.approve_kyc(admin, user_id, notes=payload.notes)
    EmailService(db, background_tasks=background_tasks).send_kyc_approved(
        target, reviewed_by=admin.full_name,
    )
    WebhookService(db, background_tasks=background_tasks).dispatch(
        WebhookEvents.KYC_APPROVED,
        user_id=target.id,
        data={
            "user_id": target.id,
            "account_number": target.account_number,
            "reviewed_by": admin.full_name,
            "reviewed_at": target.kyc_reviewed_at.isoformat() if target.kyc_reviewed_at else None,
        },
    )
    return target


@router.post("/kyc/{user_id}/reject", response_model=AdminUserOut)
def reject_kyc(
    user_id: int,
    payload: KycRejectRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    service = AdminService(db)
    target = service.reject_kyc(admin, user_id, reason=payload.reason)
    EmailService(db, background_tasks=background_tasks).send_kyc_rejected(
        target, reason=payload.reason, reviewed_by=admin.full_name,
    )
    WebhookService(db, background_tasks=background_tasks).dispatch(
        WebhookEvents.KYC_REJECTED,
        user_id=target.id,
        data={
            "user_id": target.id,
            "account_number": target.account_number,
            "reason": payload.reason,
            "reviewed_by": admin.full_name,
            "reviewed_at": target.kyc_reviewed_at.isoformat() if target.kyc_reviewed_at else None,
        },
    )
    return target


# ── Audit log viewer ──────────────────────────────────────────────
@router.get("/audit-logs", response_model=AuditLogListResponse)
def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None, max_length=100),
    search: Optional[str] = Query(None, max_length=200),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    """Paginated audit log query with filters. Newest first.

    Filters:
      - user_id:    restrict to a single user
      - action:     substring match (e.g. "login" matches login_success, login_failed, etc.)
      - search:     free-text across details / action / ip_address / request_id
      - start_date / end_date: ISO datetime range
    """
    repo = AuditLogRepository(db)
    items = repo.list_filtered(
        skip=skip, limit=limit,
        user_id=user_id, action=action, search=search,
        start_date=start_date, end_date=end_date,
    )
    total = repo.count_filtered(
        user_id=user_id, action=action, search=search,
        start_date=start_date, end_date=end_date,
    )

    # Pre-load user info for each unique user_id so we can show email + name
    user_ids = {item.user_id for item in items if item.user_id is not None}
    users_map: dict[int, User] = {}
    if user_ids:
        for u in db.query(User).filter(User.id.in_(user_ids)).all():
            users_map[u.id] = u

    out_items = []
    for log in items:
        u = users_map.get(log.user_id) if log.user_id else None
        out_items.append(AuditLogOut(
            id=log.id,
            user_id=log.user_id,
            user_email=u.email if u else None,
            user_full_name=u.full_name if u else None,
            action=log.action,
            details=log.details,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            request_id=log.request_id,
            created_at=log.created_at,
        ))

    return AuditLogListResponse(
        items=out_items, total=total, skip=skip, limit=limit
    )


@router.get("/audit-logs/actions", response_model=list[str])
def list_audit_actions(db: Session = Depends(get_db)):
    """Distinct action names — used to populate the filter dropdown in the UI."""
    from sqlalchemy import distinct, func
    rows = db.query(distinct(AuditLog.action)).order_by(AuditLog.action.asc()).all()
    return [r[0] for r in rows]
