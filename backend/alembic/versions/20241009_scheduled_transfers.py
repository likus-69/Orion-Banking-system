"""add scheduled_transfers + scheduled_transfer_executions

Revision ID: 20241009_scheduled_transfers
Revises: 20241008_totp
Create Date: 2024-10-09 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20241009_scheduled_transfers"
down_revision = "20241008_totp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schedule_type_enum = sa.Enum(
        "once", "daily", "weekly", "monthly", name="schedule_type"
    )
    schedule_status_enum = sa.Enum(
        "active", "paused", "completed", "cancelled", "failed", name="schedule_status"
    )
    execution_status_enum = sa.Enum(
        "success", "failed", "skipped", name="execution_status"
    )
    schedule_type_enum.create(op.get_bind(), checkfirst=True)
    schedule_status_enum.create(op.get_bind(), checkfirst=True)
    execution_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "scheduled_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("recipient_account_number", sa.String(length=14), nullable=False),
        sa.Column("amount", sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("schedule_type", schedule_type_enum, nullable=False),
        sa.Column("schedule_config", sa.String(length=50), nullable=False),
        sa.Column("next_run_at", sa.DateTime(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_execution_id", sa.Integer(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), default=0, nullable=False),
        sa.Column("status", schedule_status_enum, default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_scheduled_transfers_user_id", "scheduled_transfers", ["user_id"])
    op.create_index("ix_scheduled_transfers_status", "scheduled_transfers", ["status"])
    op.create_index("ix_scheduled_transfers_next_run_at", "scheduled_transfers", ["next_run_at"])

    op.create_table(
        "scheduled_transfer_executions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scheduled_transfer_id", sa.Integer(),
                  sa.ForeignKey("scheduled_transfers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transaction_id", sa.Integer(),
                  sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("transaction_reference", sa.String(length=32), nullable=True),
        sa.Column("status", execution_status_enum, default="success", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_scheduled_transfer_executions_scheduled_transfer_id",
        "scheduled_transfer_executions", ["scheduled_transfer_id"]
    )
    op.create_index(
        "ix_scheduled_transfer_executions_executed_at",
        "scheduled_transfer_executions", ["executed_at"]
    )

    # Add FK from scheduled_transfers.last_execution_id → executions.id
    op.create_foreign_key(
        "fk_scheduled_transfers_last_execution_id",
        "scheduled_transfers",
        "scheduled_transfer_executions",
        ["last_execution_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_scheduled_transfers_last_execution_id",
        "scheduled_transfers",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_scheduled_transfer_executions_executed_at",
        table_name="scheduled_transfer_executions",
    )
    op.drop_index(
        "ix_scheduled_transfer_executions_scheduled_transfer_id",
        table_name="scheduled_transfer_executions",
    )
    op.drop_table("scheduled_transfer_executions")

    op.drop_index("ix_scheduled_transfers_next_run_at", table_name="scheduled_transfers")
    op.drop_index("ix_scheduled_transfers_status", table_name="scheduled_transfers")
    op.drop_index("ix_scheduled_transfers_user_id", table_name="scheduled_transfers")
    op.drop_table("scheduled_transfers")

    sa.Enum(name="execution_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="schedule_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="schedule_type").drop(op.get_bind(), checkfirst=True)
