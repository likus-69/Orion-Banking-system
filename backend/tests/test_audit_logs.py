"""Admin audit log viewer tests — filters, pagination, RBAC."""
from __future__ import annotations


# ── Authorization ────────────────────────────────────────────────
def test_audit_logs_require_admin(client, registered_user):
    r = client.get("/api/admin/audit-logs", headers=registered_user["headers"])
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "authorization_failed"


def test_audit_logs_require_auth(client):
    r = client.get("/api/admin/audit-logs")
    assert r.status_code == 401


def test_audit_logs_actions_require_admin(client, registered_user):
    r = client.get("/api/admin/audit-logs/actions", headers=registered_user["headers"])
    assert r.status_code == 403


def test_admin_can_view_audit_logs(client, admin_user, registered_user):
    # Trigger a few audit log entries
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    r = client.get("/api/admin/audit-logs", headers=admin_user["headers"])
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 1  # at least the deposit


# ── Filters ──────────────────────────────────────────────────────
def test_filter_by_action_substring(client, admin_user, registered_user):
    # Alice registers + logs in → 'register' + 'login_success' actions
    r = client.get("/api/admin/audit-logs?action=login",
                   headers=admin_user["headers"])
    items = r.json()["items"]
    assert len(items) >= 1
    assert all("login" in item["action"] for item in items)


def test_filter_by_user_id(client, admin_user, registered_user):
    alice_id = registered_user["user"]["id"]
    r = client.get(f"/api/admin/audit-logs?user_id={alice_id}",
                   headers=admin_user["headers"])
    items = r.json()["items"]
    assert len(items) >= 1
    assert all(item["user_id"] == alice_id for item in items)


def test_filter_includes_user_email_and_name(client, admin_user, registered_user):
    """The endpoint joins user info so admins can see who did what without
    a second round-trip per row."""
    alice_id = registered_user["user"]["id"]
    r = client.get(f"/api/admin/audit-logs?user_id={alice_id}",
                   headers=admin_user["headers"])
    items = r.json()["items"]
    assert len(items) >= 1
    first = items[0]
    assert first["user_email"] == registered_user["email"]
    assert first["user_full_name"] == "Test User"


def test_free_text_search(client, admin_user, registered_user):
    # Trigger a deposit
    client.post("/api/transactions/deposit", json={"amount": 250, "memo": "audit test"},
                headers=registered_user["headers"])
    r = client.get("/api/admin/audit-logs?search=deposit",
                   headers=admin_user["headers"])
    items = r.json()["items"]
    assert len(items) >= 1
    assert any("deposit" in item["action"] for item in items)


def test_free_text_search_no_match(client, admin_user):
    r = client.get("/api/admin/audit-logs?search=zzznomatchxyz",
                   headers=admin_user["headers"])
    assert r.json()["total"] == 0
    assert r.json()["items"] == []


def test_distinct_actions_endpoint(client, admin_user, registered_user):
    # Trigger some actions
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    r = client.get("/api/admin/audit-logs/actions",
                   headers=admin_user["headers"])
    assert r.status_code == 200
    actions = r.json()
    assert isinstance(actions, list)
    assert "register" in actions
    assert "login_success" in actions


# ── Pagination ───────────────────────────────────────────────────
def test_pagination_basic(client, admin_user, registered_user):
    # Trigger a few entries
    for _ in range(5):
        client.post("/api/transactions/deposit", json={"amount": 10},
                    headers=registered_user["headers"])
    r = client.get("/api/admin/audit-logs?skip=0&limit=3",
                   headers=admin_user["headers"])
    body = r.json()
    assert len(body["items"]) <= 3
    assert body["skip"] == 0
    assert body["limit"] == 3
    assert body["total"] >= 5  # at least the 5 deposits we just made

    # Second page
    r = client.get("/api/admin/audit-logs?skip=3&limit=3",
                   headers=admin_user["headers"])
    body2 = r.json()
    assert body2["skip"] == 3
    # Should not overlap with first page
    first_ids = {item["id"] for item in body["items"]}
    second_ids = {item["id"] for item in body2["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_limit_capped_at_200(client, admin_user):
    """Trying to fetch more than 200 rows in one request is rejected."""
    r = client.get("/api/admin/audit-logs?limit=500",
                   headers=admin_user["headers"])
    assert r.status_code == 422


# ── Date range filter ─────────────────────────────────────────────
def test_date_range_filter(client, admin_user):
    """Use a future start_date to ensure we get 0 results (no logs in the future)."""
    from datetime import datetime, timedelta, timezone
    # FastAPI query param parsing prefers naive ISO format
    future_start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(tzinfo=None).isoformat()
    r = client.get(f"/api/admin/audit-logs?start_date={future_start}",
                   headers=admin_user["headers"])
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ── Sort order (newest first) ────────────────────────────────────
def test_results_are_newest_first(client, admin_user, registered_user):
    # Make two deposits at slightly different times
    client.post("/api/transactions/deposit", json={"amount": 10},
                headers=registered_user["headers"])
    client.post("/api/transactions/deposit", json={"amount": 20},
                headers=registered_user["headers"])
    r = client.get("/api/admin/audit-logs?action=deposit",
                   headers=admin_user["headers"])
    items = r.json()["items"]
    if len(items) >= 2:
        # First item should be newer than second
        from datetime import datetime
        first = datetime.fromisoformat(items[0]["created_at"].replace("Z", "+00:00")) if items[0]["created_at"].endswith("Z") else datetime.fromisoformat(items[0]["created_at"])
        second = datetime.fromisoformat(items[1]["created_at"].replace("Z", "+00:00")) if items[1]["created_at"].endswith("Z") else datetime.fromisoformat(items[1]["created_at"])
        # Both might be tz-naive (SQLite) — compare directly
        if first.tzinfo is None and second.tzinfo is None:
            assert first >= second
        else:
            assert first >= second


# ── Page route ───────────────────────────────────────────────────
def test_audit_logs_page_renders_for_admin(client, admin_user):
    r = client.get("/admin/audit-logs", headers=admin_user["headers"],
                   follow_redirects=False)
    assert r.status_code == 200
    assert "Audit logs" in r.text
    assert "Filters" in r.text


def test_audit_logs_page_forbidden_for_customer(client, registered_user):
    r = client.get("/admin/audit-logs", headers=registered_user["headers"],
                   follow_redirects=False)
    assert r.status_code == 403


# ── Admin actions show up in audit logs ──────────────────────────
def test_admin_actions_appear_in_audit_logs(client, admin_user, user_with_pending_kyc):
    """When an admin approves KYC, that action should be logged with admin's user_id."""
    target_id = user_with_pending_kyc["user"]["id"]
    # Approve the KYC
    client.post(f"/api/admin/kyc/{target_id}/approve", json={},
                headers=admin_user["headers"])
    # Look up the audit log
    r = client.get(f"/api/admin/audit-logs?user_id={admin_user['user'].id}&action=kyc_approve",
                   headers=admin_user["headers"])
    items = r.json()["items"]
    assert len(items) >= 1
    assert items[0]["action"] == "kyc_approve"
    assert items[0]["user_id"] == admin_user["user"].id
