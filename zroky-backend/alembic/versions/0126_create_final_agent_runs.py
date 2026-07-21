"""create final agent runs

Revision ID: 0126_create_final_agent_runs
Revises: 0125_create_final_approval_requirements
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0126_create_final_agent_runs"
down_revision = "0125_create_final_approval_requirements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "final_agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("external_run_id", sa.String(length=255), nullable=True),
        sa.Column("intent_id", sa.String(length=36), nullable=True),
        sa.Column("workflow_key", sa.String(length=160), nullable=True),
        sa.Column("agent_ref", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'declared'"), nullable=False),
        sa.Column("run_digest", sa.String(length=80), nullable=False),
        sa.Column("run_json", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('declared','running','succeeded','failed','cancelled','unknown')",
            name="ck_final_agent_runs_status",
        ),
        sa.ForeignKeyConstraint(["intent_id"], ["final_workflow_intents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "environment", "idempotency_key", name="ux_final_agent_runs_scope_idempotency"),
    )
    op.create_index(
        "ix_final_agent_runs_scope_status",
        "final_agent_runs",
        ["project_id", "environment", "status", "created_at"],
    )
    op.create_index(
        "ix_final_agent_runs_scope_external",
        "final_agent_runs",
        ["project_id", "environment", "external_run_id"],
    )
    op.create_index(
        "ix_final_agent_runs_scope_intent",
        "final_agent_runs",
        ["project_id", "environment", "intent_id"],
    )
    _enable_project_rls("final_agent_runs")


def downgrade() -> None:
    _disable_project_rls("final_agent_runs")
    op.drop_index("ix_final_agent_runs_scope_intent", table_name="final_agent_runs")
    op.drop_index("ix_final_agent_runs_scope_external", table_name="final_agent_runs")
    op.drop_index("ix_final_agent_runs_scope_status", table_name="final_agent_runs")
    op.drop_table("final_agent_runs")


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
