"""Webhook schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.webhook import DeliveryStatus, WebhookStatus


class WebhookCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    url: HttpUrl
    # Comma-separated event types; empty string = all events
    subscribed_events: str = Field("", max_length=500)


class WebhookUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    url: Optional[HttpUrl] = None
    subscribed_events: Optional[str] = Field(None, max_length=500)
    status: Optional[WebhookStatus] = None


class WebhookOut(BaseModel):
    """Webhook subscription view — secret is included so user can copy it
    for verifying signatures on their receiver."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    secret: str  # shown once on creation; user must copy it
    subscribed_events: str
    status: WebhookStatus
    created_at: datetime
    updated_at: datetime


class WebhookDeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    webhook_id: int
    event_id: str
    event_type: str
    payload: str
    status: DeliveryStatus
    attempt_count: int
    response_status_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    last_attempt_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None


class WebhookEventTypeInfo(BaseModel):
    """Static info about an event type, for the UI."""

    name: str
    description: str
    sample_data_keys: list[str]
