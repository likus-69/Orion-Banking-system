from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import Transaction, User
from app.schemas.user import DepositRequest, TransactionRecord, TransferRequest, UserResponse
from app.services.auth_service import create_audit_log, get_current_user

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/me", response_model=UserResponse)
def get_my_account(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/history", response_model=list[TransactionRecord])
def get_account_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    transactions = (
        db.query(Transaction)
        .filter((Transaction.from_account_id == current_user.id) | (Transaction.to_account_id == current_user.id))
        .order_by(Transaction.created_at.desc())
        .all()
    )

    response = []
    for tx in transactions:
        if tx.from_account_id == current_user.id:
            direction = "outgoing"
            counterparty = db.query(User).filter(User.id == tx.to_account_id).first() if tx.to_account_id else None
        else:
            direction = "incoming"
            counterparty = db.query(User).filter(User.id == tx.from_account_id).first() if tx.from_account_id else None

        response.append(
            TransactionRecord(
                id=tx.id,
                type=tx.type,
                amount=float(tx.amount),
                memo=tx.memo,
                status=tx.status,
                created_at=tx.created_at,
                direction=direction,
                counterparty_name=counterparty.full_name if counterparty else None,
                counterparty_account_number=counterparty.account_number if counterparty else None,
            )
        )
    return response


@router.post("/deposit")
def deposit_funds(payload: DepositRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be greater than zero")

    current_user.balance += payload.amount
    tx = Transaction(
        from_account_id=None,
        to_account_id=current_user.id,
        type="deposit",
        amount=payload.amount,
        memo=payload.memo,
        status="completed",
    )
    db.add(tx)
    create_audit_log(db, current_user.id, "deposit", f"Deposited {payload.amount} via API", ip_address=None)
    db.commit()
    return {"message": "Deposit successful", "balance": float(current_user.balance)}


@router.post("/withdraw")
def withdraw_funds(payload: DepositRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be greater than zero")
    if payload.amount > float(current_user.balance):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

    current_user.balance -= payload.amount
    tx = Transaction(
        from_account_id=current_user.id,
        to_account_id=None,
        type="withdrawal",
        amount=payload.amount,
        memo=payload.memo,
        status="completed",
    )
    db.add(tx)
    create_audit_log(db, current_user.id, "withdrawal", f"Withdrew {payload.amount} via API", ip_address=None)
    db.commit()
    return {"message": "Withdrawal successful", "balance": float(current_user.balance)}


@router.post("/transfer")
def transfer_funds(payload: TransferRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    recipient = db.query(User).filter(User.account_number == payload.recipient_account_number).first()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient account not found")
    if recipient.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot transfer to your own account")
    if payload.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be greater than zero")
    if payload.amount > float(current_user.balance):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

    current_user.balance -= payload.amount
    recipient.balance += payload.amount
    tx = Transaction(
        from_account_id=current_user.id,
        to_account_id=recipient.id,
        type="transfer",
        amount=payload.amount,
        memo=payload.memo,
        status="completed",
    )
    db.add_all([tx, current_user, recipient])
    create_audit_log(db, current_user.id, "transfer_outgoing", f"Transferred {payload.amount} to {recipient.account_number}", ip_address=None)
    create_audit_log(db, recipient.id, "transfer_incoming", f"Received {payload.amount} from {current_user.account_number}", ip_address=None)
    db.commit()
    return {"message": "Transfer successful", "balance": float(current_user.balance)}
