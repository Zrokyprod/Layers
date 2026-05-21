"""create event_counts metering ledger

Revision ID: 0048_create_event_counts_ledger
Revises: 0047_create_replay_jobs
Create Date: 2026-05-12 10:00:00.000000

Creates event_counts — one row per (tenant_id, month) tracking cumulative event
volume for billing.  The upsert is: INSERT … ON CONFLICT DO UPDATE count += 1.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048_create_event_counts_ledger"
down_revision = "0047_create_replay_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_counts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("month", sa.String(7), nullable=False, comment="YYYY-MM"),
        sa.Column("event_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("last_event_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "month", name="ux_event_counts_tenant_month"),
    )
    op.create_index("ix_event_counts_tenant_month", "event_counts", ["tenant_id", "month"])


def downgrade() -> None:
    op.drop_index("ix_event_counts_tenant_month", table_name="event_counts")
    op.drop_table("event_counts")
