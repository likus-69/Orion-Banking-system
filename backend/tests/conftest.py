"""Pytest configuration for Orion Banking tests.

Sets up an isolated in-memory SQLite DB per test, configures the FastAPI app,
and provides fixtures for authenticated clients and sample users.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from collections.abc import Iterator

# Make sure 'app' is importable
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Force SQLite in-memory + a known secret key BEFORE importing the app.
# Must be set before importing app.config (which caches settings).
os.environ.pop("DATABASE_URL", None)
os.environ["DATABASE_URL"] = "sqlite:///./test_orion.db"  # file-backed for cross-test isolation
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-32chars-or-more"
os.environ["ENV"] = "dev"
os.environ["LOG_LEVEL"] = "WARNING"
# Use the in-memory email backend so tests can assert what got sent.
os.environ["EMAIL_BACKEND"] = "memory"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models.user import KycStatus, User, UserRole
from app.services.email_service import get_sent_emails, reset_sent_emails
from app.services.token_service import hash_pin


@pytest.fixture(scope="function", autouse=True)
def reset_db() -> Iterator[None]:
    """Drop + recreate all tables before every test."""
    from app.services.email_service import reset_sent_emails

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    reset_sent_emails()
    yield
    Base.metadata.drop_all(bind=engine)
    reset_sent_emails()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """FastAPI TestClient with lifespan (so SQLite tables get created)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def registered_user(client: TestClient) -> dict:
    """Register + return a fresh customer's credentials and access token."""
    r = client.post(
        "/api/auth/register",
        json={
            "full_name": "Test User",
            "email": "test@orionbank.com",
            "pin": "8421",
        },
    )
    assert r.status_code == 201, r.text
    user = r.json()
    r = client.post(
        "/api/auth/login",
        json={"email": "test@orionbank.com", "pin": "8421"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {
        "user": user,
        "email": "test@orionbank.com",
        "pin": "8421",
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture()
def admin_user(client: TestClient, db: Session) -> dict:
    """Create an admin account directly in the DB and log in."""
    admin = User(
        account_number="10000000000001",
        full_name="Admin Root",
        email="admin@orionbank.com",
        pin_hash=hash_pin("1357"),
        balance=0,
        role=UserRole.admin,
        kyc_status=KycStatus.verified,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    r = client.post(
        "/api/auth/login",
        json={"email": "admin@orionbank.com", "pin": "1357"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {
        "user": admin,
        "email": "admin@orionbank.com",
        "pin": "1357",
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture()
def user_with_pending_kyc(client: TestClient, registered_user: dict) -> dict:
    """Submit KYC info so the customer's status becomes in_review."""
    r = client.put(
        "/api/accounts/me/kyc",
        json={
            "phone": "+1-555-010-1234",
            "address_line": "123 Main St",
            "city": "Kampala",
            "country": "Uganda",
            "date_of_birth": "1990-01-01T00:00:00",
        },
        headers=registered_user["headers"],
    )
    assert r.status_code == 200, r.text
    registered_user["user"] = r.json()
    return registered_user
