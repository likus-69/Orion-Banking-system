"""add webhook_subscriptions + webhook_deliveries

Revision ID: 20241007_webhooks
Revises: 20241006_email_prefs
Create Date: 2024-10-07 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20241007_webhooks"
down_revision = "20241006_email_prefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    webhook_status_enum = sa.Enum("active", "paused", "disabled", name="webhook_status")
    delivery_status_enum = sa.Enum("pending", "delivered", "failed", name="webhook_delivery_status")
    webhook_status_enum.create(op.get_bind(), checkfirst=True)
    delivery_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("secret", sa.String(length=255), nullable=False),
        sa.Column("subscribed_events", sa.Text(), default="", nullable=False),
        sa.Column("status", webhook_status_enum, default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_webhook_subscriptions_user_id", "webhook_subscriptions", ["user_id"])
    op.create_index("ix_webhook_subscriptions_status", "webhook_subscriptions", ["status"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("webhook_id", sa.Integer(),
                  sa.ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", delivery_status_enum, default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), default=0, nullable=False),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_webhook_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"])
    op.create_index("ix_webhook_deliveries_event_type", "webhook_deliveries", ["event_type"])
    op.create_index("ix_webhook_deliveries_status", "webhook_deliveries", ["status"])
    op.create_index("ix_webhook_deliveries_created_at", "webhook_deliveries", ["created_at"])
    op.create_index("ix_webhook_deliveries_event_id", "webhook_deliveries", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_event_id", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_created_at", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_status", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_event_type", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_webhook_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_webhook_subscriptions_status", table_name="webhook_subscriptions")
    op.drop_index("ix_webhook_subscriptions_user_id", table_name="webhook_subscriptions")
    op.drop_table("webhook_subscriptions")

    sa.Enum(name="webhook_delivery_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="webhook_status").drop(op.get_bind(), checkfirst=True)
