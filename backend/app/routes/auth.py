from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import Transaction, User
from app.schemas.user import Token, UserCreate, UserLogin, UserResponse
from app.services.auth_service import create_access_token, hash_pin, verify_pin

router = APIRouter(prefix="/auth", tags=["auth"])


def generate_account_number(db: Session) -> str:
    while True:
        account_number = str(10000000000000 + db.query(User).count() * 17 + 1)[0:14]
        if not db.query(User).filter(User.account_number == account_number).first():
            return account_number


@router.post("/register", response_model=UserResponse)
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        account_number=generate_account_number(db),
        full_name=payload.full_name.strip(),
        email=email,
        pin_hash=hash_pin(payload.pin),
        balance=0.00,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_pin(payload.pin, user.pin_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or PIN")

    token = create_access_token(subject=user.email)
    return {"access_token": token, "token_type": "bearer"}
