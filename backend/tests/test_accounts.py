"""Account API tests."""
from __future__ import annotations


def test_get_me(client, registered_user):
    r = client.get("/api/accounts/me", headers=registered_user["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == registered_user["email"]
    assert body["full_name"] == "Test User"
    assert body["balance"] == 0


def test_update_profile_name(client, registered_user):
    r = client.patch(
        "/api/accounts/me",
        json={"full_name": "Updated Name"},
        headers=registered_user["headers"],
    )
    assert r.status_code == 200
    assert r.json()["full_name"] == "Updated Name"


def test_update_kyc(client, registered_user):
    r = client.put(
        "/api/accounts/me/kyc",
        json={
            "phone": "+1-555-010-1234",
            "address_line": "123 Main St",
            "city": "Kampala",
            "country": "Uganda",
        },
        headers=registered_user["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["phone"] == "+1-555-010-1234"
    assert body["city"] == "Kampala"
    assert body["country"] == "Uganda"
    assert body["kyc_status"] == "in_review"


def test_notifications_created_on_deposit(client, registered_user):
    client.post(
        "/api/transactions/deposit",
        json={"amount": 100},
        headers=registered_user["headers"],
    )
    r = client.get("/api/notifications", headers=registered_user["headers"])
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert items[0]["title"] == "Deposit"
