"""extend agents for tool-control profiles

Revision ID: 0095_extend_agents_for_tool_control_profiles
Revises: 0094_add_project_alert_slack_delivery
Create Date: 2026-06-25 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0095_extend_agents_for_tool_control_profiles"
down_revision = "0094_add_project_alert_slack_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agents") as batch_op:
        batch_op.add_column(
            sa.Column(
                "runtime_path",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'sdk'"),
            )
        )
        batch_op.add_column(sa.Column("framework", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("environment", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("model_provider", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("model_name", sa.String(length=120), nullable=True))
        batch_op.add_column(
            sa.Column("tool_names_json", sa.Text(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch_op.add_column(
            sa.Column(
                "allowed_action_types_json",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "blocked_action_types_json",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(sa.Column("default_policy_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column("risk_limits_json", sa.Text(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch_op.add_column(
            sa.Column(
                "verification_connectors_json",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"))
        )
        batch_op.add_column(sa.Column("created_by_subject", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("updated_by_subject", sa.String(length=255), nullable=True))
        batch_op.create_check_constraint(
            "ck_agents_runtime_path",
            "runtime_path IN ('sdk','http_gateway','mcp_gateway','webhook')",
        )

    op.create_index(
        "ix_agents_project_active_updated",
        "agents",
        ["project_id", "is_active", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agents_project_active_updated", table_name="agents")
    with op.batch_alter_table("agents") as batch_op:
        batch_op.drop_constraint("ck_agents_runtime_path", type_="check")
        batch_op.drop_column("updated_by_subject")
        batch_op.drop_column("created_by_subject")
        batch_op.drop_column("is_active")
        batch_op.drop_column("metadata_json")
        batch_op.drop_column("verification_connectors_json")
        batch_op.drop_column("risk_limits_json")
        batch_op.drop_column("default_policy_id")
        batch_op.drop_column("blocked_action_types_json")
        batch_op.drop_column("allowed_action_types_json")
        batch_op.drop_column("tool_names_json")
        batch_op.drop_column("model_name")
        batch_op.drop_column("model_provider")
        batch_op.drop_column("environment")
        batch_op.drop_column("framework")
        batch_op.drop_column("runtime_path")
