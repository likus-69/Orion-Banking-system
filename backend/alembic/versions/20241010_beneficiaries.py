"""add beneficiaries table

Revision ID: 20241010_beneficiaries
Revises: 20241009_scheduled_transfers
Create Date: 2024-10-10 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20241010_beneficiaries"
down_revision = "20241009_scheduled_transfers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    category_enum = sa.Enum(
        "family", "friend", "business", "utility", "other",
        name="beneficiary_category",
    )
    # create_table() below creates the enum type on Postgres; creating it
    # explicitly as well fails with "type already exists".

    op.create_table(
        "beneficiaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_account_number", sa.String(length=14), nullable=False),
        sa.Column("recipient_name", sa.String(length=255), nullable=False),
        sa.Column("nickname", sa.String(length=100), nullable=True),
        sa.Column("category", category_enum, default="other", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_user_id", "recipient_account_number",
                             name="uq_beneficiary_owner_recipient"),
    )
    op.create_index("ix_beneficiaries_owner_user_id", "beneficiaries", ["owner_user_id"])
    op.create_index("ix_beneficiaries_recipient_account_number",
                    "beneficiaries", ["recipient_account_number"])


def downgrade() -> None:
    op.drop_index("ix_beneficiaries_recipient_account_number", table_name="beneficiaries")
    op.drop_index("ix_beneficiaries_owner_user_id", table_name="beneficiaries")
    op.drop_table("beneficiaries")
    sa.Enum(name="beneficiary_category").drop(op.get_bind(), checkfirst=True)
