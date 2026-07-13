"""Add durable tenant-fair verification dispatch state.

Revision ID: 0127_tenant_verification_dispatch
Revises: 0126_private_runner_verification_jobs
Create Date: 2026-07-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0127_tenant_verification_dispatch"
down_revision = "0126_private_runner_verification_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verification_dispatch_states",
        sa.Column("project_id", sa.String(length=64), primary_key=True),
        sa.Column("last_dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatch_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_verification_dispatch_states_last_dispatched",
        "verification_dispatch_states",
        ["last_dispatched_at"],
    )
    # Existing outbox rows are immediately eligible after rollout; creating
    # state rows here prevents the new inner join from stranding pre-upgrade
    # verification or receipt work.
    op.execute(
        """
        INSERT INTO verification_dispatch_states (project_id)
        SELECT DISTINCT project_id
        FROM action_post_execution_jobs
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_verification_dispatch_states_last_dispatched",
        table_name="verification_dispatch_states",
    )
    op.drop_table("verification_dispatch_states")
