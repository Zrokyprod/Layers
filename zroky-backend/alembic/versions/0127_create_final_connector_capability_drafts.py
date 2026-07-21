"""create final connector capability drafts

Revision ID: 0127_create_final_connector_capability_drafts
Revises: 0126_create_final_agent_runs
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0127_create_final_connector_capability_drafts"
down_revision = "0126_create_final_agent_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "final_connector_capability_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("capability_key", sa.String(length=255), nullable=False),
        sa.Column("schema_digest", sa.String(length=80), nullable=False),
        sa.Column("schema_json", sa.Text(), nullable=False),
        sa.Column("trust_status", sa.String(length=32), server_default=sa.text("'draft_untrusted'"), nullable=False),
        sa.Column("trusted_for_recovery", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source_kind IN ('mcp','a2a','openapi','asyncapi')", name="ck_final_capability_drafts_source_kind"),
        sa.CheckConstraint("trust_status IN ('draft_untrusted','reviewed','retired')", name="ck_final_capability_drafts_trust_status"),
        sa.CheckConstraint("trusted_for_recovery = false", name="ck_final_capability_drafts_not_recovery_trusted"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "environment", "source_kind", "capability_key", name="ux_final_capability_drafts_scope_key"),
    )
    op.create_index(
        "ix_final_capability_drafts_scope_source",
        "final_connector_capability_drafts",
        ["project_id", "environment", "source_kind", "created_at"],
    )
    _enable_project_rls("final_connector_capability_drafts")


def downgrade() -> None:
    _disable_project_rls("final_connector_capability_drafts")
    op.drop_index("ix_final_capability_drafts_scope_source", table_name="final_connector_capability_drafts")
    op.drop_table("final_connector_capability_drafts")


def _enable_project_rls(table_name: str) -> None:
    policy_name = f"{table_name}_project_isolation"
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {policy_name}
        ON {table_name}
        USING (project_id = current_setting('app.current_tenant_id', true))
        WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
        """
    )


def _disable_project_rls(table_name: str) -> None:
    policy_name = f"{table_name}_project_isolation"
    op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
