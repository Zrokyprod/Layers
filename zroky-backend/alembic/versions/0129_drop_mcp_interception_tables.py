"""drop mcp interception tables

Revision ID: 0129_drop_mcp_interception_tables
Revises: 0128_add_action_runner_capability_manifest
Create Date: 2026-07-22
"""

from __future__ import annotations

from alembic import op


revision = "0129_drop_mcp_interception_tables"
down_revision = "0128_add_action_runner_capability_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mcp_interception_events CASCADE")
    op.execute("DROP TABLE IF EXISTS mcp_tool_bindings CASCADE")


def downgrade() -> None:
    pass
