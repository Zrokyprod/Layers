"""drop legacy Teams integration install table

Revision ID: 0089_drop_legacy_teams_install
Revises: 0088_drop_legacy_stripe_billing_artifacts
Create Date: 2026-06-19 00:00:00.000000

Teams integration is no longer a product surface. Keep historical migrations
intact, but remove the active table through a forward migration.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0089_drop_legacy_teams_install"
down_revision = "0088_drop_legacy_stripe_billing_artifacts"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("tenant_teams_install"):
        op.drop_table("tenant_teams_install")


def downgrade() -> None:
    if _has_table("tenant_teams_install"):
        return

    op.create_table(
        "tenant_teams_install",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("webhook_url_encrypted", sa.Text(), nullable=False),
        sa.Column("channel_name", sa.String(length=255), nullable=True),
        sa.Column(
            "connector_type",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'webhook'"),
        ),
        sa.Column("installed_by_user", sa.String(length=255), nullable=True),
        sa.Column(
            "installed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="ux_tenant_teams_install_tenant"),
    )
    op.create_index(
        "ix_tenant_teams_install_updated_at",
        "tenant_teams_install",
        ["updated_at"],
    )
