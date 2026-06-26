"""create action runner foundation

Revision ID: 0098_create_action_runner_foundation
Revises: 0097_create_verified_action_kernel
Create Date: 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0098_create_action_runner_foundation"
down_revision = "0097_create_verified_action_kernel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_runners",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("runner_type", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=64), server_default=sa.text("'production'"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'registered'"), nullable=False),
        sa.Column("supported_operation_kinds_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("credential_scope_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("heartbeat_payload_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("capability_version", sa.String(length=64), nullable=True),
        sa.Column("registered_by_subject", sa.String(length=255), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "runner_type IN ('managed_sandbox','customer_hosted')",
            name="ck_action_runners_runner_type",
        ),
        sa.CheckConstraint(
            "status IN ('registered','online','degraded','offline','disabled')",
            name="ck_action_runners_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", "environment", name="ux_action_runners_project_name_environment"),
    )
    op.create_index("ix_action_runners_project_environment", "action_runners", ["project_id", "environment"])
    op.create_index("ix_action_runners_project_status", "action_runners", ["project_id", "status"])

    op.create_table(
        "action_execution_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("action_intent_id", sa.String(length=36), nullable=False),
        sa.Column("runner_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'planned'"), nullable=False),
        sa.Column("credential_ref", sa.String(length=512), nullable=False),
        sa.Column("plan_digest", sa.String(length=80), nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.Column("result_summary_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("protected_credential_returned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("requested_by_subject", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('planned','dispatched','running','succeeded','failed','ambiguous','cancelled')",
            name="ck_action_execution_attempts_status",
        ),
        sa.CheckConstraint(
            "protected_credential_returned = false",
            name="ck_action_execution_attempts_no_returned_credential",
        ),
        sa.ForeignKeyConstraint(["action_intent_id"], ["action_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runner_id"], ["action_runners.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "action_intent_id",
            "idempotency_key",
            name="ux_action_execution_attempts_project_intent_idempotency",
        ),
    )
    op.create_index(
        "ix_action_execution_attempts_project_created",
        "action_execution_attempts",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_action_execution_attempts_project_intent",
        "action_execution_attempts",
        ["project_id", "action_intent_id"],
    )
    op.create_index(
        "ix_action_execution_attempts_project_runner",
        "action_execution_attempts",
        ["project_id", "runner_id"],
    )
    op.create_index(
        "ix_action_execution_attempts_project_status",
        "action_execution_attempts",
        ["project_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_action_execution_attempts_project_status", table_name="action_execution_attempts")
    op.drop_index("ix_action_execution_attempts_project_runner", table_name="action_execution_attempts")
    op.drop_index("ix_action_execution_attempts_project_intent", table_name="action_execution_attempts")
    op.drop_index("ix_action_execution_attempts_project_created", table_name="action_execution_attempts")
    op.drop_table("action_execution_attempts")
    op.drop_index("ix_action_runners_project_status", table_name="action_runners")
    op.drop_index("ix_action_runners_project_environment", table_name="action_runners")
    op.drop_table("action_runners")
