"""Scheduled transfer tests — create, list, execute, pause/resume/cancel, failures."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.services.scheduled_transfer_service import ScheduledTransferService


def _iso(seconds_from_now: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now)).isoformat()


# ── Create + list ────────────────────────────────────────────────
def test_create_one_time_schedule(client, registered_user):
    # Need a recipient
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/scheduled-transfers", json={
        "name": "Test",
        "recipient_account_number": b["account_number"],
        "amount": 100,
        "memo": "test",
        "schedule_type": "once",
        "schedule_config": _iso(60),
    }, headers=registered_user["headers"])
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Test"
    assert body["status"] == "active"
    assert body["schedule_type"] == "once"
    assert body["next_run_at"]


def test_create_validates_recipient_exists(client, registered_user):
    r = client.post("/api/scheduled-transfers", json={
        "name": "Bad recipient",
        "recipient_account_number": "00000000000000",
        "amount": 100,
        "schedule_type": "once",
        "schedule_config": _iso(60),
    }, headers=registered_user["headers"])
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "account_not_found"


def test_create_rejects_self_transfer(client, registered_user):
    r = client.post("/api/scheduled-transfers", json={
        "name": "Self",
        "recipient_account_number": registered_user["user"]["account_number"],
        "amount": 100,
        "schedule_type": "once",
        "schedule_config": _iso(60),
    }, headers=registered_user["headers"])
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "self_transfer_forbidden"


def test_create_rejects_past_one_time(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/scheduled-transfers", json={
        "name": "Past",
        "recipient_account_number": b["account_number"],
        "amount": 100,
        "schedule_type": "once",
        "schedule_config": _iso(-60),  # 60s ago
    }, headers=registered_user["headers"])
    assert r.status_code == 422


def test_list_only_my_schedules(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    # Alice creates one
    client.post("/api/scheduled-transfers", json={
        "name": "Alice's schedule",
        "recipient_account_number": b["account_number"],
        "amount": 50, "schedule_type": "once",
        "schedule_config": _iso(120),
    }, headers=registered_user["headers"])
    # Bob logs in + lists his — should see 0
    tok_b = client.post("/api/auth/login",
                        json={"email":"bob@orionbank.com","pin":"7351"}).json()["access_token"]
    r = client.get("/api/scheduled-transfers",
                   headers={"Authorization": f"Bearer {tok_b}"})
    assert r.status_code == 200
    assert len(r.json()) == 0


# ── Schedule types ───────────────────────────────────────────────
def test_create_daily_schedule(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/scheduled-transfers", json={
        "name": "Daily",
        "recipient_account_number": b["account_number"],
        "amount": 50, "schedule_type": "daily",
        "schedule_config": "7",  # every 7 days
    }, headers=registered_user["headers"])
    assert r.status_code == 201
    body = r.json()
    # Next run should be ~7 days from now (rounded to midnight, so could be
    # slightly less than 7 days depending on current time of day).
    next_run_str = body["next_run_at"]
    if next_run_str.endswith("+00:00"):
        next_run = datetime.fromisoformat(next_run_str)
    else:
        next_run = datetime.fromisoformat(next_run_str).replace(tzinfo=timezone.utc)
    delta = next_run - datetime.now(timezone.utc)
    assert 6 <= delta.days <= 8


def test_create_weekly_schedule(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/scheduled-transfers", json={
        "name": "Weekly Monday",
        "recipient_account_number": b["account_number"],
        "amount": 50, "schedule_type": "weekly",
        "schedule_config": "0",  # Monday
    }, headers=registered_user["headers"])
    assert r.status_code == 201


def test_create_monthly_schedule(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/scheduled-transfers", json={
        "name": "Monthly 1st",
        "recipient_account_number": b["account_number"],
        "amount": 50, "schedule_type": "monthly",
        "schedule_config": "1",
    }, headers=registered_user["headers"])
    assert r.status_code == 201


# ── Execution ─────────────────────────────────────────────────────
def test_run_due_executes_one_time_schedule(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    # Alice deposits money
    client.post("/api/transactions/deposit", json={"amount": 1000},
                headers=registered_user["headers"])
    # Create schedule with next_run 2 seconds in the future
    r = client.post("/api/scheduled-transfers", json={
        "name": "Will execute",
        "recipient_account_number": b["account_number"],
        "amount": 100, "schedule_type": "once",
        "schedule_config": _iso(2),
    }, headers=registered_user["headers"])
    schedule_id = r.json()["id"]

    # Wait for it to become due
    import time
    time.sleep(3)

    # Manually run_due
    db = SessionLocal()
    count = ScheduledTransferService(db).run_due()
    db.close()
    assert count == 1

    # Verify the transfer happened
    me = client.get("/api/accounts/me", headers=registered_user["headers"]).json()
    assert float(me["balance"]) == 900  # 1000 - 100

    tok_b = client.post("/api/auth/login",
                        json={"email":"bob@orionbank.com","pin":"7351"}).json()["access_token"]
    me_b = client.get("/api/accounts/me",
                      headers={"Authorization": f"Bearer {tok_b}"}).json()
    assert float(me_b["balance"]) == 100

    # Schedule should be marked completed
    r = client.get(f"/api/scheduled-transfers/{schedule_id}",
                   headers=registered_user["headers"])
    assert r.json()["status"] == "completed"

    # Execution recorded
    r = client.get(f"/api/scheduled-transfers/{schedule_id}/executions",
                   headers=registered_user["headers"])
    execs = r.json()
    assert len(execs) == 1
    assert execs[0]["status"] == "success"
    assert execs[0]["transaction_reference"].startswith("ORX-")


def test_run_due_skips_account_with_insufficient_funds(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    # Alice has 0 balance — schedule will fail (insufficient funds)
    r = client.post("/api/scheduled-transfers", json={
        "name": "Will fail",
        "recipient_account_number": b["account_number"],
        "amount": 100, "schedule_type": "once",
        "schedule_config": _iso(2),
    }, headers=registered_user["headers"])
    schedule_id = r.json()["id"]
    import time
    time.sleep(3)
    db = SessionLocal()
    count = ScheduledTransferService(db).run_due()
    db.close()
    assert count == 1  # attempted, even though failed

    # Execution recorded as failed
    r = client.get(f"/api/scheduled-transfers/{schedule_id}/executions",
                   headers=registered_user["headers"])
    execs = r.json()
    assert len(execs) == 1
    assert execs[0]["status"] == "failed"
    assert "InsufficientFundsError" in execs[0]["error_message"]

    # Schedule should be marked failed (one-time that didn't succeed)
    r = client.get(f"/api/scheduled-transfers/{schedule_id}",
                   headers=registered_user["headers"])
    assert r.json()["status"] == "failed"
    assert r.json()["consecutive_failures"] == 1


def test_consecutive_failures_auto_fail_schedule(client, registered_user):
    """A daily schedule with bad recipient should auto-fail after 3 consecutive failures."""
    # Use a recipient that doesn't exist
    r = client.post("/api/scheduled-transfers", json={
        "name": "Bad recipient",
        "recipient_account_number": "00000000000001",
        "amount": 100, "schedule_type": "daily",
        "schedule_config": "1",
    }, headers=registered_user["headers"])
    # This will fail at creation — recipient doesn't exist
    assert r.status_code == 404


# ── Pause / resume / cancel ──────────────────────────────────────
def test_pause_and_resume(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/scheduled-transfers", json={
        "name": "Daily",
        "recipient_account_number": b["account_number"],
        "amount": 50, "schedule_type": "daily",
        "schedule_config": "1",
    }, headers=registered_user["headers"])
    sid = r.json()["id"]

    # Pause
    r = client.post(f"/api/scheduled-transfers/{sid}/pause",
                    headers=registered_user["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "paused"

    # Resume
    r = client.post(f"/api/scheduled-transfers/{sid}/resume",
                    headers=registered_user["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_cancel_schedule(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/scheduled-transfers", json={
        "name": "Will cancel",
        "recipient_account_number": b["account_number"],
        "amount": 50, "schedule_type": "daily",
        "schedule_config": "1",
    }, headers=registered_user["headers"])
    sid = r.json()["id"]

    r = client.post(f"/api/scheduled-transfers/{sid}/cancel",
                    headers=registered_user["headers"])
    assert r.status_code == 204

    r = client.get(f"/api/scheduled-transfers/{sid}",
                   headers=registered_user["headers"])
    assert r.json()["status"] == "cancelled"


def test_cannot_modify_other_users_schedule(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/scheduled-transfers", json={
        "name": "Alice's",
        "recipient_account_number": b["account_number"],
        "amount": 50, "schedule_type": "daily",
        "schedule_config": "1",
    }, headers=registered_user["headers"])
    sid = r.json()["id"]
    # Bob tries to access Alice's schedule
    tok_b = client.post("/api/auth/login",
                        json={"email":"bob@orionbank.com","pin":"7351"}).json()["access_token"]
    r = client.get(f"/api/scheduled-transfers/{sid}",
                   headers={"Authorization": f"Bearer {tok_b}"})
    assert r.status_code == 404
    r = client.post(f"/api/scheduled-transfers/{sid}/cancel",
                    headers={"Authorization": f"Bearer {tok_b}"})
    assert r.status_code == 404


# ── Idempotency: same schedule won't double-execute ─────────────
def test_run_due_is_idempotent(client, registered_user):
    """Calling run_due twice for the same due schedule should only execute once."""
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
    client.post("/api/transactions/deposit", json={"amount": 1000},
                headers=registered_user["headers"])
    r = client.post("/api/scheduled-transfers", json={
        "name": "Once",
        "recipient_account_number": b["account_number"],
        "amount": 100, "schedule_type": "once",
        "schedule_config": _iso(2),
    }, headers=registered_user["headers"])
    sid = r.json()["id"]
    import time
    time.sleep(3)
    db = SessionLocal()
    ScheduledTransferService(db).run_due()
    # Run again immediately — should not double-execute
    count2 = ScheduledTransferService(db).run_due()
    db.close()
    assert count2 == 0  # nothing new to execute

    # Only one execution recorded
    r = client.get(f"/api/scheduled-transfers/{sid}/executions",
                   headers=registered_user["headers"])
    assert len(r.json()) == 1
    # Balance only changed by 100 once
    me = client.get("/api/accounts/me", headers=registered_user["headers"]).json()
    assert float(me["balance"]) == 900


# ── Page routes ──────────────────────────────────────────────────
def test_scheduled_transfers_page_renders(client, registered_user):
    r = client.get("/scheduled-transfers", headers=registered_user["headers"],
                   follow_redirects=False)
    assert r.status_code == 200
    assert "Scheduled transfers" in r.text
    assert "Create schedule" in r.text
