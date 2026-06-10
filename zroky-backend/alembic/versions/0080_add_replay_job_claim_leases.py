"""add replay job claim leases

Revision ID: 0080_add_replay_job_claim_leases
Revises: 0079_skydo_billing_provider
Create Date: 2026-06-10 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0080_add_replay_job_claim_leases"
down_revision = "0079_skydo_billing_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("replay_jobs", sa.Column("claimed_by", sa.String(length=128), nullable=True))
    op.add_column("replay_jobs", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("replay_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "replay_jobs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_replay_jobs_status_lease", "replay_jobs", ["status", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_replay_jobs_status_lease", table_name="replay_jobs")
    op.drop_column("replay_jobs", "attempt_count")
    op.drop_column("replay_jobs", "lease_expires_at")
    op.drop_column("replay_jobs", "claimed_at")
    op.drop_column("replay_jobs", "claimed_by")
