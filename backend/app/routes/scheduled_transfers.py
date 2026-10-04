"""Scheduled transfer API routes — CRUD + pause/resume/cancel + execution history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.scheduled_transfer import ScheduleStatus
from app.models.user import User
from app.schemas.scheduled_transfer import (
    ScheduledTransferCreateRequest,
    ScheduledTransferExecutionOut,
    ScheduledTransferOut,
    ScheduledTransferUpdateRequest,
)
from app.services.scheduled_transfer_service import ScheduledTransferService

router = APIRouter(prefix="/api/scheduled-transfers", tags=["scheduled-transfers"])


@router.get("", response_model=list[ScheduledTransferOut])
def list_my_schedules(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ScheduledTransferService(db)
    return service.list_for_user(current_user.id)


@router.post("", response_model=ScheduledTransferOut,
             status_code=status.HTTP_201_CREATED)
def create_schedule(
    payload: ScheduledTransferCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ScheduledTransferService(db)
    return service.create(
        current_user,
        name=payload.name,
        recipient_account_number=payload.recipient_account_number,
        amount=payload.amount,
        memo=payload.memo,
        schedule_type=payload.schedule_type,
        schedule_config=payload.schedule_config,
    )


@router.get("/{schedule_id}", response_model=ScheduledTransferOut)
def get_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ScheduledTransferService(db)
    s = service.get_for_user(current_user.id, schedule_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Scheduled transfer not found")
    return s


@router.patch("/{schedule_id}", response_model=ScheduledTransferOut)
def update_schedule(
    schedule_id: int,
    payload: ScheduledTransferUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ScheduledTransferService(db)
    s = service.get_for_user(current_user.id, schedule_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Scheduled transfer not found")
    if payload.name is not None:
        s.name = payload.name.strip()[:255]
    if payload.memo is not None:
        s.memo = payload.memo
    if payload.amount is not None:
        s.amount = payload.amount
    db.commit()
    db.refresh(s)
    return s


@router.post("/{schedule_id}/pause", response_model=ScheduledTransferOut)
def pause_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ScheduledTransferService(db)
    s = service.pause(current_user.id, schedule_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Scheduled transfer not found")
    return s


@router.post("/{schedule_id}/resume", response_model=ScheduledTransferOut)
def resume_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ScheduledTransferService(db)
    try:
        s = service.resume(current_user.id, schedule_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if s is None:
        raise HTTPException(status_code=404, detail="Scheduled transfer not found")
    return s


@router.post("/{schedule_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ScheduledTransferService(db)
    if not service.cancel(current_user.id, schedule_id):
        raise HTTPException(status_code=404, detail="Scheduled transfer not found")
    return None


@router.get("/{schedule_id}/executions",
            response_model=list[ScheduledTransferExecutionOut])
def list_executions(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ScheduledTransferService(db)
    items = service.list_executions(current_user.id, schedule_id)
    if items is None:
        raise HTTPException(status_code=404, detail="Scheduled transfer not found")
    return items
