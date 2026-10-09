"""Email notification tests — verify the right email fires for each event."""
from __future__ import annotations

from app.services.email_service import get_sent_emails


def _emails_with(subject_contains: str) -> list[dict]:
    return [e for e in get_sent_emails() if subject_contains.lower() in e["subject"].lower()]


# ── Welcome email ──────────────────────────────────────────────────
def test_register_sends_welcome_email(client):
    r = client.post(
        "/api/auth/register",
        json={"full_name": "Welcome User", "email": "welcome@orionbank.com", "pin": "8421"},
    )
    assert r.status_code == 201
    welcome_emails = _emails_with("Welcome")
    assert len(welcome_emails) == 1
    assert welcome_emails[0]["to"] == "welcome@orionbank.com"
    # Welcome email should contain the account number
    body = welcome_emails[0]["text_body"]
    assert r.json()["account_number"] in body


# ── Deposit ───────────────────────────────────────────────────────
def test_deposit_sends_email(client, registered_user):
    client.post(
        "/api/transactions/deposit",
        json={"amount": 250.00, "memo": "paycheck"},
        headers=registered_user["headers"],
    )
    emails = _emails_with("Deposit")
    assert len(emails) == 1
    assert emails[0]["to"] == registered_user["email"]
    assert "$250.00" in emails[0]["text_body"]


# ── Withdrawal ───────────────────────────────────────────────────
def test_withdrawal_sends_email(client, registered_user):
    client.post(
        "/api/transactions/deposit",
        json={"amount": 500},
        headers=registered_user["headers"],
    )
    client.post(
        "/api/transactions/withdraw",
        json={"amount": 100, "memo": "rent"},
        headers=registered_user["headers"],
    )
    withdraw_emails = _emails_with("Withdrawal")
    assert len(withdraw_emails) == 1
    assert "$100.00" in withdraw_emails[0]["text_body"]


# ── Transfer (both parties notified) ─────────────────────────────
def test_transfer_sends_two_emails(client):
    a = client.post(
        "/api/auth/register",
        json={"full_name": "Alice", "email": "alice@orionbank.com", "pin": "8421"},
    ).json()
    b = client.post(
        "/api/auth/register",
        json={"full_name": "Bob", "email": "bob@orionbank.com", "pin": "7351"},
    ).json()
    tok_a = client.post(
        "/api/auth/login",
        json={"email": "alice@orionbank.com", "pin": "8421"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok_a}"}

    client.post("/api/transactions/deposit", json={"amount": 1000}, headers=headers)
    client.post(
        "/api/transactions/transfer",
        json={"recipient_account_number": b["account_number"], "amount": 200, "memo": "rent"},
        headers=headers,
    )

    outgoing = _emails_with("Transfer of $200.00 sent")
    incoming = _emails_with("received $200.00")
    assert len(outgoing) == 1
    assert len(incoming) == 1
    assert outgoing[0]["to"] == "alice@orionbank.com"
    assert incoming[0]["to"] == "bob@orionbank.com"
    # Both should contain the reference
    assert "ORX-" in outgoing[0]["text_body"]
    assert "ORX-" in incoming[0]["text_body"]
    # Bob should see Alice's name
    assert "Alice" in incoming[0]["text_body"]


# ── KYC decision emails ──────────────────────────────────────────
def test_kyc_approve_sends_email(client, admin_user, user_with_pending_kyc):
    target_id = user_with_pending_kyc["user"]["id"]
    client.post(
        f"/api/admin/kyc/{target_id}/approve",
        json={},
        headers=admin_user["headers"],
    )
    emails = _emails_with("KYC verified")
    assert len(emails) == 1
    assert emails[0]["to"] == user_with_pending_kyc["email"]


def test_kyc_reject_sends_email(client, admin_user, user_with_pending_kyc):
    target_id = user_with_pending_kyc["user"]["id"]
    client.post(
        f"/api/admin/kyc/{target_id}/reject",
        json={"reason": "Bad address — please update."},
        headers=admin_user["headers"],
    )
    emails = _emails_with("KYC needs revision")
    assert len(emails) == 1
    assert emails[0]["to"] == user_with_pending_kyc["email"]
    assert "Bad address" in emails[0]["text_body"]


# ── Per-event opt-out ────────────────────────────────────────────
def test_opting_out_of_deposit_email_skips_send(client, registered_user):
    client.put(
        "/api/accounts/me/notification-prefs",
        json={"email_on_deposit": False},
        headers=registered_user["headers"],
    )
    client.post(
        "/api/transactions/deposit",
        json={"amount": 100},
        headers=registered_user["headers"],
    )
    assert len(_emails_with("Deposit")) == 0


def test_opting_out_of_transfer_emails_skips_both_parties(client):
    # Alice opts out of outgoing transfer emails
    a = client.post(
        "/api/auth/register",
        json={"full_name": "Alice", "email": "alice@orionbank.com", "pin": "8421"},
    ).json()
    b = client.post(
        "/api/auth/register",
        json={"full_name": "Bob", "email": "bob@orionbank.com", "pin": "7351"},
    ).json()
    tok_a = client.post(
        "/api/auth/login", json={"email": "alice@orionbank.com", "pin": "8421"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok_a}"}

    client.put(
        "/api/accounts/me/notification-prefs",
        json={"email_on_transfer_out": False},
        headers=headers,
    )
    client.post("/api/transactions/deposit", json={"amount": 1000}, headers=headers)
    client.post(
        "/api/transactions/transfer",
        json={"recipient_account_number": b["account_number"], "amount": 100},
        headers=headers,
    )

    outgoing = _emails_with("Transfer of $100.00 sent")
    incoming = _emails_with("received $100.00")
    assert len(outgoing) == 0, "Alice opted out, should not receive outgoing email"
    assert len(incoming) == 1, "Bob has not opted out, should still receive incoming email"


# ── Email preference endpoints ──────────────────────────────────
def test_get_notification_prefs(client, registered_user):
    r = client.get(
        "/api/accounts/me/notification-prefs",
        headers=registered_user["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email_on_deposit"] is True
    assert body["email_on_withdrawal"] is True
    assert body["email_on_transfer_in"] is True
    assert body["email_on_transfer_out"] is True
    assert body["email_on_kyc_decision"] is True


def test_update_notification_prefs(client, registered_user):
    r = client.put(
        "/api/accounts/me/notification-prefs",
        json={
            "email_on_deposit": False,
            "email_on_transfer_out": False,
        },
        headers=registered_user["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email_on_deposit"] is False
    assert body["email_on_transfer_out"] is False
    assert body["email_on_withdrawal"] is True  # unchanged


# ── Silent failure ───────────────────────────────────────────────
def test_email_failure_does_not_break_transaction(client, registered_user, monkeypatch):
    """If the email backend throws, the deposit should still succeed."""
    from app.services import email_service

    def boom(*args, **kwargs):
        raise RuntimeError("SMTP exploded")

    monkeypatch.setattr(email_service.EmailService, "_dispatch", boom)

    r = client.post(
        "/api/transactions/deposit",
        json={"amount": 100},
        headers=registered_user["headers"],
    )
    assert r.status_code == 200, "Email failure should not break the transaction"


# ── HTML email contains expected content ─────────────────────────
def test_html_email_renders_correctly(client, registered_user):
    client.post(
        "/api/transactions/deposit",
        json={"amount": 1500.00, "memo": "salary"},
        headers=registered_user["headers"],
    )
    emails = _emails_with("Deposit")
    assert len(emails) == 1
    html = emails[0]["html_body"]
    # HTML should contain the amount formatted
    assert "$1,500.00" in html
    # Should reference the account holder
    assert "Test User" in html
