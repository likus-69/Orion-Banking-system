"""add pending_deposits table

Revision ID: 20241011_pending_deposits
Revises: 20241010_beneficiaries
Create Date: 2024-10-11 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20241011_pending_deposits"
down_revision = "20241010_beneficiaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status_enum = sa.Enum(
        "pending", "completed", "failed", "expired", name="pending_deposit_status"
    )
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "pending_deposits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reference", sa.String(length=32), nullable=False),
        sa.Column("provider_reference", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("transaction_id", sa.Integer(),
                  sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", status_enum, default="pending", nullable=False),
        sa.Column("callback_payload", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_pending_deposits_user_id", "pending_deposits", ["user_id"])
    op.create_index("ix_pending_deposits_reference", "pending_deposits", ["reference"], unique=True)
    op.create_index("ix_pending_deposits_provider_reference", "pending_deposits", ["provider_reference"])
    op.create_index("ix_pending_deposits_status", "pending_deposits", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pending_deposits_status", table_name="pending_deposits")
    op.drop_index("ix_pending_deposits_provider_reference", table_name="pending_deposits")
    op.drop_index("ix_pending_deposits_reference", table_name="pending_deposits")
    op.drop_index("ix_pending_deposits_user_id", table_name="pending_deposits")
    op.drop_table("pending_deposits")
    sa.Enum(name="pending_deposit_status").drop(op.get_bind(), checkfirst=True)
