"""Transactions API routes — deposit / withdraw / transfer / history / detail."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, get_request_meta
from app.models.transaction import TransactionCategory, TransactionStatus, TransactionType
from app.models.user import User
from app.schemas.transaction import DepositRequest, TransactionOut, TransferRequest, WithdrawRequest
from app.services.transaction_service import TransactionService


def _serialize(tx, user_id: int) -> TransactionOut:
    direction = "outgoing" if tx.from_account_id == user_id else "incoming"
    counterparty = None
    if tx.from_account_id == user_id:
        counterparty = tx.receiver
    else:
        counterparty = tx.sender

    return TransactionOut(
        id=tx.id,
        reference=tx.reference,
        type=tx.type,
        amount=float(tx.amount),
        memo=tx.memo,
        category=tx.category,
        status=tx.status,
        created_at=tx.created_at,
        direction=direction,
        counterparty_name=counterparty.full_name if counterparty else None,
        counterparty_account_number=counterparty.account_number if counterparty else None,
    )


router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.post("/deposit", response_model=TransactionOut)
def deposit(
    payload: DepositRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meta = get_request_meta(request)
    service = TransactionService(db)
    tx = service.deposit(current_user, payload.amount, memo=payload.memo, **meta)
    return _serialize(tx, current_user.id)


@router.post("/withdraw", response_model=TransactionOut)
def withdraw(
    payload: WithdrawRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meta = get_request_meta(request)
    service = TransactionService(db)
    tx = service.withdraw(current_user, payload.amount, memo=payload.memo, **meta)
    return _serialize(tx, current_user.id)


@router.post("/transfer", response_model=TransactionOut)
def transfer(
    payload: TransferRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meta = get_request_meta(request)
    service = TransactionService(db)
    tx = service.transfer(
        current_user,
        recipient_account_number=payload.recipient_account_number,
        amount=payload.amount,
        memo=payload.memo,
        idempotency_key=payload.idempotency_key,
        **meta,
    )
    return _serialize(tx, current_user.id)


@router.get("", response_model=list[TransactionOut])
def list_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = TransactionService(db)
    items = service.list_history(current_user, skip=skip, limit=limit)
    return [_serialize(t, current_user.id) for t in items]


@router.get("/{tx_id}", response_model=TransactionOut)
def get_transaction(
    tx_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = TransactionService(db)
    tx = service.get_for_user(current_user, tx_id)
    return _serialize(tx, current_user.id)
