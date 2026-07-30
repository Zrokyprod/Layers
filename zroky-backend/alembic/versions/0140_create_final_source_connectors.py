"""create final source connectors

Revision ID: 0140_create_final_source_connectors
Revises: 0139_extend_recovery_outbox_statuses
Create Date: 2026-07-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0140_create_final_source_connectors"
down_revision = "0139_extend_recovery_outbox_statuses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "final_source_connectors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("capability", sa.String(length=255), nullable=False),
        sa.Column("connector_kind", sa.String(length=32), nullable=False),
        sa.Column("secret_ref", sa.String(length=255), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("connector_kind IN ('stripe')", name="ck_final_source_connectors_kind"),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_final_source_connectors_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "environment", "capability", name="ux_final_source_connectors_scope_capability"),
    )
    op.create_index(
        "ix_final_source_connectors_scope_status",
        "final_source_connectors",
        ["project_id", "environment", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_final_source_connectors_scope_status", table_name="final_source_connectors")
    op.drop_table("final_source_connectors")
