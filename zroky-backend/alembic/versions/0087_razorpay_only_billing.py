"""make Razorpay the only active billing provider

Revision ID: 0087_razorpay_only_billing
Revises: 0086_phase10_human_approval_audit
Create Date: 2026-06-12 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0087_razorpay_only_billing"
down_revision = "0086_phase10_human_approval_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    op.alter_column(
        "subscriptions",
        "payment_provider",
        server_default=sa.text("'razorpay'"),
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    op.alter_column(
        "subscriptions",
        "payment_provider",
        server_default=sa.text("'razorpay'"),
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
