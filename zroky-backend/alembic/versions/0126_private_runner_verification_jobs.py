"""Create private runner verification jobs.

Revision ID: 0126_private_runner_verification_jobs
Revises: 0125_canonicalize_private_runner_refs
Create Date: 2026-07-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0126_private_runner_verification_jobs"
down_revision = "0125_canonicalize_private_runner_refs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "private_runner_verification_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("action_intent_id", sa.String(length=36), nullable=False),
        sa.Column("execution_attempt_id", sa.String(length=36), nullable=False),
        sa.Column("runner_id", sa.String(length=36), nullable=False),
        sa.Column("connector_type", sa.String(length=64), nullable=False),
        sa.Column("credential_ref", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("plan_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('queued','claimed','succeeded','failed','cancelled')",
            name="ck_private_runner_verify_status",
        ),
        sa.ForeignKeyConstraint(["action_intent_id"], ["action_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_attempt_id"], ["action_execution_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runner_id"], ["action_runners.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "project_id",
            "execution_attempt_id",
            name="ux_private_runner_verify_project_attempt",
        ),
    )
    op.create_index(
        "ix_private_runner_verify_project_runner_status",
        "private_runner_verification_jobs",
        ["project_id", "runner_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_private_runner_verify_project_runner_status", table_name="private_runner_verification_jobs")
    op.drop_table("private_runner_verification_jobs")
