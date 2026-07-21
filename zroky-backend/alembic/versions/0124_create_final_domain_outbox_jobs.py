"""create final domain outbox jobs

Revision ID: 0124_create_final_domain_outbox_jobs
Revises: 0123_create_final_domain_tables
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0124_create_final_domain_outbox_jobs"
down_revision = "0123_create_final_domain_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "final_domain_outbox_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("payload_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("claimed_by", sa.String(length=128), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "job_type IN ('verify_outcome','plan_recovery','execute_recovery','generate_evidence')",
            name="ck_final_domain_outbox_jobs_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','claimed','running','succeeded','retrying','dead')",
            name="ck_final_domain_outbox_jobs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "environment", "idempotency_key", name="ux_final_outbox_scope_idempotency"),
    )
    op.create_index(
        "ix_final_outbox_scope_status",
        "final_domain_outbox_jobs",
        ["project_id", "environment", "status", "available_at"],
    )
    op.create_index(
        "ix_final_outbox_aggregate",
        "final_domain_outbox_jobs",
        ["project_id", "environment", "aggregate_type", "aggregate_id"],
    )
    op.create_index("ix_final_outbox_lease", "final_domain_outbox_jobs", ["status", "lease_expires_at"])
    _enable_project_rls("final_domain_outbox_jobs")


def downgrade() -> None:
    _disable_project_rls("final_domain_outbox_jobs")
    op.drop_index("ix_final_outbox_lease", table_name="final_domain_outbox_jobs")
    op.drop_index("ix_final_outbox_aggregate", table_name="final_domain_outbox_jobs")
    op.drop_index("ix_final_outbox_scope_status", table_name="final_domain_outbox_jobs")
    op.drop_table("final_domain_outbox_jobs")


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
