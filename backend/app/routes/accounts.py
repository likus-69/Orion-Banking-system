from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import Transaction, User
from app.schemas.user import DepositRequest, TransferRequest, UserResponse
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/me", response_model=UserResponse)
def get_my_account(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/deposit")
def deposit_funds(payload: DepositRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be greater than zero")

    current_user.balance += payload.amount
    db.add(
        Transaction(
            from_account_id=None,
            to_account_id=current_user.id,
            type="deposit",
            amount=payload.amount,
            memo=payload.memo,
            status="completed",
        )
    )
    db.commit()
    return {"message": "Deposit successful", "balance": float(current_user.balance)}


@router.post("/withdraw")
def withdraw_funds(payload: DepositRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be greater than zero")
    if payload.amount > float(current_user.balance):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

    current_user.balance -= payload.amount
    db.add(
        Transaction(
            from_account_id=current_user.id,
            to_account_id=None,
            type="withdrawal",
            amount=payload.amount,
            memo=payload.memo,
            status="completed",
        )
    )
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
    db.add_all(
        [
            Transaction(
                from_account_id=current_user.id,
                to_account_id=recipient.id,
                type="transfer",
                amount=payload.amount,
                memo=payload.memo,
                status="completed",
            ),
            current_user,
            recipient,
        ]
    )
    db.commit()
    return {"message": "Transfer successful", "balance": float(current_user.balance)}
