"""Add MCP interception tool bindings and event audit.

Revision ID: 0122_mcp_interception
Revises: 0121_add_user_totp_mfa
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0122_mcp_interception"
down_revision = "0121_add_user_totp_mfa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_tool_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("is_regex", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("action_type", sa.String(length=160), nullable=False),
        sa.Column("operation_kind", sa.String(length=32), nullable=True),
        sa.Column("connector_family", sa.String(length=80), nullable=True),
        sa.Column("contract_key", sa.String(length=160), nullable=True),
        sa.Column("contract_version", sa.String(length=32), nullable=True),
        sa.Column("fail_posture", sa.String(length=16), nullable=True),
        sa.Column("protected", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "tool_name", name="ux_mcp_tool_bindings_project_tool"),
        sa.CheckConstraint(
            "fail_posture IS NULL OR fail_posture IN ('fail_open','fail_closed')",
            name="ck_mcp_tool_bindings_fail_posture",
        ),
        sa.CheckConstraint("status IN ('active','retired')", name="ck_mcp_tool_bindings_status"),
    )
    op.create_index(
        "ix_mcp_tool_bindings_project_status",
        "mcp_tool_bindings",
        ["project_id", "status"],
        unique=False,
    )

    op.create_table(
        "mcp_interception_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("mcp_request_id", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=255), nullable=True),
        sa.Column("action_type", sa.String(length=160), nullable=True),
        sa.Column("protected", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("binding_source", sa.String(length=32), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("intent_id", sa.String(length=36), nullable=True),
        sa.Column("forward_attempted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("forward_succeeded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("execution_state", sa.String(length=16), server_default=sa.text("'not_attempted'"), nullable=False),
        sa.Column("upstream_error", sa.String(length=512), nullable=True),
        sa.Column("fail_posture", sa.String(length=16), nullable=True),
        sa.Column("action_receipt_id", sa.String(length=36), nullable=True),
        sa.Column("receipt_digest", sa.String(length=80), nullable=True),
        sa.Column("proof_status", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "execution_state IN ('not_attempted','succeeded','unknown')",
            name="ck_mcp_interception_events_execution_state",
        ),
    )
    op.create_index(
        "ix_mcp_interception_events_project_created",
        "mcp_interception_events",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_interception_events_request",
        "mcp_interception_events",
        ["mcp_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_interception_events_receipt",
        "mcp_interception_events",
        ["project_id", "action_receipt_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_interception_events_receipt", table_name="mcp_interception_events")
    op.drop_index("ix_mcp_interception_events_request", table_name="mcp_interception_events")
    op.drop_index("ix_mcp_interception_events_project_created", table_name="mcp_interception_events")
    op.drop_table("mcp_interception_events")
    op.drop_index("ix_mcp_tool_bindings_project_status", table_name="mcp_tool_bindings")
    op.drop_table("mcp_tool_bindings")
