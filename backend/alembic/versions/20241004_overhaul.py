"""add kyc, refresh tokens, notifications, tx categories, tx reference

Revision ID: 20241004_overhaul
Revises: 20241003_initial
Create Date: 2024-10-04 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20241004_overhaul"
down_revision = "20241003_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── New table: refresh_tokens ────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=255), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked", sa.Boolean(), default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    # ── New table: notifications ─────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("level", sa.String(length=20), default="info", nullable=False),
        sa.Column("is_read", sa.Boolean(), default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    # ── New columns on users (KYC + lifecycle) ───────────────────
    op.add_column("users", sa.Column("phone", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("address_line", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("country", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("date_of_birth", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("kyc_status", sa.String(length=20), default="pending", nullable=False))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), default=True, nullable=False))
    op.add_column("users", sa.Column("is_locked", sa.Boolean(), default=False, nullable=False))
    op.add_column("users", sa.Column("failed_login_attempts", sa.Integer(), default=0, nullable=False))

    # ── New columns on transactions ──────────────────────────────
    op.add_column("transactions", sa.Column("reference", sa.String(length=32), nullable=True))
    op.add_column("transactions", sa.Column("idempotency_key", sa.String(length=64), nullable=True))

    # Create the enums so we can switch columns to them.
    tx_type_enum = sa.Enum(
        "deposit", "withdrawal", "transfer", "fee", "interest", "refund",
        name="tx_type",
    )
    tx_status_enum = sa.Enum(
        "pending", "completed", "failed", "reversed",
        name="tx_status",
    )
    tx_category_enum = sa.Enum(
        "general", "salary", "groceries", "utilities", "rent", "dining",
        "transport", "entertainment", "shopping", "health", "transfer", "other",
        name="tx_category",
    )
    tx_type_enum.create(op.get_bind(), checkfirst=True)
    tx_status_enum.create(op.get_bind(), checkfirst=True)
    tx_category_enum.create(op.get_bind(), checkfirst=True)

    # Backfill reference for existing rows so we can set NOT NULL.
    op.execute("""
        UPDATE transactions
        SET reference = 'ORX-' || substr(hex(randomblob(2)), 1, 4) || '-' || substr(hex(randomblob(2)), 1, 4)
        WHERE reference IS NULL
    """)
    op.alter_column("transactions", "reference", existing_type=sa.String(length=32), nullable=False)
    op.create_index("ix_transactions_reference", "transactions", ["reference"], unique=True)
    op.create_index("ix_transactions_idempotency_key", "transactions", ["idempotency_key"], unique=True)

    op.add_column(
        "transactions",
        sa.Column("category", tx_category_enum, nullable=False, server_default="general"),
    )
    op.add_column(
        "transactions",
        sa.Column("status_enum", tx_status_enum, nullable=False, server_default="completed"),
    )

    # ── New columns on audit_logs ────────────────────────────────
    op.add_column("audit_logs", sa.Column("user_agent", sa.String(length=512), nullable=True))
    op.add_column("audit_logs", sa.Column("request_id", sa.String(length=64), nullable=True))
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    # audit_logs
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_request_id", table_name="audit_logs")
    op.drop_column("audit_logs", "request_id")
    op.drop_column("audit_logs", "user_agent")

    # transactions
    op.drop_column("transactions", "status_enum")
    op.drop_column("transactions", "category")
    op.drop_index("ix_transactions_idempotency_key", table_name="transactions")
    op.drop_index("ix_transactions_reference", table_name="transactions")
    op.alter_column("transactions", "reference", existing_type=sa.String(length=32), nullable=True)
    op.drop_column("transactions", "idempotency_key")
    op.drop_column("transactions", "reference")

    sa.Enum(name="tx_category").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tx_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tx_type").drop(op.get_bind(), checkfirst=True)

    # users
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "is_locked")
    op.drop_column("users", "is_active")
    op.drop_column("users", "kyc_status")
    op.drop_column("users", "date_of_birth")
    op.drop_column("users", "country")
    op.drop_column("users", "city")
    op.drop_column("users", "address_line")
    op.drop_column("users", "phone")

    # notifications
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")

    # refresh_tokens
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
