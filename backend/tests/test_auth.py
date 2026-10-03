"""Auth API tests — register, login, refresh, logout."""
from __future__ import annotations


def test_register_returns_user_without_pin(client):
    r = client.post(
        "/api/auth/register",
        json={"full_name": "Alice", "email": "alice@orionbank.com", "pin": "9281"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "alice@orionbank.com"
    assert body["account_number"]
    assert len(body["account_number"]) == 14
    assert "pin_hash" not in body  # never leak the hash
    assert body["balance"] == 0


def test_register_rejects_duplicate_email(client):
    payload = {"full_name": "Bob", "email": "bob@orionbank.com", "pin": "9281"}
    r1 = client.post("/api/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = client.post("/api/auth/register", json=payload)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "email_already_registered"


def test_register_rejects_weak_pin(client):
    for weak in ["1234", "1111", "4321"]:
        r = client.post(
            "/api/auth/register",
            json={"full_name": "Weak " + weak, "email": f"weak{weak}@orionbank.com", "pin": weak},
        )
        assert r.status_code == 422, f"PIN {weak} should be rejected"
        assert r.json()["error"]["code"] == "weak_pin"


def test_login_with_correct_pin(client):
    client.post(
        "/api/auth/register",
        json={"full_name": "Carol", "email": "carol@orionbank.com", "pin": "9281"},
    )
    r = client.post(
        "/api/auth/login",
        json={"email": "carol@orionbank.com", "pin": "9281"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_login_with_wrong_pin_does_not_reveal_user(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "nonexistent@orionbank.com", "pin": "9999"},
    )
    assert r.status_code == 401
    assert "Invalid email or PIN" in r.json()["error"]["message"]
    # Should NOT say "user not found" — that would be a user enumeration leak.


def test_login_lockout_after_five_failures(client):
    client.post(
        "/api/auth/register",
        json={"full_name": "Dave", "email": "dave@orionbank.com", "pin": "9281"},
    )
    for _ in range(5):
        r = client.post(
            "/api/auth/login",
            json={"email": "dave@orionbank.com", "pin": "0000"},
        )
        assert r.status_code == 401
    # Sixth attempt with correct PIN should now be locked
    r = client.post(
        "/api/auth/login",
        json={"email": "dave@orionbank.com", "pin": "9281"},
    )
    assert r.status_code == 401
    assert "locked" in r.json()["error"]["message"].lower()


def test_refresh_token_rotates(client):
    client.post(
        "/api/auth/register",
        json={"full_name": "Eve", "email": "eve@orionbank.com", "pin": "9281"},
    )
    r = client.post(
        "/api/auth/login",
        json={"email": "eve@orionbank.com", "pin": "9281"},
    )
    rt = r.json()["refresh_token"]
    r2 = client.post("/api/auth/refresh", json={"refresh_token": rt})
    assert r2.status_code == 200
    new_tokens = r2.json()
    assert new_tokens["access_token"] != r.json()["access_token"]
    assert new_tokens["refresh_token"] != rt  # rotated


def test_refresh_token_single_use(client):
    """A used refresh token cannot be used again."""
    client.post(
        "/api/auth/register",
        json={"full_name": "Frank", "email": "frank@orionbank.com", "pin": "9281"},
    )
    r = client.post(
        "/api/auth/login",
        json={"email": "frank@orionbank.com", "pin": "9281"},
    )
    rt = r.json()["refresh_token"]
    r1 = client.post("/api/auth/refresh", json={"refresh_token": rt})
    assert r1.status_code == 200
    r2 = client.post("/api/auth/refresh", json={"refresh_token": rt})
    assert r2.status_code == 401


def test_logout_revokes_refresh_token(client, registered_user):
    rt = client.post(
        "/api/auth/login",
        json={"email": registered_user["email"], "pin": registered_user["pin"]},
    ).json()["refresh_token"]
    # Logout
    r = client.post("/api/auth/logout", headers=registered_user["headers"])
    assert r.status_code == 204
    # The refresh token should now be unusable
    r2 = client.post("/api/auth/refresh", json={"refresh_token": rt})
    assert r2.status_code == 401


def test_protected_endpoint_requires_token(client):
    r = client.get("/api/accounts/me")
    assert r.status_code == 401
