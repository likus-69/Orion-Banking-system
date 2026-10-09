"""add TOTP / 2FA columns on users

Revision ID: 20241008_totp
Revises: 20241007_webhooks
Create Date: 2024-10-08 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20241008_totp"
down_revision = "20241007_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), default=False, nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("totp_secret_enc", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("totp_backup_codes_hashed", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("totp_setup_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "totp_setup_at")
    op.drop_column("users", "totp_backup_codes_hashed")
    op.drop_column("users", "totp_secret_enc")
    op.drop_column("users", "totp_enabled")
