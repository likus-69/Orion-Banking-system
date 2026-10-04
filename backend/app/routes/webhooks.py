"""Webhook API routes — CRUD + delivery history + test ping + redeliver."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.user import User
from app.models.webhook import WebhookStatus
from app.schemas.webhook import (
    WebhookCreateRequest,
    WebhookDeliveryOut,
    WebhookOut,
    WebhookUpdateRequest,
)
from app.services.webhook_service import WebhookService

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.get("", response_model=list[WebhookOut])
def list_my_webhooks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WebhookService(db)
    return service.list_subscriptions(current_user.id)


@router.post("", response_model=WebhookOut, status_code=status.HTTP_201_CREATED)
def create_webhook(
    payload: WebhookCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WebhookService(db, background_tasks=background_tasks)
    sub = service.create_subscription(
        current_user.id,
        name=payload.name,
        url=str(payload.url),
        subscribed_events=payload.subscribed_events,
    )
    return sub


@router.get("/{webhook_id}", response_model=WebhookOut)
def get_webhook(
    webhook_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WebhookService(db)
    sub = service.get_subscription(current_user.id, webhook_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return sub


@router.patch("/{webhook_id}", response_model=WebhookOut)
def update_webhook(
    webhook_id: int,
    payload: WebhookUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WebhookService(db)
    sub = service.update_subscription(
        current_user.id,
        webhook_id,
        name=payload.name,
        url=str(payload.url) if payload.url is not None else None,
        subscribed_events=payload.subscribed_events,
        status=payload.status,
    )
    if sub is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return sub


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    webhook_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WebhookService(db)
    if not service.delete_subscription(current_user.id, webhook_id):
        raise HTTPException(status_code=404, detail="Webhook not found")
    return None


@router.post("/{webhook_id}/rotate-secret", response_model=dict)
def rotate_secret(
    webhook_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WebhookService(db)
    new_secret = service.rotate_secret(current_user.id, webhook_id)
    if new_secret is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"secret": new_secret}


@router.post("/{webhook_id}/test", response_model=WebhookDeliveryOut)
def send_test_ping(
    webhook_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WebhookService(db, background_tasks=background_tasks)
    delivery = service.send_test_event(current_user.id, webhook_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return delivery


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryOut])
def list_deliveries(
    webhook_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WebhookService(db)
    deliveries = service.list_deliveries(current_user.id, webhook_id, limit=limit)
    if deliveries is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return deliveries


@router.post("/deliveries/{delivery_id}/redeliver", response_model=WebhookDeliveryOut)
def redeliver(
    delivery_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WebhookService(db, background_tasks=background_tasks)
    from app.models.webhook import WebhookDelivery

    delivery = db.get(WebhookDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    # Verify ownership
    sub = delivery.subscription
    if sub is None or sub.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Delivery not found")

    ok = service.redeliver(current_user.id, delivery_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Could not redeliver")
    # Return the newest delivery for this webhook
    deliveries = service.list_deliveries(current_user.id, sub.id, limit=1)
    return deliveries[0] if deliveries else delivery
