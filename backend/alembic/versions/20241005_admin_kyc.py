"""add user role + KYC review fields

Revision ID: 20241005_admin_kyc
Revises: 20241004_overhaul
Create Date: 2024-10-05 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20241005_admin_kyc"
down_revision = "20241004_overhaul"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────
    user_role_enum = sa.Enum("customer", "support", "admin", name="user_role")
    kyc_status_enum = sa.Enum("pending", "in_review", "verified", "rejected", name="kyc_status")
    user_role_enum.create(op.get_bind(), checkfirst=True)
    kyc_status_enum.create(op.get_bind(), checkfirst=True)

    # ── Add columns ───────────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column("role", user_role_enum, nullable=False, server_default="customer"),
    )
    op.create_index("ix_users_role", "users", ["role"])

    # Convert kyc_status from String(20) to enum. Existing values happen to match.
    # SQLite won't let us ALTER COLUMN type, so we add a new column + copy + drop.
    # For Postgres we could ALTER TYPE directly. To keep this migration
    # portable across both, we use raw SQL with a guard.
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.add_column(
        "users",
        sa.Column("kyc_status_new", kyc_status_enum, nullable=True),
    )
    # Backfill from existing string column. On Postgres the target column is a
    # real enum type, so the CASE expression needs an explicit cast.
    backfill = (
        "UPDATE users SET kyc_status_new = "
        "(CASE kyc_status WHEN 'verified' THEN 'verified' "
        "WHEN 'in_review' THEN 'in_review' WHEN 'rejected' THEN 'rejected' "
        "ELSE 'pending' END)"
    )
    if dialect == "postgresql":
        backfill += "::kyc_status"
    op.execute(backfill)
    op.drop_column("users", "kyc_status")
    op.alter_column("users", "kyc_status_new", new_column_name="kyc_status",
                    existing_type=kyc_status_enum, nullable=False, server_default="pending")
    op.create_index("ix_users_kyc_status", "users", ["kyc_status"])

    op.add_column(
        "users",
        sa.Column("kyc_reviewed_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("users", sa.Column("kyc_reviewed_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("kyc_rejection_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "kyc_rejection_reason")
    op.drop_column("users", "kyc_reviewed_at")
    op.drop_column("users", "kyc_reviewed_by")

    # Revert kyc_status enum back to string
    op.alter_column(
        "users",
        "kyc_status",
        existing_type=sa.Enum("pending", "in_review", "verified", "rejected", name="kyc_status"),
        type_=sa.String(length=20),
        postgresql_using="kyc_status::text",
    )
    op.drop_index("ix_users_kyc_status", table_name="users")

    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "role")

    sa.Enum(name="kyc_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
