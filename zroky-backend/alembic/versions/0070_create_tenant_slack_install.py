"""create tenant_slack_install table.

Revision ID: 0070_create_tenant_slack_install
Revises: 0069_create_reliability_recommendations
Create Date: 2026-05-21 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0070_create_tenant_slack_install"
down_revision = "0069_create_reliability_recommendations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_slack_install",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("team_id", sa.String(64), nullable=False),
        sa.Column("team_name", sa.String(255), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("channel_id", sa.String(64), nullable=True),
        sa.Column("channel_name", sa.String(255), nullable=True),
        sa.Column("bot_user_id", sa.String(64), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("installed_by_user", sa.String(255), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="ux_tenant_slack_install_tenant"),
    )
    op.create_index("ix_tenant_slack_install_team_id", "tenant_slack_install", ["team_id"])
    op.create_index("ix_tenant_slack_install_channel_id", "tenant_slack_install", ["channel_id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_slack_install_channel_id", table_name="tenant_slack_install")
    op.drop_index("ix_tenant_slack_install_team_id", table_name="tenant_slack_install")
    op.drop_table("tenant_slack_install")
