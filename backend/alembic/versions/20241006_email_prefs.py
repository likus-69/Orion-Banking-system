"""add email notification preferences on users

Revision ID: 20241006_email_prefs
Revises: 20241005_admin_kyc
Create Date: 2024-10-06 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20241006_email_prefs"
down_revision = "20241005_admin_kyc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_on_deposit", sa.Boolean(), default=True, nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("email_on_withdrawal", sa.Boolean(), default=True, nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("email_on_transfer_in", sa.Boolean(), default=True, nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("email_on_transfer_out", sa.Boolean(), default=True, nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("email_on_kyc_decision", sa.Boolean(), default=True, nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("users", "email_on_kyc_decision")
    op.drop_column("users", "email_on_transfer_out")
    op.drop_column("users", "email_on_transfer_in")
    op.drop_column("users", "email_on_withdrawal")
    op.drop_column("users", "email_on_deposit")
