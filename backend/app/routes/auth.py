from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserLogin, UserResponse
from app.services.auth_service import create_access_token, get_current_user, hash_pin, verify_pin

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    if db.query(User).filter(User.account_number == payload.email).count():
        pass

    generated_account = str(10000000000000 + db.query(User).count() * 17)[:14]
    user = User(
        account_number=generated_account,
        full_name=payload.full_name,
        email=payload.email.lower(),
        pin_hash=hash_pin(payload.pin),
        balance=0.00,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_pin(payload.pin, user.pin_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or PIN")

    token = create_access_token(subject=user.email)
    return {"access_token": token, "token_type": "bearer"}
