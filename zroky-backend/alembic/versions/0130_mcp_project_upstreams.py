"""Add project-scoped MCP upstream bindings and gateway sessions.

Revision ID: 0130_mcp_project_upstreams
Revises: 0129_outcome_mismatch_responses
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0130_mcp_project_upstreams"
down_revision = "0129_outcome_mismatch_responses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_upstream_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("endpoint_url", sa.String(length=2048), nullable=False),
        sa.Column("protocol_version", sa.String(length=32), nullable=False, server_default="2025-06-18"),
        sa.Column("bearer_credential_id", sa.String(length=36), nullable=True),
        sa.Column("allowed_tools_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("test_status", sa.String(length=16), nullable=False, server_default="not_tested"),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_error", sa.String(length=64), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_subject", sa.String(length=255), nullable=True),
        sa.Column("updated_by_subject", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('draft','active','disabled')", name="ck_mcp_upstream_bindings_status"),
        sa.CheckConstraint(
            "test_status IN ('not_tested','succeeded','failed')",
            name="ck_mcp_upstream_bindings_test_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_mcp_upstream_bindings_version"),
        sa.ForeignKeyConstraint(
            ["bearer_credential_id"], ["connector_credentials.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="ux_mcp_upstream_bindings_project"),
    )
    op.create_index(
        "ix_mcp_upstream_bindings_project_status",
        "mcp_upstream_bindings",
        ["project_id", "status"],
    )
    op.create_table(
        "mcp_gateway_sessions",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("binding_id", sa.String(length=36), nullable=False),
        sa.Column("binding_version", sa.Integer(), nullable=False),
        sa.Column("principal_subject", sa.String(length=255), nullable=True),
        sa.Column("upstream_session_id", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["binding_id"], ["mcp_upstream_bindings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mcp_gateway_sessions_project_expiry",
        "mcp_gateway_sessions",
        ["project_id", "expires_at"],
    )
    op.create_index(
        "ix_mcp_gateway_sessions_binding",
        "mcp_gateway_sessions",
        ["binding_id", "binding_version"],
    )

    # These tables all carry project_id, so database-level tenant isolation is
    # part of the gateway boundary rather than an application-only promise.
    # Include the two 0122 tables here because that migration predates the
    # tenant-gateway rollout and did not install RLS policies.
    if op.get_bind().dialect.name == "postgresql":
        for table_name in (
            "mcp_tool_bindings",
            "mcp_interception_events",
            "mcp_upstream_bindings",
            "mcp_gateway_sessions",
        ):
            policy_name = f"{table_name}_tenant_isolation"
            op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
            op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}")
            op.execute(
                f"""
                CREATE POLICY {policy_name}
                ON {table_name}
                USING (project_id = current_setting('app.current_tenant_id', true))
                WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
                """
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name in (
            "mcp_tool_bindings",
            "mcp_interception_events",
            "mcp_upstream_bindings",
            "mcp_gateway_sessions",
        ):
            policy_name = f"{table_name}_tenant_isolation"
            op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_mcp_gateway_sessions_binding", table_name="mcp_gateway_sessions")
    op.drop_index("ix_mcp_gateway_sessions_project_expiry", table_name="mcp_gateway_sessions")
    op.drop_table("mcp_gateway_sessions")
    op.drop_index("ix_mcp_upstream_bindings_project_status", table_name="mcp_upstream_bindings")
    op.drop_table("mcp_upstream_bindings")
