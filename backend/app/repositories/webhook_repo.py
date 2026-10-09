"""Webhook repository — data access for WebhookSubscription + WebhookDelivery."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.webhook import (
    DeliveryStatus,
    WebhookDelivery,
    WebhookStatus,
    WebhookSubscription,
)
from app.repositories.base import BaseRepository


class WebhookRepository:
    """Data access for webhook subscriptions + deliveries."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Subscriptions ────────────────────────────────────────────
    def list_for_user(self, user_id: int) -> list[WebhookSubscription]:
        return (
            self.db.query(WebhookSubscription)
            .filter(WebhookSubscription.user_id == user_id)
            .order_by(WebhookSubscription.created_at.desc())
            .all()
        )

    def get_for_user(self, user_id: int, webhook_id: int) -> Optional[WebhookSubscription]:
        return (
            self.db.query(WebhookSubscription)
            .filter(
                WebhookSubscription.id == webhook_id,
                WebhookSubscription.user_id == user_id,
            )
            .first()
        )

    def list_active_for_user(self, user_id: int) -> list[WebhookSubscription]:
        return (
            self.db.query(WebhookSubscription)
            .filter(
                WebhookSubscription.user_id == user_id,
                WebhookSubscription.status == WebhookStatus.active,
            )
            .all()
        )

    # ── Deliveries ───────────────────────────────────────────────
    def create_delivery(
        self, *, webhook_id: int, event_id: str, event_type: str, payload: str
    ) -> WebhookDelivery:
        d = WebhookDelivery(
            webhook_id=webhook_id,
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            status=DeliveryStatus.pending,
            attempt_count=0,
        )
        self.db.add(d)
        self.db.flush()
        return d

    def list_deliveries(self, webhook_id: int, *, limit: int = 50) -> list[WebhookDelivery]:
        return (
            self.db.query(WebhookDelivery)
            .filter(WebhookDelivery.webhook_id == webhook_id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
            .all()
        )
