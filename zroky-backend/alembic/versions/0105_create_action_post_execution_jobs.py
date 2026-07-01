"""create action post-execution jobs

Revision ID: 0105_create_action_post_execution_jobs
Revises: 0104_add_postgres_read_connector_config
Create Date: 2026-06-28 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0105_create_action_post_execution_jobs"
down_revision = "0104_add_postgres_read_connector_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("action_intents") as batch_op:
        batch_op.add_column(
            sa.Column(
                "proof_status",
                sa.String(length=32),
                server_default=sa.text("'not_started'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "receipt_status",
                sa.String(length=32),
                server_default=sa.text("'missing'"),
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_action_intents_proof_status",
            "proof_status IN ('not_started','pending','matched','mismatched','not_verified')",
        )
        batch_op.create_check_constraint(
            "ck_action_intents_receipt_status",
            "receipt_status IN ('missing','pending','generated','failed')",
        )
    op.create_index(
        "ix_action_intents_project_proof",
        "action_intents",
        ["project_id", "proof_status", "created_at"],
    )

    op.create_table(
        "action_post_execution_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("action_intent_id", sa.String(length=36), nullable=False),
        sa.Column("execution_attempt_id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("payload_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("claimed_by", sa.String(length=128), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "job_type IN ('verify_outcome','generate_receipt')",
            name="ck_action_post_execution_jobs_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','claimed','running','succeeded','retrying','dead')",
            name="ck_action_post_execution_jobs_status",
        ),
        sa.ForeignKeyConstraint(["action_intent_id"], ["action_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_attempt_id"], ["action_execution_attempts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "action_intent_id",
            "execution_attempt_id",
            "job_type",
            name="ux_action_post_execution_jobs_project_attempt_type",
        ),
    )
    op.create_index(
        "ix_action_post_execution_jobs_project_status",
        "action_post_execution_jobs",
        ["project_id", "status", "available_at"],
    )
    op.create_index(
        "ix_action_post_execution_jobs_attempt",
        "action_post_execution_jobs",
        ["project_id", "execution_attempt_id"],
    )
    op.create_index(
        "ix_action_post_execution_jobs_action",
        "action_post_execution_jobs",
        ["project_id", "action_intent_id"],
    )
    op.create_index(
        "ix_action_post_execution_jobs_lease",
        "action_post_execution_jobs",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_action_post_execution_jobs_lease", table_name="action_post_execution_jobs")
    op.drop_index("ix_action_post_execution_jobs_action", table_name="action_post_execution_jobs")
    op.drop_index("ix_action_post_execution_jobs_attempt", table_name="action_post_execution_jobs")
    op.drop_index("ix_action_post_execution_jobs_project_status", table_name="action_post_execution_jobs")
    op.drop_table("action_post_execution_jobs")
    op.drop_index("ix_action_intents_project_proof", table_name="action_intents")
    with op.batch_alter_table("action_intents") as batch_op:
        batch_op.drop_constraint("ck_action_intents_receipt_status", type_="check")
        batch_op.drop_constraint("ck_action_intents_proof_status", type_="check")
        batch_op.drop_column("receipt_status")
        batch_op.drop_column("proof_status")
