"""add slack approval user allowlist

Revision ID: 0103_add_slack_approval_user_allowlist
Revises: 0102_add_dual_approval_tracking
Create Date: 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0103_add_slack_approval_user_allowlist"
down_revision = "0102_add_dual_approval_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_slack_install",
        sa.Column("approval_user_ids_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tenant_slack_install", "approval_user_ids_json")
