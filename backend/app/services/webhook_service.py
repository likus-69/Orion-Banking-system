"""Webhook service — dispatch events to user-registered URLs.

For each event:
1. Find all active subscriptions matching the event type
2. For each, build a payload + HMAC signature
3. Persist a WebhookDelivery row (status=pending)
4. POST the payload via background task with retry (max 3 attempts)

HMAC signature: SHA-256 of payload using the webhook's secret,
sent in the `X-Orion-Signature` header (hex-encoded). Receivers should
re-compute and compare to verify authenticity.

Payload shape:
    {
      "id": "evt_<hex>",            # stable event id for idempotency
      "type": "transaction.deposit",
      "created_at": "2024-10-07T...",
      "data": { ...event-specific... }
    }
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.logging_config import get_logger
from app.models.webhook import (
    DeliveryStatus,
    WebhookDelivery,
    WebhookStatus,
    WebhookSubscription,
)
from app.repositories.webhook_repo import WebhookRepository
from app.services.audit_service import AuditService

log = get_logger(__name__)


# Event constants — kept in sync with the docs and the JS frontend.
class WebhookEvents:
    TRANSACTION_DEPOSIT = "transaction.deposit"
    TRANSACTION_WITHDRAWAL = "transaction.withdrawal"
    TRANSACTION_TRANSFER_IN = "transaction.transfer.in"
    TRANSACTION_TRANSFER_OUT = "transaction.transfer.out"
    KYC_APPROVED = "kyc.approved"
    KYC_REJECTED = "kyc.rejected"
    SCHEDULED_TRANSFER_EXECUTED = "scheduled_transfer.executed"
    SCHEDULED_TRANSFER_FAILED = "scheduled_transfer.failed"

    ALL = [
        TRANSACTION_DEPOSIT,
        TRANSACTION_WITHDRAWAL,
        TRANSACTION_TRANSFER_IN,
        TRANSACTION_TRANSFER_OUT,
        KYC_APPROVED,
        KYC_REJECTED,
        SCHEDULED_TRANSFER_EXECUTED,
        SCHEDULED_TRANSFER_FAILED,
    ]


def _generate_event_id() -> str:
    return "evt_" + secrets.token_hex(12)


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """HMAC-SHA256 of payload using secret. Returns hex digest."""
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _serialize(obj: Any) -> Any:
    """JSON-safe conversion for arbitrary objects (SQLAlchemy models, enums, etc.)."""
    if hasattr(obj, "value"):  # enums
        return obj.value
    if hasattr(obj, "isoformat"):  # datetimes
        return obj.isoformat()
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if hasattr(obj, "__dict__"):
        return {k: _serialize(v) for k, v in vars(obj).items() if not k.startswith("_")}
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    return str(obj)


class WebhookService:
    """Dispatch webhook events to subscribed URLs."""

    def __init__(self, db: Session, background_tasks=None) -> None:
        self.db = db
        self.background_tasks = background_tasks
        self.repo = WebhookRepository(db)
        self.audit = AuditService(db)

    # ── Dispatch ────────────────────────────────────────────────
    def dispatch(self, event_type: str, *, user_id: int, data: dict) -> None:
        """Find matching subscriptions and schedule deliveries.

        Safe to call from a route handler — does not block. Dispatch happens
        in background tasks; any failure is logged but never raised.
        """
        subscriptions = self.repo.list_active_for_user(user_id)
        if not subscriptions:
            return

        matching = [s for s in subscriptions if s.is_subscribed_to(event_type)]
        if not matching:
            return

        event_id = _generate_event_id()
        created_at = datetime.now(timezone.utc).isoformat()
        payload = json.dumps({
            "id": event_id,
            "type": event_type,
            "created_at": created_at,
            "data": _serialize(data),
        }, default=str, separators=(",", ":"))

        for sub in matching:
            delivery = self.repo.create_delivery(
                webhook_id=sub.id,
                event_id=event_id,
                event_type=event_type,
                payload=payload,
            )
            if self.background_tasks is not None:
                self.background_tasks.add_task(
                    self._deliver, delivery_id=delivery.id, secret=sub.secret, url=sub.url
                )
            else:
                # Synchronous (tests)
                self._deliver(delivery_id=delivery.id, secret=sub.secret, url=sub.url)

        self.db.commit()
        log.info("webhook.dispatched", event_type=event_type, user_id=user_id,
                 deliveries=len(matching))

    def _deliver(self, *, delivery_id: int, secret: str, url: str) -> None:
        """Actually POST the payload to the URL with retries."""
        # Use a fresh session — background tasks run after the request's
        # session has been closed.
        from app.database import SessionLocal

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            db = SessionLocal()
            try:
                delivery = db.get(WebhookDelivery, delivery_id)
                if delivery is None:
                    log.warning("webhook.delivery_not_found", delivery_id=delivery_id)
                    return

                subscription = delivery.subscription
                if subscription is None or subscription.status != WebhookStatus.active:
                    log.info("webhook.skip_inactive", delivery_id=delivery_id)
                    return

                payload_bytes = delivery.payload.encode("utf-8")
                signature = _sign_payload(payload_bytes, secret)

                headers = {
                    "Content-Type": "application/json",
                    "X-Orion-Signature": f"sha256={signature}",
                    "X-Orion-Event": delivery.event_type,
                    "X-Orion-Delivery": str(delivery.id),
                    "User-Agent": f"Orion-Banking-Webhooks/1.0",
                }

                delivery.attempt_count = attempt
                delivery.last_attempt_at = datetime.now(timezone.utc)

                try:
                    req = urllib.request.Request(
                        subscription.url,
                        data=payload_bytes,
                        headers=headers,
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        delivery.response_status_code = resp.status
                        try:
                            delivery.response_body = resp.read(2048).decode("utf-8", errors="replace")
                        except Exception:
                            delivery.response_body = None

                        if 200 <= resp.status < 300:
                            delivery.status = DeliveryStatus.delivered
                            delivery.delivered_at = datetime.now(timezone.utc)
                            db.commit()
                            log.info("webhook.delivered",
                                     delivery_id=delivery.id,
                                     status=resp.status,
                                     attempts=attempt)
                            return
                        else:
                            delivery.error_message = f"HTTP {resp.status}"
                            # 4xx is permanent — no retry
                            if 400 <= resp.status < 500:
                                delivery.status = DeliveryStatus.failed
                                db.commit()
                                log.warning("webhook.4xx_no_retry",
                                            delivery_id=delivery.id, status=resp.status)
                                return
                except urllib.error.HTTPError as e:
                    delivery.response_status_code = e.code
                    try:
                        delivery.response_body = e.read(2048).decode("utf-8", errors="replace")
                    except Exception:
                        pass
                    delivery.error_message = f"HTTPError: {e.code} {e.reason}"
                    if 400 <= e.code < 500:
                        delivery.status = DeliveryStatus.failed
                        db.commit()
                        return
                except Exception as e:
                    delivery.error_message = f"{type(e).__name__}: {e}"

                db.commit()

                if attempt < max_attempts:
                    # Exponential backoff: 2s, 8s, 32s — but we're synchronous
                    # in background tasks, so just retry immediately for the demo.
                    # In production, defer to a real queue (Celery / RQ).
                    continue

                # Out of retries
                delivery.status = DeliveryStatus.failed
                db.commit()
                log.warning("webhook.failed_final",
                             delivery_id=delivery.id, attempts=attempt)
                return
            finally:
                db.close()

    # ── Subscription CRUD ───────────────────────────────────────
    def list_subscriptions(self, user_id: int) -> list[WebhookSubscription]:
        return self.repo.list_for_user(user_id)

    def get_subscription(self, user_id: int, webhook_id: int) -> Optional[WebhookSubscription]:
        return self.repo.get_for_user(user_id, webhook_id)

    def create_subscription(
        self, user_id: int, *, name: str, url: str, subscribed_events: str = "",
    ) -> WebhookSubscription:
        secret = secrets.token_urlsafe(32)
        sub = WebhookSubscription(
            user_id=user_id,
            name=name.strip()[:255],
            url=url.strip()[:2048],
            secret=secret,
            subscribed_events=subscribed_events,
            status=WebhookStatus.active,
        )
        self.db.add(sub)
        self.db.flush()
        self.audit.log(
            user_id=user_id,
            action="webhook_created",
            details=f"Created webhook '{sub.name}' for URL {sub.url}",
        )
        self.db.commit()
        self.db.refresh(sub)
        log.info("webhook.created", webhook_id=sub.id, user_id=user_id)
        return sub

    def update_subscription(
        self, user_id: int, webhook_id: int, *,
        name: Optional[str] = None,
        url: Optional[str] = None,
        subscribed_events: Optional[str] = None,
        status: Optional[WebhookStatus] = None,
    ) -> Optional[WebhookSubscription]:
        sub = self.repo.get_for_user(user_id, webhook_id)
        if sub is None:
            return None
        if name is not None:
            sub.name = name.strip()[:255]
        if url is not None:
            sub.url = url.strip()[:2048]
        if subscribed_events is not None:
            sub.subscribed_events = subscribed_events
        if status is not None:
            sub.status = status
        self.audit.log(
            user_id=user_id,
            action="webhook_updated",
            details=f"Updated webhook id={webhook_id}",
        )
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def delete_subscription(self, user_id: int, webhook_id: int) -> bool:
        sub = self.repo.get_for_user(user_id, webhook_id)
        if sub is None:
            return False
        self.audit.log(
            user_id=user_id,
            action="webhook_deleted",
            details=f"Deleted webhook '{sub.name}' (id={webhook_id})",
        )
        self.db.delete(sub)
        self.db.commit()
        return True

    def rotate_secret(self, user_id: int, webhook_id: int) -> Optional[str]:
        sub = self.repo.get_for_user(user_id, webhook_id)
        if sub is None:
            return None
        new_secret = secrets.token_urlsafe(32)
        sub.secret = new_secret
        self.audit.log(
            user_id=user_id,
            action="webhook_secret_rotated",
            details=f"Rotated secret for webhook id={webhook_id}",
        )
        self.db.commit()
        return new_secret

    # ── Delivery history ────────────────────────────────────────
    def list_deliveries(
        self, user_id: int, webhook_id: int, *, limit: int = 50
    ) -> Optional[list[WebhookDelivery]]:
        sub = self.repo.get_for_user(user_id, webhook_id)
        if sub is None:
            return None
        return self.repo.list_deliveries(webhook_id, limit=limit)

    def redeliver(self, user_id: int, delivery_id: int) -> bool:
        """Re-send an existing delivery (creates a new pending delivery row)."""
        from app.models.webhook import WebhookSubscription
        delivery = self.db.get(WebhookDelivery, delivery_id)
        if delivery is None:
            return False
        sub = delivery.subscription
        if sub is None or sub.user_id != user_id:
            return False

        new_delivery = self.repo.create_delivery(
            webhook_id=sub.id,
            event_id=delivery.event_id,
            event_type=delivery.event_type,
            payload=delivery.payload,
        )
        self.db.commit()
        if self.background_tasks is not None:
            self.background_tasks.add_task(
                self._deliver, delivery_id=new_delivery.id, secret=sub.secret, url=sub.url
            )
        else:
            self._deliver(delivery_id=new_delivery.id, secret=sub.secret, url=sub.url)
        return True

    # ── Test ping ───────────────────────────────────────────────
    def send_test_event(self, user_id: int, webhook_id: int) -> Optional[WebhookDelivery]:
        """Send a test ping so users can verify their receiver is set up correctly."""
        sub = self.repo.get_for_user(user_id, webhook_id)
        if sub is None:
            return None

        event_id = _generate_event_id()
        payload = json.dumps({
            "id": event_id,
            "type": "ping",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data": {
                "message": "Test ping from Orion Banking webhooks",
                "webhook_id": sub.id,
                "webhook_name": sub.name,
            },
        }, default=str, separators=(",", ":"))

        delivery = self.repo.create_delivery(
            webhook_id=sub.id,
            event_id=event_id,
            event_type="ping",
            payload=payload,
        )
        self.db.commit()

        if self.background_tasks is not None:
            self.background_tasks.add_task(
                self._deliver, delivery_id=delivery.id, secret=sub.secret, url=sub.url
            )
        else:
            self._deliver(delivery_id=delivery.id, secret=sub.secret, url=sub.url)
        return delivery
