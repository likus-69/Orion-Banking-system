"""Deposit API routes — mobile money (MTN/Airtel) + webhook callbacks + status polling."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_current_user, get_db
from app.exceptions import OrionError, ValidationError
from app.logging_config import get_logger
from app.models.pending_deposit import PendingDeposit, PendingDepositStatus
from app.models.user import User
from app.services.mobile_money_service import DepositResult, get_deposit_provider
from app.services.transaction_service import TransactionService

log = get_logger(__name__)

router = APIRouter(prefix="/api/deposit", tags=["deposit"])


class InitiateDepositRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=15, description="e.g. +256700000000")
    amount: float = Field(..., gt=0, le=settings.max_deposit_per_transaction)
    memo: str | None = Field(None, max_length=500)


class InitiateDepositResponse(BaseModel):
    status: str
    reference: str
    provider: str
    message: str
    provider_reference: str | None = None


class ManualDepositRequest(BaseModel):
    amount: float = Field(..., gt=0, le=settings.max_deposit_per_transaction)
    memo: str | None = Field(None, max_length=500)


class DepositStatusResponse(BaseModel):
    reference: str
    status: str  # pending | completed | failed | expired
    amount: float
    provider: str
    phone_number: str
    created_at: str
    completed_at: str | None = None
    failure_reason: str | None = None


@router.post("/initiate", response_model=InitiateDepositResponse)
def initiate_mobile_money_deposit(
    payload: InitiateDepositRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initiate a mobile money deposit.

    Sends a payment prompt to the user's phone. Once they approve,
    the provider calls our webhook → we complete the deposit.

    With the stub provider (default), status stays 'pending' and you
    can simulate completion by calling POST /api/deposit/callback/stub.
    """
    import secrets as _secrets

    reference = f"DEP-{_secrets.token_hex(2).upper()}-{_secrets.token_hex(2).upper()}"

    provider = get_deposit_provider()
    result: DepositResult = provider.initiate_deposit(
        phone_number=payload.phone_number,
        amount=payload.amount,
        reference=reference,
        payer_message=payload.memo or f"Orion Banking deposit",
    )

    if result.status == "failed":
        return InitiateDepositResponse(
            status="failed",
            reference=result.reference,
            provider=result.provider,
            message=result.message,
            provider_reference=result.provider_reference,
        )

    # Store the pending deposit
    pending = PendingDeposit(
        user_id=current_user.id,
        reference=reference,
        provider_reference=result.provider_reference,
        provider=result.provider,
        amount=payload.amount,
        phone_number=payload.phone_number,
        memo=payload.memo,
        status=PendingDepositStatus.pending,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(pending)
    db.commit()

    log.info(
        "deposit.initiated",
        user_id=current_user.id,
        reference=reference,
        provider=result.provider,
        amount=payload.amount,
        phone=payload.phone_number,
    )

    return InitiateDepositResponse(
        status=result.status,
        reference=result.reference,
        provider=result.provider,
        message=result.message,
        provider_reference=result.provider_reference,
    )


@router.get("/status/{reference}", response_model=DepositStatusResponse)
def get_deposit_status(
    reference: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check the status of a pending mobile money deposit.

    The frontend polls this every 5s after initiating a deposit.
    """
    pending = (
        db.query(PendingDeposit)
        .filter(
            PendingDeposit.reference == reference,
            PendingDeposit.user_id == current_user.id,
        )
        .first()
    )
    if pending is None:
        raise ValidationError("Deposit not found.")

    return DepositStatusResponse(
        reference=pending.reference,
        status=pending.status.value if hasattr(pending.status, "value") else str(pending.status),
        amount=float(pending.amount),
        provider=pending.provider,
        phone_number=pending.phone_number,
        created_at=pending.created_at.isoformat(),
        completed_at=pending.completed_at.isoformat() if pending.completed_at else None,
        failure_reason=pending.failure_reason,
    )


@router.post("/manual", status_code=status.HTTP_200_OK)
def manual_deposit(
    payload: ManualDepositRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manual deposit (teller / bank transfer).

    Subject to the same limits + KYC checks as mobile money deposits.
    """
    meta = {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }
    service = TransactionService(db)
    tx = service.deposit(current_user, payload.amount, memo=payload.memo, **meta)

    from app.services.email_service import EmailService

    EmailService(db, background_tasks=background_tasks).send_deposit_confirmation(
        current_user,
        amount=f"${float(tx.amount):,.2f}",
        reference=tx.reference,
        memo=tx.memo,
        new_balance=f"${float(current_user.balance):,.2f}",
    )
    return {
        "id": tx.id,
        "reference": tx.reference,
        "type": tx.type.value if hasattr(tx.type, "value") else str(tx.type),
        "amount": float(tx.amount),
        "memo": tx.memo,
        "status": tx.status.value if hasattr(tx.status, "value") else str(tx.status),
    }


# ── Webhook callbacks from mobile money providers ────────────────
@router.post("/callback/{provider}", include_in_schema=False)
async def deposit_callback(
    provider: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Webhook callback — called by MTN MoMo / Airtel Money when payment is confirmed.

    For the stub provider, you can call this manually to simulate completion:
      POST /api/deposit/callback/stub
      Body: {"reference": "DEP-XXXX-YYYY", "status": "SUCCESSFUL", "amount": 100}
    """
    body = await request.body()

    log.info(
        "deposit.callback_received",
        provider=provider,
        body_length=len(body),
    )

    try:
        payload = json.loads(body)
    except Exception:
        log.warning("deposit.callback_invalid_json", provider=provider)
        return {"status": "error", "message": "Invalid JSON"}

    # Extract reference + status from the callback payload
    reference = None
    payment_status = None
    amount = None

    if provider == "mtn_momo":
        reference = payload.get("externalId")
        payment_status = payload.get("status", "").upper()
        amount = float(payload.get("amount", 0))
    elif provider == "airtel_money":
        tx_data = payload.get("transaction", {})
        reference = tx_data.get("reference") or tx_data.get("id")
        payment_status = tx_data.get("status", "").upper()
        amount = float(tx_data.get("amount", 0))
    else:
        # Stub — manual simulation
        reference = payload.get("reference")
        payment_status = payload.get("status", "SUCCESSFUL").upper()
        amount = float(payload.get("amount", 0))

    if not reference:
        log.warning("deposit.callback_missing_reference", provider=provider)
        return {"status": "error", "message": "Missing reference"}

    # Find the pending deposit
    pending = (
        db.query(PendingDeposit)
        .filter(PendingDeposit.reference == reference)
        .first()
    )
    if pending is None:
        log.warning("deposit.callback_pending_not_found", reference=reference)
        return {"status": "error", "message": "Pending deposit not found"}

    if pending.status != PendingDepositStatus.pending:
        log.info("deposit.callback_already_processed", reference=reference, status=pending.status)
        return {"status": "ok", "message": "Already processed", "final_status": pending.status.value}

    # Save the callback payload for debugging
    pending.callback_payload = json.dumps(payload, indent=2)

    if payment_status in ("SUCCESSFUL", "SUCCESS", "COMPLETED"):
        # Complete the deposit — credit the user's account
        from app.models.user import User as UserModel

        user = db.query(UserModel).filter(UserModel.id == pending.user_id).first()
        if user is None:
            log.error("deposit.callback_user_not_found", user_id=pending.user_id)
            return {"status": "error", "message": "User not found"}

        # Use TransactionService to create the actual deposit transaction
        service = TransactionService(db)
        try:
            tx = service.deposit(
                user,
                pending.amount,
                memo=pending.memo or f"Mobile money deposit via {pending.provider}",
                ip_address=None,
                request_id=reference,
            )
            pending.status = PendingDepositStatus.completed
            pending.transaction_id = tx.id
            pending.completed_at = datetime.now(timezone.utc)
            db.commit()

            log.info(
                "deposit.callback_completed",
                reference=reference,
                transaction_id=tx.id,
                tx_ref=tx.reference,
                amount=pending.amount,
            )
            return {"status": "success", "reference": reference, "transaction_reference": tx.reference}

        except OrionError as exc:
            pending.status = PendingDepositStatus.failed
            pending.failure_reason = exc.message
            db.commit()
            log.warning(
                "deposit.callback_failed",
                reference=reference,
                error=exc.message,
            )
            return {"status": "failed", "reference": reference, "error": exc.message}

    else:
        # Payment failed / declined / timed out
        pending.status = PendingDepositStatus.failed
        pending.failure_reason = f"Provider returned status: {payment_status}"
        db.commit()

        log.warning(
            "deposit.callback_payment_failed",
            reference=reference,
            status=payment_status,
        )
        return {"status": "failed", "reference": reference, "payment_status": payment_status}



# ── MTN MoMo provisioning endpoints (setup flow) ─────────────────
@router.get("/mtn/setup")
def mtn_setup_instructions():
    return {
        "provider": "mtn_momo",
        "steps": [
            {"step": 1, "title": "Register at MTN MoMo Developer Portal", "url": "https://momodeveloper.mtn.com"},
            {"step": 2, "title": "Get Primary Key + Secondary Key from the Collection API product"},
            {"step": 3, "title": "POST /api/deposit/mtn/provision-api-user"},
            {"step": 4, "title": "POST /api/deposit/mtn/create-api-key"},
            {"step": 5, "title": "Ready! Deposits work via /api/deposit/initiate"}
        ],
        "current_config": {
            "has_primary_key": bool(settings.mtn_momo_primary_key),
            "has_api_user_id": bool(settings.mtn_momo_api_user_id),
            "has_api_key": bool(settings.mtn_momo_api_key),
        }
    }


@router.post("/mtn/provision-api-user")
def mtn_provision_api_user(current_user: User = Depends(get_current_user)):
    from app.services.mobile_money_service import MtnMoMoProvider
    return MtnMoMoProvider().provision_api_user()


@router.post("/mtn/create-api-key")
def mtn_create_api_key(current_user: User = Depends(get_current_user)):
    from app.services.mobile_money_service import MtnMoMoProvider
    return MtnMoMoProvider().create_api_key()
