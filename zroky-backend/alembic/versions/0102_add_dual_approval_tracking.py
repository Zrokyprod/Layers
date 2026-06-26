"""add dual approval tracking

Revision ID: 0102_add_dual_approval_tracking
Revises: 0101_create_usage_meter_counts
Create Date: 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0102_add_dual_approval_tracking"
down_revision = "0101_create_usage_meter_counts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runtime_policy_decisions",
        sa.Column("required_approval_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "runtime_policy_decisions",
        sa.Column("approval_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "runtime_policy_decisions",
        sa.Column("approver_subjects_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.execute(
        "UPDATE runtime_policy_decisions "
        "SET required_approval_count = 1 "
        "WHERE status IN ('pending_approval', 'approved') AND required_approval_count = 0"
    )
    op.execute(
        "UPDATE runtime_policy_decisions "
        "SET approval_count = 1 "
        "WHERE status = 'approved' AND approval_count = 0"
    )


def downgrade() -> None:
    op.drop_column("runtime_policy_decisions", "approver_subjects_json")
    op.drop_column("runtime_policy_decisions", "approval_count")
    op.drop_column("runtime_policy_decisions", "required_approval_count")
