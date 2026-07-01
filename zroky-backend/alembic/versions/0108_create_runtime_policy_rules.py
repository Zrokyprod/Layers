"""create runtime policy rules

Revision ID: 0108_create_runtime_policy_rules
Revises: 0107_add_action_intent_agent_id
Create Date: 2026-06-29 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0108_create_runtime_policy_rules"
down_revision = "0107_add_action_intent_agent_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_policy_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("action_type", sa.String(length=64), nullable=True),
        sa.Column("environment", sa.String(length=64), nullable=True),
        sa.Column("policy_patch_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=True),
        sa.Column("updated_by_subject", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_runtime_policy_rules_version"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], name="fk_runtime_policy_rules_agent_id", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runtime_policy_rules_project_action", "runtime_policy_rules", ["project_id", "action_type"])
    op.create_index("ix_runtime_policy_rules_project_agent", "runtime_policy_rules", ["project_id", "agent_id"])
    op.create_index("ix_runtime_policy_rules_project_enabled", "runtime_policy_rules", ["project_id", "is_enabled"])
    op.create_index("ix_runtime_policy_rules_project_env", "runtime_policy_rules", ["project_id", "environment"])
    op.create_index("ix_runtime_policy_rules_project_priority", "runtime_policy_rules", ["project_id", "priority", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_runtime_policy_rules_project_priority", table_name="runtime_policy_rules")
    op.drop_index("ix_runtime_policy_rules_project_env", table_name="runtime_policy_rules")
    op.drop_index("ix_runtime_policy_rules_project_enabled", table_name="runtime_policy_rules")
    op.drop_index("ix_runtime_policy_rules_project_agent", table_name="runtime_policy_rules")
    op.drop_index("ix_runtime_policy_rules_project_action", table_name="runtime_policy_rules")
    op.drop_table("runtime_policy_rules")
