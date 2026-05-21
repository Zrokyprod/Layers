"""create replay_jobs table

Revision ID: 0047_create_replay_jobs
Revises: 0046_add_issue_severity_blast_radius
Create Date: 2026-05-12 09:30:00.000000

Creates the replay_jobs table used by the replay worker poll/result protocol.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_create_replay_jobs"
down_revision = "0046_add_issue_severity_blast_radius"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replay_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("call_id", sa.String(64), sa.ForeignKey("calls.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pr_id", sa.String(36), sa.ForeignKey("diagnosis_pull_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("candidate_fix_diff", sa.Text, nullable=True),
        sa.Column("artifact_url", sa.String(2048), nullable=True),
        sa.Column("artifact_signature", sa.String(128), nullable=True),
        sa.Column("timeout_seconds", sa.Integer, nullable=False, server_default="300"),
        sa.Column("diff_metric", sa.Float, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("stdout_tail", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_replay_jobs_tenant_status", "replay_jobs", ["tenant_id", "status"])
    op.create_index("ix_replay_jobs_tenant_created", "replay_jobs", ["tenant_id", "created_at"])
    op.create_index("ix_replay_jobs_call_id", "replay_jobs", ["call_id"])
    op.create_index("ix_replay_jobs_pr_id", "replay_jobs", ["pr_id"])


def downgrade() -> None:
    op.drop_index("ix_replay_jobs_pr_id", table_name="replay_jobs")
    op.drop_index("ix_replay_jobs_call_id", table_name="replay_jobs")
    op.drop_index("ix_replay_jobs_tenant_created", table_name="replay_jobs")
    op.drop_index("ix_replay_jobs_tenant_status", table_name="replay_jobs")
    op.drop_table("replay_jobs")
