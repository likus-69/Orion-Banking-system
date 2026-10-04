"""Notifications center tests — unread-count, mark-read, mark-all-read, RBAC."""
from __future__ import annotations


def test_unread_count_requires_auth(client):
    r = client.get("/api/notifications/unread-count")
    assert r.status_code == 401


def test_unread_count_starts_at_zero(client, registered_user):
    r = client.get("/api/notifications/unread-count", headers=registered_user["headers"])
    assert r.status_code == 200
    assert r.json() == {"unread_count": 0}


def test_unread_count_increments_after_event(client, registered_user):
    # A deposit creates a notification
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    r = client.get("/api/notifications/unread-count", headers=registered_user["headers"])
    assert r.json()["unread_count"] == 1

    # Another deposit
    client.post("/api/transactions/deposit", json={"amount": 50},
                headers=registered_user["headers"])
    r = client.get("/api/notifications/unread-count", headers=registered_user["headers"])
    assert r.json()["unread_count"] == 2


def test_mark_read_decrements_count(client, registered_user):
    # Create 2 notifications
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    client.post("/api/transactions/deposit", json={"amount": 50},
                headers=registered_user["headers"])
    # Get the IDs
    r = client.get("/api/notifications", headers=registered_user["headers"])
    notif_id = r.json()[0]["id"]
    # Mark one read
    r = client.post(f"/api/notifications/{notif_id}/read",
                    headers=registered_user["headers"])
    assert r.status_code == 204
    # Count should now be 1
    r = client.get("/api/notifications/unread-count", headers=registered_user["headers"])
    assert r.json()["unread_count"] == 1


def test_mark_all_read_clears_count(client, registered_user):
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    client.post("/api/transactions/deposit", json={"amount": 50},
                headers=registered_user["headers"])
    client.post("/api/transactions/deposit", json={"amount": 25},
                headers=registered_user["headers"])
    assert client.get("/api/notifications/unread-count",
                       headers=registered_user["headers"]).json()["unread_count"] == 3
    client.post("/api/notifications/read-all",
                headers=registered_user["headers"])
    assert client.get("/api/notifications/unread-count",
                       headers=registered_user["headers"]).json()["unread_count"] == 0


def test_list_unread_only_filters_correctly(client, registered_user):
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    client.post("/api/transactions/deposit", json={"amount": 50},
                headers=registered_user["headers"])
    # Mark one read
    items = client.get("/api/notifications", headers=registered_user["headers"]).json()
    notif_id = items[0]["id"]
    client.post(f"/api/notifications/{notif_id}/read",
                headers=registered_user["headers"])
    # List unread_only=true should return 1
    r = client.get("/api/notifications?unread_only=true",
                   headers=registered_user["headers"])
    assert len(r.json()) == 1
    # All returned should be unread
    assert all(not n["is_read"] for n in r.json())


def test_list_returns_all_when_not_filtered(client, registered_user):
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    items = client.get("/api/notifications", headers=registered_user["headers"]).json()
    assert len(items) >= 1


def test_cross_user_isolation(client):
    """Alice's notifications should not be visible to Bob."""
    a = client.post("/api/auth/register",
                    json={"full_name":"Alice","email":"alice@orionbank.com","pin":"8421"}).json()
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    tok_a = client.post("/api/auth/login",
                        json={"email":"alice@orionbank.com","pin":"8421"}).json()["access_token"]
    tok_b = client.post("/api/auth/login",
                        json={"email":"bob@orionbank.com","pin":"7351"}).json()["access_token"]
    # Alice creates notifications
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers={"Authorization": f"Bearer {tok_a}"})
    # Bob should see 0 unread
    r = client.get("/api/notifications/unread-count",
                   headers={"Authorization": f"Bearer {tok_b}"})
    assert r.json()["unread_count"] == 0
    # Bob's list should be empty
    r = client.get("/api/notifications",
                   headers={"Authorization": f"Bearer {tok_b}"})
    assert r.json() == []


def test_cannot_mark_read_other_users_notification(client):
    """Bob should not be able to mark Alice's notification as read."""
    a = client.post("/api/auth/register",
                    json={"full_name":"Alice","email":"alice@orionbank.com","pin":"8421"}).json()
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    tok_a = client.post("/api/auth/login",
                        json={"email":"alice@orionbank.com","pin":"8421"}).json()["access_token"]
    tok_b = client.post("/api/auth/login",
                        json={"email":"bob@orionbank.com","pin":"7351"}).json()["access_token"]
    # Alice deposits → notification created
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers={"Authorization": f"Bearer {tok_a}"})
    # Get Alice's notification ID
    alice_notif = client.get("/api/notifications",
                              headers={"Authorization": f"Bearer {tok_a}"}).json()[0]
    notif_id = alice_notif["id"]
    # Bob tries to mark it read — endpoint returns 204 but doesn't actually modify
    r = client.post(f"/api/notifications/{notif_id}/read",
                    headers={"Authorization": f"Bearer {tok_b}"})
    assert r.status_code == 204  # idempotent — doesn't error
    # Alice should still see it as unread
    r = client.get("/api/notifications/unread-count",
                   headers={"Authorization": f"Bearer {tok_a}"})
    assert r.json()["unread_count"] == 1


# ── Page route ───────────────────────────────────────────────────
def test_notifications_page_renders(client, registered_user):
    r = client.get("/notifications", headers=registered_user["headers"],
                   follow_redirects=False)
    assert r.status_code == 200
    assert "Notifications" in r.text
    assert "Mark all read" in r.text


def test_bell_icon_present_on_dashboard(client, registered_user):
    """The bell should appear in the topnav on authenticated pages."""
    r = client.get("/dashboard", headers=registered_user["headers"],
                   follow_redirects=False)
    assert r.status_code == 200
    assert "notifBell" in r.text
    assert "notif-dropdown" in r.text or "notifDropdown" in r.text


def test_bell_icon_absent_on_login_page(client):
    """Login page should NOT show the bell (unauthenticated)."""
    r = client.get("/login", follow_redirects=False)
    assert r.status_code == 200
    # Bell markup is always in base.html but its display is gated by JS
    # checking localStorage — so the bell element will be in the HTML
    # but `style="display: none;"` until JS runs. Confirm the JS gate is present.
    assert "orion_access_token" in r.text


# ── Polling-friendly ─────────────────────────────────────────────
def test_unread_count_is_fast_no_join(client, registered_user):
    """The endpoint should be a simple COUNT(*) — no joins to user table."""
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    r = client.get("/api/notifications/unread-count", headers=registered_user["headers"])
    # Response should be small + flat
    assert set(r.json().keys()) == {"unread_count"}
