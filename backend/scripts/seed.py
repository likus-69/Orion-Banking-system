"""Seed script — populates the database with demo data.

Usage:
    cd backend
    python scripts/seed.py

This is safe to run multiple times: existing demo users are skipped.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure 'app' is importable when running from the backend/ dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Force SQLite if no DATABASE_URL is set, for local dev convenience.
os.environ.setdefault("DATABASE_URL", "sqlite:///./orion_banking.db")
os.environ.setdefault("SECRET_KEY", "dev-only-secret-not-for-production-32-chars-or-more")
os.environ.setdefault("ENV", "dev")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models.user import KycStatus, User, UserRole  # noqa: E402
from app.models.transaction import (  # noqa: E402
    Transaction,
    TransactionCategory,
    TransactionStatus,
    TransactionType,
)
from app.models.notification import Notification  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.services.token_service import hash_pin  # noqa: E402


DEMO_USERS = [
    {
        "full_name": "Mary Garcia",
        "email": "mary.garcia@orionbank.com",
        "pin": "8421",
        "balance": 12_500.00,
        "phone": "+1-555-010-1234",
        "city": "Kampala",
        "country": "Uganda",
        "kyc_status": KycStatus.verified,
        "role": UserRole.customer,
    },
    {
        "full_name": "Alex Rivera",
        "email": "alex.rivera@orionbank.com",
        "pin": "7351",
        "balance": 3_200.50,
        "phone": "+1-555-020-9876",
        "city": "Nairobi",
        "country": "Kenya",
        "kyc_status": KycStatus.in_review,  # shows up in admin KYC queue
        "role": UserRole.customer,
    },
    {
        "full_name": "Demo User",
        "email": "demo@orionbank.com",
        "pin": "4242",
        "balance": 0.00,
        "kyc_status": KycStatus.pending,
        "role": UserRole.customer,
    },
    {
        "full_name": "Site Admin",
        "email": "admin@orionbank.com",
        "pin": "1357",
        "balance": 0.00,
        "kyc_status": KycStatus.verified,
        "role": UserRole.admin,
    },
]


def generate_account_number() -> str:
    import secrets as _secrets

    return f"{_secrets.randbelow(90_000_000_000_000) + 10_000_000_000_000}"


def generate_reference() -> str:
    import secrets as _secrets

    return f"ORX-{_secrets.token_hex(2).upper()}-{_secrets.token_hex(2).upper()}"


def seed() -> None:
    # Create tables if not present (dev convenience).
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        created_users = []
        for u in DEMO_USERS:
            existing = db.query(User).filter(User.email == u["email"]).first()
            if existing:
                print(f"  skip existing: {u['email']}  (account {existing.account_number})")
                created_users.append(existing)
                continue

            user = User(
                account_number=generate_account_number(),
                full_name=u["full_name"],
                email=u["email"],
                pin_hash=hash_pin(u["pin"]),
                balance=u["balance"],
                phone=u.get("phone"),
                city=u.get("city"),
                country=u.get("country"),
                kyc_status=u.get("kyc_status", KycStatus.pending),
                role=u.get("role", UserRole.customer),
                is_active=True,
                is_locked=False,
            )
            db.add(user)
            db.flush()
            db.add(
                AuditLog(
                    user_id=user.id,
                    action="register",
                    details=f"Seeded account {user.account_number} (role={user.role.value})",
                )
            )
            print(f"  created: {u['email']}  (account {user.account_number})  PIN: {u['pin']}  role: {u.get('role', UserRole.customer).value}")
            created_users.append(user)

        db.commit()

        # Generate some sample transactions for Mary Garcia.
        mary = next((u for u in created_users if u.email == "mary.garcia@orionbank.com"), None)
        alex = next((u for u in created_users if u.email == "alex.rivera@orionbank.com"), None)
        if mary and alex:
            sample_txs = [
                # (type, from_id, to_id, amount, memo, category)
                (TransactionType.deposit, None, mary.id, 5000.00, "Salary deposit", TransactionCategory.salary),
                (TransactionType.deposit, None, mary.id, 800.00, "Freelance payment", TransactionCategory.general),
                (TransactionType.withdrawal, mary.id, None, 350.00, "ATM withdrawal", TransactionCategory.general),
                (TransactionType.withdrawal, mary.id, None, 1250.00, "Rent payment", TransactionCategory.rent),
                (TransactionType.transfer, mary.id, alex.id, 200.00, "Dinner split", TransactionCategory.dining),
                (TransactionType.transfer, alex.id, mary.id, 50.00, "Coffee reimbursement", TransactionCategory.dining),
                (TransactionType.deposit, None, alex.id, 1500.00, "Bonus", TransactionCategory.salary),
                (TransactionType.withdrawal, alex.id, None, 75.00, "Groceries", TransactionCategory.groceries),
            ]
            existing_tx_count = db.query(Transaction).count()
            if existing_tx_count == 0:
                for tx_type, from_id, to_id, amount, memo, category in sample_txs:
                    tx = Transaction(
                        reference=generate_reference(),
                        from_account_id=from_id,
                        to_account_id=to_id,
                        type=tx_type,
                        amount=amount,
                        memo=memo,
                        category=category,
                        status=TransactionStatus.completed,
                    )
                    db.add(tx)
                db.commit()
                print(f"  created {len(sample_txs)} sample transactions")

                # Add a notification for Mary
                db.add(
                    Notification(
                        user_id=mary.id,
                        title="Welcome to Orion Banking",
                        body="Your demo account is ready. Try making a deposit!",
                        level="info",
                        is_read=False,
                    )
                )
                db.commit()

        print()
        print("Seed complete. Login credentials:")
        for u in DEMO_USERS:
            print(f"  {u['email']} / {u['pin']}")
    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding Orion Banking database…")
    seed()
