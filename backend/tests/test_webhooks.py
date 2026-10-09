"""Webhook tests — subscription CRUD, dispatch, HMAC signing, retry, delivery persistence."""
from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import socketserver
import threading
import time

from app.models.webhook import WebhookStatus


# ── CRUD ──────────────────────────────────────────────────────────
def test_create_webhook_returns_secret(client, registered_user):
    r = client.post(
        "/api/webhooks",
        json={
            "name": "My webhook",
            "url": "https://example.com/hook",
            "subscribed_events": "transaction.deposit",
        },
        headers=registered_user["headers"],
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "My webhook"
    assert body["url"] == "https://example.com/hook"
    assert body["secret"]  # auto-generated
    assert len(body["secret"]) >= 32
    assert body["status"] == "active"


def test_list_my_webhooks(client, registered_user):
    client.post("/api/webhooks", json={
        "name": "W1", "url": "https://example.com/1", "subscribed_events": "",
    }, headers=registered_user["headers"])
    client.post("/api/webhooks", json={
        "name": "W2", "url": "https://example.com/2", "subscribed_events": "",
    }, headers=registered_user["headers"])
    r = client.get("/api/webhooks", headers=registered_user["headers"])
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_cannot_view_other_users_webhook(client):
    a = client.post("/api/auth/register",
                    json={"full_name":"Alice","email":"a@orionbank.com","pin":"8421"}).json()
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob","email":"b@orionbank.com","pin":"7351"}).json()
    tok_a = client.post("/api/auth/login",
                        json={"email":"a@orionbank.com","pin":"8421"}).json()["access_token"]
    tok_b = client.post("/api/auth/login",
                        json={"email":"b@orionbank.com","pin":"7351"}).json()["access_token"]
    # A creates a webhook
    r = client.post("/api/webhooks", json={
        "name":"A's hook","url":"https://example.com/a","subscribed_events":"",
    }, headers={"Authorization": f"Bearer {tok_a}"})
    wid = r.json()["id"]
    # B tries to view it — should 404
    r = client.get(f"/api/webhooks/{wid}", headers={"Authorization": f"Bearer {tok_b}"})
    assert r.status_code == 404


def test_update_webhook_status(client, registered_user):
    r = client.post("/api/webhooks", json={
        "name":"WH","url":"https://example.com/h","subscribed_events":"",
    }, headers=registered_user["headers"])
    wid = r.json()["id"]
    r = client.patch(f"/api/webhooks/{wid}", json={"status": "paused"},
                     headers=registered_user["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "paused"


def test_rotate_secret(client, registered_user):
    r = client.post("/api/webhooks", json={
        "name":"WH","url":"https://example.com/h","subscribed_events":"",
    }, headers=registered_user["headers"])
    wid = r.json()["id"]
    old_secret = r.json()["secret"]
    r = client.post(f"/api/webhooks/{wid}/rotate-secret",
                    headers=registered_user["headers"])
    assert r.status_code == 200
    new_secret = r.json()["secret"]
    assert new_secret != old_secret
    assert len(new_secret) >= 32


def test_delete_webhook(client, registered_user):
    r = client.post("/api/webhooks", json={
        "name":"WH","url":"https://example.com/h","subscribed_events":"",
    }, headers=registered_user["headers"])
    wid = r.json()["id"]
    r = client.delete(f"/api/webhooks/{wid}", headers=registered_user["headers"])
    assert r.status_code == 204
    # Confirm gone
    r = client.get(f"/api/webhooks/{wid}", headers=registered_user["headers"])
    assert r.status_code == 404


# ── Dispatch + HMAC signing ───────────────────────────────────────
def _start_receiver(verb_handler=None):
    """Start a tiny HTTP server on a random port to receive webhooks."""
    received = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length)
            received.append({
                "headers": dict(self.headers),
                "body": body.decode("utf-8"),
            })
            if verb_handler:
                status, body_out = verb_handler(self)
            else:
                status, body_out = 200, b"ok"
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body_out)
        def log_message(self, *args, **kwargs):
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, received


def test_deposit_fires_webhook_with_hmac_signature(client):
    # Spin up a receiver
    server, port, received = _start_receiver()

    try:
        # Register + create webhook pointing at receiver
        c = client.post("/api/auth/register",
                        json={"full_name":"Alice","email":"alice@orionbank.com","pin":"8421"})
        tok = client.post("/api/auth/login",
                          json={"email":"alice@orionbank.com","pin":"8421"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}

        r = client.post("/api/webhooks", json={
            "name":"Test receiver",
            "url":f"http://127.0.0.1:{port}/hook",
            "subscribed_events":"transaction.deposit",
        }, headers=headers)
        secret = r.json()["secret"]
        wid = r.json()["id"]

        # Make a deposit — should trigger webhook
        client.post("/api/transactions/deposit",
                    json={"amount":100,"memo":"hook test"}, headers=headers)
        time.sleep(0.3)

        # Verify the receiver got exactly one POST
        assert len(received) == 1, f"Expected 1 webhook delivery, got {len(received)}"
        req = received[0]
        # HMAC signature present + valid
        sig_header = req["headers"].get("X-Orion-Signature", "")
        assert sig_header.startswith("sha256="), f"Bad signature header: {sig_header!r}"
        sig = sig_header.replace("sha256=", "")
        expected = hmac.new(secret.encode(), req["body"].encode(), hashlib.sha256).hexdigest()
        assert hmac.compare_digest(sig, expected), "HMAC signature mismatch"

        # Other headers
        assert req["headers"]["X-Orion-Event"] == "transaction.deposit"
        assert req["headers"]["Content-Type"] == "application/json"

        # Payload structure
        payload = json.loads(req["body"])
        assert payload["id"].startswith("evt_")
        assert payload["type"] == "transaction.deposit"
        assert payload["data"]["amount"] == 100.0
        assert payload["data"]["reference"].startswith("ORX-")
        assert "created_at" in payload

        # Delivery persisted
        r = client.get(f"/api/webhooks/{wid}/deliveries", headers=headers)
        deliveries = r.json()
        assert len(deliveries) == 1
        assert deliveries[0]["status"] == "delivered"
        assert deliveries[0]["response_status_code"] == 200
        assert deliveries[0]["attempt_count"] == 1
    finally:
        server.shutdown()


def test_event_filter_excludes_unsubscribed_events(client):
    """Webhook subscribed to deposit should NOT fire on withdrawal."""
    server, port, received = _start_receiver()

    try:
        client.post("/api/auth/register",
                    json={"full_name":"Alice","email":"alice@orionbank.com","pin":"8421"})
        tok = client.post("/api/auth/login",
                          json={"email":"alice@orionbank.com","pin":"8421"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}

        client.post("/api/webhooks", json={
            "name":"Deposits only",
            "url":f"http://127.0.0.1:{port}/hook",
            "subscribed_events":"transaction.deposit",
        }, headers=headers)
        # Deposit money first
        client.post("/api/transactions/deposit", json={"amount":500}, headers=headers)
        time.sleep(0.3)
        received.clear()
        # Withdraw — should NOT fire webhook
        client.post("/api/transactions/withdraw", json={"amount":50}, headers=headers)
        time.sleep(0.3)
        assert len(received) == 0, "Withdrawal should not have triggered deposit-only webhook"
    finally:
        server.shutdown()


def test_subscribe_to_all_events_fires_for_every_event(client):
    """Empty subscribed_events = all events."""
    server, port, received = _start_receiver()
    try:
        client.post("/api/auth/register",
                    json={"full_name":"Alice","email":"alice@orionbank.com","pin":"8421"})
        tok = client.post("/api/auth/login",
                          json={"email":"alice@orionbank.com","pin":"8421"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}
        client.post("/api/webhooks", json={
            "name":"All events",
            "url":f"http://127.0.0.1:{port}/hook",
            "subscribed_events":"",
        }, headers=headers)
        client.post("/api/transactions/deposit", json={"amount":100}, headers=headers)
        client.post("/api/transactions/withdraw", json={"amount":50}, headers=headers)
        time.sleep(0.4)
        assert len(received) == 2
        events = sorted([json.loads(r["body"])["type"] for r in received])
        assert events == ["transaction.deposit", "transaction.withdrawal"]
    finally:
        server.shutdown()


def test_test_ping_sends_ping_event(client, registered_user):
    server, port, received = _start_receiver()
    try:
        r = client.post("/api/webhooks", json={
            "name":"WH","url":f"http://127.0.0.1:{port}/hook","subscribed_events":"",
        }, headers=registered_user["headers"])
        wid = r.json()["id"]

        r = client.post(f"/api/webhooks/{wid}/test", headers=registered_user["headers"])
        assert r.status_code == 200
        assert r.json()["event_type"] == "ping"
        time.sleep(0.3)
        assert len(received) == 1
        payload = json.loads(received[0]["body"])
        assert payload["type"] == "ping"
        assert payload["data"]["webhook_id"] == wid
    finally:
        server.shutdown()


def test_paused_webhook_does_not_fire(client, registered_user):
    server, port, received = _start_receiver()
    try:
        r = client.post("/api/webhooks", json={
            "name":"WH","url":f"http://127.0.0.1:{port}/hook","subscribed_events":"",
        }, headers=registered_user["headers"])
        wid = r.json()["id"]
        # Pause it
        client.patch(f"/api/webhooks/{wid}", json={"status":"paused"},
                     headers=registered_user["headers"])
        # Make a deposit
        client.post("/api/transactions/deposit", json={"amount":100},
                    headers=registered_user["headers"])
        time.sleep(0.3)
        # Receiver should NOT have received anything
        assert len(received) == 0
        # Delivery history should also be empty (no deliveries created)
        r = client.get(f"/api/webhooks/{wid}/deliveries",
                       headers=registered_user["headers"])
        assert len(r.json()) == 0
    finally:
        server.shutdown()


def test_failed_delivery_records_status_code(client, registered_user):
    """Receiver returns 500 — delivery should be marked failed after retries."""
    def handler(self):
        return 500, b"Internal error"
    server, port, received = _start_receiver(verb_handler=handler)
    try:
        r = client.post("/api/webhooks", json={
            "name":"WH","url":f"http://127.0.0.1:{port}/hook","subscribed_events":"",
        }, headers=registered_user["headers"])
        wid = r.json()["id"]
        client.post("/api/transactions/deposit", json={"amount":100},
                    headers=registered_user["headers"])
        time.sleep(1.0)  # retries take time
        # Should have made 3 attempts (max_attempts)
        assert len(received) == 3, f"Expected 3 retry attempts, got {len(received)}"
        # Delivery should be marked failed
        deliveries = client.get(f"/api/webhooks/{wid}/deliveries",
                                headers=registered_user["headers"]).json()
        # Each attempt creates a new delivery row OR updates the existing one —
        # our impl updates in place, so there's 1 delivery with attempt_count=3
        assert len(deliveries) == 1
        assert deliveries[0]["status"] == "failed"
        assert deliveries[0]["attempt_count"] == 3
        assert deliveries[0]["response_status_code"] == 500
        assert deliveries[0]["error_message"] is not None
    finally:
        server.shutdown()


def test_4xx_does_not_retry(client, registered_user):
    """Receiver returns 404 — should NOT retry (4xx is permanent)."""
    def handler(self):
        return 404, b"Not found"
    server, port, received = _start_receiver(verb_handler=handler)
    try:
        client.post("/api/webhooks", json={
            "name":"WH","url":f"http://127.0.0.1:{port}/hook","subscribed_events":"",
        }, headers=registered_user["headers"])
        client.post("/api/transactions/deposit", json={"amount":100},
                    headers=registered_user["headers"])
        time.sleep(0.5)
        # Should have made exactly 1 attempt (no retry on 4xx)
        assert len(received) == 1, f"Expected 1 attempt (no retry on 4xx), got {len(received)}"
    finally:
        server.shutdown()


def test_transfer_fires_two_webhooks_when_both_parties_subscribed(client):
    """Both sender + recipient get their own webhook event."""
    server_a, port_a, received_a = _start_receiver()
    server_b, port_b, received_b = _start_receiver()
    try:
        a = client.post("/api/auth/register",
                        json={"full_name":"Alice","email":"alice@orionbank.com","pin":"8421"}).json()
        b = client.post("/api/auth/register",
                        json={"full_name":"Bob","email":"bob@orionbank.com","pin":"7351"}).json()
        tok_a = client.post("/api/auth/login",
                            json={"email":"alice@orionbank.com","pin":"8421"}).json()["access_token"]
        tok_b = client.post("/api/auth/login",
                            json={"email":"bob@orionbank.com","pin":"7351"}).json()["access_token"]
        # Both subscribe to transfer events
        client.post("/api/webhooks", json={
            "name":"A","url":f"http://127.0.0.1:{port_a}/a","subscribed_events":"transaction.transfer.out",
        }, headers={"Authorization": f"Bearer {tok_a}"})
        client.post("/api/webhooks", json={
            "name":"B","url":f"http://127.0.0.1:{port_b}/b","subscribed_events":"transaction.transfer.in",
        }, headers={"Authorization": f"Bearer {tok_b}"})
        # Alice deposits money
        client.post("/api/transactions/deposit", json={"amount":1000},
                    headers={"Authorization": f"Bearer {tok_a}"})
        # Alice transfers to Bob
        client.post("/api/transactions/transfer", json={
            "recipient_account_number": b["account_number"], "amount": 200,
        }, headers={"Authorization": f"Bearer {tok_a}"})
        time.sleep(0.4)
        # Alice got transfer.out, Bob got transfer.in
        assert len(received_a) == 1, f"Alice should have 1 delivery, got {len(received_a)}"
        assert len(received_b) == 1, f"Bob should have 1 delivery, got {len(received_b)}"
        a_type = json.loads(received_a[0]["body"])["type"]
        b_type = json.loads(received_b[0]["body"])["type"]
        assert a_type == "transaction.transfer.out"
        assert b_type == "transaction.transfer.in"
    finally:
        server_a.shutdown()
        server_b.shutdown()


def test_redeliver_creates_new_delivery(client, registered_user):
    server, port, received = _start_receiver()
    try:
        r = client.post("/api/webhooks", json={
            "name":"WH","url":f"http://127.0.0.1:{port}/hook","subscribed_events":"",
        }, headers=registered_user["headers"])
        wid = r.json()["id"]
        # Make a deposit so we have a delivery
        client.post("/api/transactions/deposit", json={"amount":100},
                    headers=registered_user["headers"])
        time.sleep(0.3)
        # Get the delivery id
        deliveries = client.get(f"/api/webhooks/{wid}/deliveries",
                                headers=registered_user["headers"]).json()
        orig_id = deliveries[0]["id"]
        # Redeliver
        received.clear()
        r = client.post(f"/api/webhooks/deliveries/{orig_id}/redeliver",
                        headers=registered_user["headers"])
        assert r.status_code == 200
        time.sleep(0.3)
        # Receiver should have gotten 1 more request
        assert len(received) == 1
    finally:
        server.shutdown()


def test_kyc_approval_fires_webhook(client, admin_user, user_with_pending_kyc):
    server, port, received = _start_receiver()
    try:
        # User creates a webhook for KYC events
        client.post("/api/webhooks", json={
            "name":"WH","url":f"http://127.0.0.1:{port}/hook",
            "subscribed_events":"kyc.approved,kyc.rejected",
        }, headers=user_with_pending_kyc["headers"])
        # Admin approves
        target_id = user_with_pending_kyc["user"]["id"]
        client.post(f"/api/admin/kyc/{target_id}/approve", json={},
                    headers=admin_user["headers"])
        time.sleep(0.3)
        assert len(received) == 1
        payload = json.loads(received[0]["body"])
        assert payload["type"] == "kyc.approved"
        assert payload["data"]["user_id"] == target_id
        assert "reviewed_by" in payload["data"]
    finally:
        server.shutdown()
