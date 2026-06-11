"""phase 9 runtime policy gate decisions

Revision ID: 0085_phase9_runtime_policy_gate
Revises: 0084_phase6_8_replay_goldens_ci_gate
Create Date: 2026-06-11 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0085_phase9_runtime_policy_gate"
down_revision = "0084_phase6_8_replay_goldens_ci_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_policy_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("call_id", sa.String(length=64), nullable=True),
        sa.Column("agent_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=64), nullable=True),
        sa.Column("action_type", sa.String(length=64), nullable=True),
        sa.Column("tool_name", sa.String(length=255), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("request_json", sa.Text(), nullable=True),
        sa.Column("policy_snapshot_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=64), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "decision IN ('allow', 'block', 'requires_approval')",
            name="ck_runtime_policy_decisions_decision",
        ),
        sa.CheckConstraint(
            "status IN ('allowed', 'blocked', 'pending_approval', 'approved', 'rejected', 'expired')",
            name="ck_runtime_policy_decisions_status",
        ),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], name="fk_runtime_policy_decisions_call_id", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_runtime_policy_decisions_project_status_created",
        "runtime_policy_decisions",
        ["project_id", "status", "created_at"],
    )
    op.create_index(
        "ix_runtime_policy_decisions_project_trace_created",
        "runtime_policy_decisions",
        ["project_id", "trace_id", "created_at"],
    )
    op.create_index(
        "ix_runtime_policy_decisions_project_tool_created",
        "runtime_policy_decisions",
        ["project_id", "tool_name", "created_at"],
    )
    op.create_index(
        "ix_runtime_policy_decisions_project_created",
        "runtime_policy_decisions",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_policy_decisions_project_created", table_name="runtime_policy_decisions")
    op.drop_index("ix_runtime_policy_decisions_project_tool_created", table_name="runtime_policy_decisions")
    op.drop_index("ix_runtime_policy_decisions_project_trace_created", table_name="runtime_policy_decisions")
    op.drop_index("ix_runtime_policy_decisions_project_status_created", table_name="runtime_policy_decisions")
    op.drop_table("runtime_policy_decisions")
