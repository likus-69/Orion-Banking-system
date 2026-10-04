"""Transactions API routes — deposit / withdraw / transfer / history / detail."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, get_request_meta
from app.models.transaction import TransactionCategory, TransactionStatus, TransactionType
from app.models.user import User
from app.schemas.transaction import DepositRequest, TransactionOut, TransferRequest, WithdrawRequest
from app.services.email_service import EmailService
from app.services.transaction_service import TransactionService
from app.services.webhook_service import WebhookEvents, WebhookService


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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meta = get_request_meta(request)
    service = TransactionService(db)
    tx = service.deposit(current_user, payload.amount, memo=payload.memo, **meta)
    EmailService(db, background_tasks=background_tasks).send_deposit_confirmation(
        current_user,
        amount=f"${float(tx.amount):,.2f}",
        reference=tx.reference,
        memo=tx.memo,
        new_balance=f"${float(current_user.balance):,.2f}",
    )
    WebhookService(db, background_tasks=background_tasks).dispatch(
        WebhookEvents.TRANSACTION_DEPOSIT,
        user_id=current_user.id,
        data={
            "transaction_id": tx.id,
            "reference": tx.reference,
            "amount": float(tx.amount),
            "memo": tx.memo,
            "new_balance": float(current_user.balance),
            "created_at": tx.created_at.isoformat(),
        },
    )
    return _serialize(tx, current_user.id)


@router.post("/withdraw", response_model=TransactionOut)
def withdraw(
    payload: WithdrawRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meta = get_request_meta(request)
    service = TransactionService(db)
    tx = service.withdraw(current_user, payload.amount, memo=payload.memo, **meta)
    EmailService(db, background_tasks=background_tasks).send_withdrawal_confirmation(
        current_user,
        amount=f"${float(tx.amount):,.2f}",
        reference=tx.reference,
        memo=tx.memo,
        new_balance=f"${float(current_user.balance):,.2f}",
    )
    WebhookService(db, background_tasks=background_tasks).dispatch(
        WebhookEvents.TRANSACTION_WITHDRAWAL,
        user_id=current_user.id,
        data={
            "transaction_id": tx.id,
            "reference": tx.reference,
            "amount": float(tx.amount),
            "memo": tx.memo,
            "new_balance": float(current_user.balance),
            "created_at": tx.created_at.isoformat(),
        },
    )
    return _serialize(tx, current_user.id)


@router.post("/transfer", response_model=TransactionOut)
def transfer(
    payload: TransferRequest,
    request: Request,
    background_tasks: BackgroundTasks,
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
    recipient = tx.receiver
    EmailService(db, background_tasks=background_tasks).send_transfer_outgoing(
        current_user,
        amount=f"${float(tx.amount):,.2f}",
        reference=tx.reference,
        recipient_name=recipient.full_name,
        recipient_account=recipient.account_number,
        memo=tx.memo,
        new_balance=f"${float(current_user.balance):,.2f}",
    )
    EmailService(db, background_tasks=background_tasks).send_transfer_incoming(
        recipient,
        amount=f"${float(tx.amount):,.2f}",
        reference=tx.reference,
        sender_name=current_user.full_name,
        sender_account=current_user.account_number,
        memo=tx.memo,
        new_balance=f"${float(recipient.balance):,.2f}",
    )
    # Sender webhook
    WebhookService(db, background_tasks=background_tasks).dispatch(
        WebhookEvents.TRANSACTION_TRANSFER_OUT,
        user_id=current_user.id,
        data={
            "transaction_id": tx.id,
            "reference": tx.reference,
            "amount": float(tx.amount),
            "memo": tx.memo,
            "recipient_name": recipient.full_name,
            "recipient_account": recipient.account_number,
            "new_balance": float(current_user.balance),
            "created_at": tx.created_at.isoformat(),
        },
    )
    # Recipient webhook
    WebhookService(db, background_tasks=background_tasks).dispatch(
        WebhookEvents.TRANSACTION_TRANSFER_IN,
        user_id=recipient.id,
        data={
            "transaction_id": tx.id,
            "reference": tx.reference,
            "amount": float(tx.amount),
            "memo": tx.memo,
            "sender_name": current_user.full_name,
            "sender_account": current_user.account_number,
            "new_balance": float(recipient.balance),
            "created_at": tx.created_at.isoformat(),
        },
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
