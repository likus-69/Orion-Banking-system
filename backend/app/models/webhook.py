"""Webhook subscription + delivery models."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WebhookStatus(str, enum.Enum):
    """Lifecycle of a webhook subscription."""

    active = "active"
    paused = "paused"
    disabled = "disabled"


class DeliveryStatus(str, enum.Enum):
    """Outcome of a single delivery attempt."""

    pending = "pending"
    delivered = "delivered"
    failed = "failed"


class WebhookSubscription(Base):
    """A user's subscription to receive webhook events at a URL."""

    __tablename__ = "webhook_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Friendly name for the user to identify this webhook
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Target URL — must be HTTPS in production (configurable)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # HMAC secret used to sign payloads (stored in plaintext; the secret
    # is shared with the receiver so they can verify signatures).
    secret: Mapped[str] = mapped_column(String(255), nullable=False)

    # Comma-separated event types this subscription listens to.
    # Empty string means "all events".
    subscribed_events: Mapped[str] = mapped_column(Text, default="", nullable=False)

    status: Mapped[WebhookStatus] = mapped_column(
        Enum(WebhookStatus, name="webhook_status"),
        default=WebhookStatus.active,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )

    # ── Helpers ──────────────────────────────────────────────────
    def is_subscribed_to(self, event_type: str) -> bool:
        """Returns True if this subscription wants the given event type."""
        if not self.subscribed_events.strip():
            return True  # empty = all events
        events = [e.strip() for e in self.subscribed_events.split(",") if e.strip()]
        return event_type in events


class WebhookDelivery(Base):
    """Persisted record of a single delivery attempt (one per retry)."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    webhook_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Event id (stable, used by receiver for idempotency)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # The full payload as JSON (so we can redeliver later)
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="webhook_delivery_status"),
        default=DeliveryStatus.pending,
        nullable=False,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False, index=True)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    subscription: Mapped[WebhookSubscription] = relationship(back_populates="deliveries")
