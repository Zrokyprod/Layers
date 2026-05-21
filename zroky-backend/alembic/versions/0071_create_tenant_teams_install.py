"""create tenant_teams_install table.

Revision ID: 0071_create_tenant_teams_install
Revises: 0070_create_tenant_slack_install
Create Date: 2026-05-21 00:10:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0071_create_tenant_teams_install"
down_revision = "0070_create_tenant_slack_install"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_teams_install",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("webhook_url_encrypted", sa.Text(), nullable=False),
        sa.Column("channel_name", sa.String(255), nullable=True),
        sa.Column("connector_type", sa.String(32), nullable=False, server_default=sa.text("'webhook'")),
        sa.Column("installed_by_user", sa.String(255), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="ux_tenant_teams_install_tenant"),
    )
    op.create_index("ix_tenant_teams_install_updated_at", "tenant_teams_install", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_tenant_teams_install_updated_at", table_name="tenant_teams_install")
    op.drop_table("tenant_teams_install")
