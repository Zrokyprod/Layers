"""add durable golden set flaky and CI blocking flags

Revision ID: 0073_add_golden_set_ci_flags
Revises: 0072_consolidate_issues_into_anomalies
Create Date: 2026-05-26 17:35:00.000000

Phase 11: Goldens are production regression memory. Flaky and blocking
labels must persist beyond a dashboard refresh so CI and operators can trust
the set state.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0073_add_golden_set_ci_flags"
down_revision = "0072_consolidate_issues_into_anomalies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "golden_sets",
        sa.Column("is_flaky", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "golden_sets",
        sa.Column("blocks_ci", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("golden_sets", "blocks_ci")
    op.drop_column("golden_sets", "is_flaky")
