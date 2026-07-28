"""drop mcp interception tables

Revision ID: 0137_drop_mcp_interception_tables
Revises: 0136_add_action_runner_capability_manifest
Create Date: 2026-07-22
"""

from __future__ import annotations

from alembic import op


revision = "0137_drop_mcp_interception_tables"
down_revision = "0136_add_action_runner_capability_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    suffix = " CASCADE" if op.get_bind().dialect.name == "postgresql" else ""
    op.execute(f"DROP TABLE IF EXISTS mcp_interception_events{suffix}")
    op.execute(f"DROP TABLE IF EXISTS mcp_tool_bindings{suffix}")


def downgrade() -> None:
    pass
