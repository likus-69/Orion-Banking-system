"""Admin API tests — role-based access control + KYC review workflow."""
from __future__ import annotations


# ── Authorization ──────────────────────────────────────────────────
def test_admin_endpoints_require_admin_role(client, registered_user):
    """A regular customer must NOT be able to access admin endpoints."""
    endpoints = [
        ("GET", "/api/admin/stats"),
        ("GET", "/api/admin/users"),
        ("GET", "/api/admin/kyc/pending"),
    ]
    for method, path in endpoints:
        r = client.request(method, path, headers=registered_user["headers"])
        assert r.status_code == 403, f"{method} {path} should be 403 for customers, got {r.status_code}"
        assert r.json()["error"]["code"] == "authorization_failed"


def test_admin_endpoints_require_auth(client):
    """Anonymous requests get 401."""
    r = client.get("/api/admin/stats")
    assert r.status_code == 401


def test_admin_can_access_stats(client, admin_user):
    r = client.get("/api/admin/stats", headers=admin_user["headers"])
    assert r.status_code == 200
    body = r.json()
    for key in ("total_users", "total_admins", "pending_kyc", "verified_kyc",
                "rejected_kyc", "locked_accounts", "total_balance", "transactions_today"):
        assert key in body, f"missing stat: {key}"


# ── User listing ──────────────────────────────────────────────────
def test_admin_can_list_users(client, admin_user, registered_user):
    r = client.get("/api/admin/users", headers=admin_user["headers"])
    assert r.status_code == 200
    items = r.json()
    # At least 2 users: the admin + the registered customer
    assert len(items) >= 2
    emails = [u["email"] for u in items]
    assert "admin@orionbank.com" in emails
    assert "test@orionbank.com" in emails


def test_admin_user_search(client, admin_user, registered_user):
    r = client.get(
        "/api/admin/users?search=test@orion",
        headers=admin_user["headers"],
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["email"] == "test@orionbank.com"


def test_admin_user_role_filter(client, admin_user, registered_user):
    r = client.get(
        "/api/admin/users?role=admin",
        headers=admin_user["headers"],
    )
    assert r.status_code == 200
    items = r.json()
    assert all(u["role"] == "admin" for u in items)
    assert len(items) >= 1


# ── KYC review flow ───────────────────────────────────────────────
def test_kyc_queue_returns_only_pending(client, admin_user, user_with_pending_kyc):
    r = client.get("/api/admin/kyc/pending", headers=admin_user["headers"])
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["email"] == user_with_pending_kyc["email"]
    assert items[0]["kyc_status"] == "in_review"


def test_admin_approve_kyc(client, admin_user, user_with_pending_kyc):
    target_id = user_with_pending_kyc["user"]["id"]
    r = client.post(
        f"/api/admin/kyc/{target_id}/approve",
        json={"notes": "Documents verified"},
        headers=admin_user["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kyc_status"] == "verified"
    assert body["kyc_reviewed_by"] == admin_user["user"].id
    assert body["kyc_reviewed_at"] is not None
    assert body["kyc_rejection_reason"] is None


def test_admin_reject_kyc_requires_reason(client, admin_user, user_with_pending_kyc):
    target_id = user_with_pending_kyc["user"]["id"]
    # Empty reason
    r = client.post(
        f"/api/admin/kyc/{target_id}/reject",
        json={"reason": ""},
        headers=admin_user["headers"],
    )
    assert r.status_code == 422  # Pydantic min_length=4


def test_admin_reject_kyc_with_reason(client, admin_user, user_with_pending_kyc):
    target_id = user_with_pending_kyc["user"]["id"]
    r = client.post(
        f"/api/admin/kyc/{target_id}/reject",
        json={"reason": "Date of birth does not match — please re-submit."},
        headers=admin_user["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kyc_status"] == "rejected"
    assert body["kyc_rejection_reason"] == "Date of birth does not match — please re-submit."
    assert body["kyc_reviewed_by"] == admin_user["user"].id


def test_kyc_decision_creates_notification(client, admin_user, user_with_pending_kyc):
    target_id = user_with_pending_kyc["user"]["id"]
    # Approve
    client.post(
        f"/api/admin/kyc/{target_id}/approve",
        json={},
        headers=admin_user["headers"],
    )
    # Check user now has a notification
    r = client.get(
        "/api/notifications",
        headers=user_with_pending_kyc["headers"],
    )
    assert r.status_code == 200
    notifs = r.json()
    assert any("verified" in n["title"].lower() for n in notifs), \
        f"Expected a 'verified' notification, got: {[n['title'] for n in notifs]}"


def test_user_can_resubmit_kyc_after_rejection(client, admin_user, user_with_pending_kyc):
    """If admin rejects, the user can update KYC again to put it back in review."""
    target_id = user_with_pending_kyc["user"]["id"]
    # Reject
    client.post(
        f"/api/admin/kyc/{target_id}/reject",
        json={"reason": "Bad address"},
        headers=admin_user["headers"],
    )
    # User resubmits
    r = client.put(
        "/api/accounts/me/kyc",
        json={"address_line": "456 New St"},
        headers=user_with_pending_kyc["headers"],
    )
    assert r.status_code == 200
    assert r.json()["kyc_status"] == "in_review"
    assert r.json()["kyc_rejection_reason"] is None


# ── Account lock/unlock ──────────────────────────────────────────
def test_admin_can_lock_user(client, admin_user, registered_user):
    target_id = registered_user["user"]["id"]
    r = client.post(
        f"/api/admin/users/{target_id}/lock",
        headers=admin_user["headers"],
    )
    assert r.status_code == 200
    assert r.json()["is_locked"] is True


def test_locked_user_cannot_login(client, admin_user, registered_user):
    target_id = registered_user["user"]["id"]
    client.post(
        f"/api/admin/users/{target_id}/lock",
        headers=admin_user["headers"],
    )
    # Try to login
    r = client.post(
        "/api/auth/login",
        json={"email": registered_user["email"], "pin": registered_user["pin"]},
    )
    assert r.status_code == 401
    assert "locked" in r.json()["error"]["message"].lower()


def test_admin_can_unlock_user(client, admin_user, registered_user):
    target_id = registered_user["user"]["id"]
    # Lock first
    client.post(f"/api/admin/users/{target_id}/lock", headers=admin_user["headers"])
    # Then unlock
    r = client.post(f"/api/admin/users/{target_id}/unlock", headers=admin_user["headers"])
    assert r.status_code == 200
    assert r.json()["is_locked"] is False
    assert r.json()["failed_login_attempts"] == 0


def test_admin_cannot_lock_another_admin(client, admin_user, db):
    """Self-protection: admins can't lock other admins."""
    from app.models.user import KycStatus, User, UserRole
    from app.services.token_service import hash_pin

    other_admin = User(
        account_number="20000000000002",
        full_name="Other Admin",
        email="other-admin@orionbank.com",
        pin_hash=hash_pin("2468"),
        balance=0,
        role=UserRole.admin,
        kyc_status=KycStatus.verified,
    )
    db.add(other_admin)
    db.commit()
    db.refresh(other_admin)

    r = client.post(
        f"/api/admin/users/{other_admin.id}/lock",
        headers=admin_user["headers"],
    )
    assert r.status_code == 403


# ── Stats correctness ─────────────────────────────────────────────
def test_stats_counts_after_kyc_workflow(client, admin_user, user_with_pending_kyc):
    # Initially: 1 pending KYC (the customer), 1 verified (the admin themselves)
    r = client.get("/api/admin/stats", headers=admin_user["headers"])
    assert r.json()["pending_kyc"] == 1
    assert r.json()["verified_kyc"] == 1  # admin is verified

    # Approve the customer's KYC
    target_id = user_with_pending_kyc["user"]["id"]
    client.post(
        f"/api/admin/kyc/{target_id}/approve",
        json={},
        headers=admin_user["headers"],
    )

    r = client.get("/api/admin/stats", headers=admin_user["headers"])
    assert r.json()["pending_kyc"] == 0
    assert r.json()["verified_kyc"] == 2  # admin + customer


# ── Page routes ───────────────────────────────────────────────────
def test_admin_pages_require_admin(client, registered_user):
    """Customer hitting /admin gets 403."""
    for path in ["/admin", "/admin/kyc", "/admin/users"]:
        r = client.get(path, headers=registered_user["headers"], follow_redirects=False)
        assert r.status_code == 403, f"{path} should be 403 for customers"


def test_admin_pages_render_for_admin(client, admin_user):
    for path in ["/admin", "/admin/kyc", "/admin/users"]:
        r = client.get(path, headers=admin_user["headers"], follow_redirects=False)
        assert r.status_code == 200, f"{path} should render for admin"
        assert "text/html" in r.headers.get("content-type", "")
