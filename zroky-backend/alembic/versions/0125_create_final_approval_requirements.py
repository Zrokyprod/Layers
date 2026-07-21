"""create final approval requirements

Revision ID: 0125_create_final_approval_requirements
Revises: 0124_create_final_domain_outbox_jobs
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0125_create_final_approval_requirements"
down_revision = "0124_create_final_domain_outbox_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "final_approval_requirements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("intent_id", sa.String(length=36), nullable=False),
        sa.Column("policy_decision_id", sa.String(length=36), nullable=False),
        sa.Column("required_role", sa.String(length=32), server_default=sa.text("'admin'"), nullable=False),
        sa.Column("binding_digest", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("required_role IN ('admin','owner')", name="ck_final_approval_requirements_role"),
        sa.CheckConstraint("status IN ('pending','approved','denied')", name="ck_final_approval_requirements_status"),
        sa.ForeignKeyConstraint(["intent_id"], ["final_workflow_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_decision_id"], ["final_policy_decisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "environment", "policy_decision_id", name="ux_final_approvals_scope_decision"),
    )
    op.create_index(
        "ix_final_approvals_scope_status",
        "final_approval_requirements",
        ["project_id", "environment", "status", "created_at"],
    )
    _enable_project_rls("final_approval_requirements")


def downgrade() -> None:
    _disable_project_rls("final_approval_requirements")
    op.drop_index("ix_final_approvals_scope_status", table_name="final_approval_requirements")
    op.drop_table("final_approval_requirements")


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
