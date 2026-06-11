"""phase 10 human approval evidence and audit log

Revision ID: 0086_phase10_human_approval_audit
Revises: 0085_phase9_runtime_policy_gate
Create Date: 2026-06-11 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0086_phase10_human_approval_audit"
down_revision = "0085_phase9_runtime_policy_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runtime_policy_decisions", sa.Column("intended_action_json", sa.Text(), nullable=True))
    op.add_column("runtime_policy_decisions", sa.Column("trace_context_json", sa.Text(), nullable=True))
    op.add_column("runtime_policy_decisions", sa.Column("policy_hit_json", sa.Text(), nullable=True))
    op.add_column("runtime_policy_decisions", sa.Column("business_impact_json", sa.Text(), nullable=True))
    op.add_column("runtime_policy_decisions", sa.Column("approval_scope_hash", sa.String(length=64), nullable=True))
    op.add_column("runtime_policy_decisions", sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("runtime_policy_decisions", sa.Column("consumed_by_decision_id", sa.String(length=36), nullable=True))
    op.create_index(
        "ix_runtime_policy_decisions_project_scope",
        "runtime_policy_decisions",
        ["project_id", "approval_scope_hash"],
    )

    op.create_table(
        "runtime_policy_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["runtime_policy_decisions.id"],
            name="fk_runtime_policy_audit_decision_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_runtime_policy_audit_project_decision_created",
        "runtime_policy_audit_events",
        ["project_id", "decision_id", "created_at"],
    )
    op.create_index(
        "ix_runtime_policy_audit_project_created",
        "runtime_policy_audit_events",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_policy_audit_project_created", table_name="runtime_policy_audit_events")
    op.drop_index("ix_runtime_policy_audit_project_decision_created", table_name="runtime_policy_audit_events")
    op.drop_table("runtime_policy_audit_events")

    op.drop_index("ix_runtime_policy_decisions_project_scope", table_name="runtime_policy_decisions")
    op.drop_column("runtime_policy_decisions", "consumed_by_decision_id")
    op.drop_column("runtime_policy_decisions", "consumed_at")
    op.drop_column("runtime_policy_decisions", "approval_scope_hash")
    op.drop_column("runtime_policy_decisions", "business_impact_json")
    op.drop_column("runtime_policy_decisions", "policy_hit_json")
    op.drop_column("runtime_policy_decisions", "trace_context_json")
    op.drop_column("runtime_policy_decisions", "intended_action_json")
