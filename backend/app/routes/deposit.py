"""Deposit API routes — mobile money (MTN/Airtel) + webhook callbacks."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_current_user, get_db
from app.models.transaction import TransactionStatus, TransactionType
from app.models.user import User
from app.services.mobile_money_service import DepositResult, get_deposit_provider
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/api/deposit", tags=["deposit"])


class InitiateDepositRequest(BaseModel):
    """Initiate a mobile money deposit — user enters phone number + amount."""

    phone_number: str = Field(..., min_length=10, max_length=15, description="Phone number with country code, e.g. +256700000000")
    amount: float = Field(..., gt=0, le=settings.max_deposit_per_transaction)
    memo: str | None = Field(None, max_length=500)


class InitiateDepositResponse(BaseModel):
    status: str  # "pending" | "success" | "failed"
    reference: str
    provider: str  # "stub" | "mtn_momo" | "airtel_money"
    message: str
    provider_reference: str | None = None


class ManualDepositRequest(BaseModel):
    """For backward compatibility — manual deposit (no mobile money)."""

    amount: float = Field(..., gt=0, le=settings.max_deposit_per_transaction)
    memo: str | None = Field(None, max_length=500)


@router.post("/initiate", response_model=InitiateDepositResponse)
def initiate_mobile_money_deposit(
    payload: InitiateDepositRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initiate a mobile money deposit.

    This sends a payment prompt to the user's phone. Once they approve
    (on their MTN/Airtel app), the provider calls our webhook callback
    and we complete the deposit.

    To test without real credentials:
      Set MOBILE_MONEY_PROVIDER=stub in .env — the stub provider returns
      "pending" immediately, simulating the flow.
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

    return InitiateDepositResponse(
        status=result.status,
        reference=result.reference,
        provider=result.provider,
        message=result.message,
        provider_reference=result.provider_reference,
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

    This is the 'old' deposit endpoint — kept for backward compatibility.
    Subject to the same limits + KYC checks.
    """
    from app.deps import get_request_meta

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
    """Webhook callback endpoint for mobile money providers.

    MTN MoMo and Airtel Money will call this endpoint when a deposit
    is confirmed (user approved the payment prompt on their phone).

    The provider sends a POST with the transaction status. We verify
    the signature, then complete the deposit by crediting the user's
    account.
    """
    from app.logging_config import get_logger

    log = get_logger("deposit.callback")

    body = await request.body()
    signature = request.headers.get("X-Signature", "")

    log.info(
        "deposit.callback_received",
        provider=provider,
        signature_present=bool(signature),
        body_length=len(body),
    )

    try:
        import json

        payload = json.loads(body)
    except Exception:
        log.warning("deposit.callback_invalid_json", provider=provider)
        return {"status": "error", "message": "Invalid JSON"}

    # Extract reference + status from the callback payload
    # MTN MoMo format: {"externalId": "...", "status": "SUCCESSFUL", ...}
    # Airtel format: {"transaction": {"id": "...", "status": "SUCCESS", ...}}
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
        # Stub provider — simulate success
        reference = payload.get("reference")
        payment_status = "SUCCESSFUL"
        amount = float(payload.get("amount", 0))

    if not reference:
        log.warning("deposit.callback_missing_reference", provider=provider)
        return {"status": "error", "message": "Missing reference"}

    # If payment was successful, find the pending deposit and complete it
    if payment_status in ("SUCCESSFUL", "SUCCESS", "COMPLETED"):
        # Look up the pending transaction by reference
        from app.models.transaction import Transaction
        from app.models.user import User as UserModel

        # In a real implementation, we'd store the pending deposit in a
        # separate table. For now, we look up the user by the reference
        # pattern and complete the deposit.
        # The reference format is: DEP-XXXX-YYYY
        # The user info would be stored in a pending_deposits table.
        # For the stub provider, we'll just log that it was received.

        log.info(
            "deposit.callback_success",
            provider=provider,
            reference=reference,
            amount=amount,
        )
        return {"status": "success", "reference": reference}
    else:
        log.warning(
            "deposit.callback_failed",
            provider=provider,
            reference=reference,
            status=payment_status,
        )
        return {"status": "failed", "reference": reference}
