"""Transaction API tests — deposit, withdraw, transfer, history."""
from __future__ import annotations


def test_deposit_increases_balance(client, registered_user):
    r = client.post(
        "/api/transactions/deposit",
        json={"amount": 100.50, "memo": "paycheck"},
        headers=registered_user["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "deposit"
    assert body["amount"] == 100.50
    assert body["status"] == "completed"
    assert body["reference"].startswith("ORX-")

    me = client.get("/api/accounts/me", headers=registered_user["headers"]).json()
    assert float(me["balance"]) == 100.50


def test_deposit_rejects_zero_or_negative(client, registered_user):
    r1 = client.post(
        "/api/transactions/deposit",
        json={"amount": 0},
        headers=registered_user["headers"],
    )
    assert r1.status_code == 422  # pydantic gt=0
    r2 = client.post(
        "/api/transactions/deposit",
        json={"amount": -50},
        headers=registered_user["headers"],
    )
    assert r2.status_code == 422


def test_withdraw_decreases_balance(client, registered_user):
    client.post(
        "/api/transactions/deposit",
        json={"amount": 500, "memo": "seed"},
        headers=registered_user["headers"],
    )
    r = client.post(
        "/api/transactions/withdraw",
        json={"amount": 100, "memo": "lunch"},
        headers=registered_user["headers"],
    )
    assert r.status_code == 200
    me = client.get("/api/accounts/me", headers=registered_user["headers"]).json()
    assert float(me["balance"]) == 400


def test_withdraw_insufficient_funds(client, registered_user):
    r = client.post(
        "/api/transactions/withdraw",
        json={"amount": 1000},
        headers=registered_user["headers"],
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "insufficient_funds"


def test_transfer_to_self_rejected(client, registered_user):
    r = client.post(
        "/api/transactions/transfer",
        json={"recipient_account_number": registered_user["user"]["account_number"], "amount": 10},
        headers=registered_user["headers"],
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "self_transfer_forbidden"


def test_transfer_to_nonexistent_recipient(client, registered_user):
    r = client.post(
        "/api/transactions/transfer",
        json={"recipient_account_number": "00000000000000", "amount": 10},
        headers=registered_user["headers"],
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "account_not_found"


def test_transfer_succeeds_between_users(client):
    # User A
    a = client.post(
        "/api/auth/register",
        json={"full_name": "Alice", "email": "alice@orionbank.com", "pin": "8421"},
    ).json()
    # User B
    b = client.post(
        "/api/auth/register",
        json={"full_name": "Bob", "email": "bob@orionbank.com", "pin": "7351"},
    ).json()
    # Alice logs in
    tok_a = client.post(
        "/api/auth/login",
        json={"email": "alice@orionbank.com", "pin": "8421"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok_a}"}

    # Alice deposits 500
    client.post("/api/transactions/deposit", json={"amount": 500}, headers=headers)

    # Alice transfers 200 to Bob
    r = client.post(
        "/api/transactions/transfer",
        json={
            "recipient_account_number": b["account_number"],
            "amount": 200,
            "memo": "rent split",
        },
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["type"] == "transfer"

    # Verify balances
    me_a = client.get("/api/accounts/me", headers=headers).json()
    assert float(me_a["balance"]) == 300

    tok_b = client.post(
        "/api/auth/login",
        json={"email": "bob@orionbank.com", "pin": "7351"},
    ).json()["access_token"]
    me_b = client.get("/api/accounts/me", headers={"Authorization": f"Bearer {tok_b}"}).json()
    assert float(me_b["balance"]) == 200


def test_transfer_idempotency_key_prevents_duplicate(client):
    # Two users
    a = client.post(
        "/api/auth/register",
        json={"full_name": "Alice", "email": "alice@orionbank.com", "pin": "8421"},
    ).json()
    b = client.post(
        "/api/auth/register",
        json={"full_name": "Bob", "email": "bob@orionbank.com", "pin": "7351"},
    ).json()
    tok = client.post(
        "/api/auth/login",
        json={"email": "alice@orionbank.com", "pin": "8421"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    client.post("/api/transactions/deposit", json={"amount": 1000}, headers=headers)

    payload = {
        "recipient_account_number": b["account_number"],
        "amount": 100,
        "idempotency_key": "idem-key-12345",
    }
    r1 = client.post("/api/transactions/transfer", json=payload, headers=headers)
    assert r1.status_code == 200
    r2 = client.post("/api/transactions/transfer", json=payload, headers=headers)
    assert r2.status_code == 200
    # Same reference returned
    assert r1.json()["reference"] == r2.json()["reference"]
    # Balance only decreased by 100, not 200
    me = client.get("/api/accounts/me", headers=headers).json()
    assert float(me["balance"]) == 900  # 1000 - 100


def test_history_returns_both_incoming_and_outgoing(client):
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

    client.post("/api/transactions/deposit", json={"amount": 500}, headers=headers)
    client.post(
        "/api/transactions/transfer",
        json={"recipient_account_number": b["account_number"], "amount": 200},
        headers=headers,
    )
    r = client.get("/api/transactions", headers=headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    # Most recent first
    assert items[0]["type"] == "transfer"
    assert items[1]["type"] == "deposit"


def test_get_single_transaction(client, registered_user):
    r = client.post(
        "/api/transactions/deposit",
        json={"amount": 50},
        headers=registered_user["headers"],
    )
    tx_id = r.json()["id"]
    r2 = client.get(f"/api/transactions/{tx_id}", headers=registered_user["headers"])
    assert r2.status_code == 200
    assert r2.json()["id"] == tx_id


def test_cannot_view_other_users_transaction(client):
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
    tok_b = client.post(
        "/api/auth/login",
        json={"email": "bob@orionbank.com", "pin": "7351"},
    ).json()["access_token"]

    # Alice makes a deposit
    r = client.post(
        "/api/transactions/deposit",
        json={"amount": 100},
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    tx_id = r.json()["id"]

    # Bob tries to view Alice's transaction — should get 404 (don't leak existence)
    r2 = client.get(f"/api/transactions/{tx_id}", headers={"Authorization": f"Bearer {tok_b}"})
    assert r2.status_code == 404


def test_statement_pdf_export(client, registered_user):
    client.post(
        "/api/transactions/deposit",
        json={"amount": 250, "memo": "test deposit"},
        headers=registered_user["headers"],
    )
    r = client.get("/api/statements/export.pdf", headers=registered_user["headers"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) > 1000
