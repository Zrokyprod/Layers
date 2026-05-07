"""Add project_invitations, notifications, platform_llm_usage tables.

Revision ID: 0026_add_invitations_notifications_platform_llm
Revises: 0025_partition_high_volume_tables
Create Date: 2026-05-05 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0026_add_invitations_notifications_platform_llm"
down_revision = "0025_partition_high_volume_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # project_invitations
    op.create_table(
        "project_invitations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), server_default=sa.text("'member'"), nullable=False),
        sa.Column("invited_by_subject", sa.String(length=255), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "email", name="ux_project_invitations_project_email"),
    )
    op.create_index("ix_project_invitations_token_hash", "project_invitations", ["token_hash"], unique=True)
    op.create_index("ix_project_invitations_project_id", "project_invitations", ["project_id"], unique=False)
    op.create_index("ix_project_invitations_email", "project_invitations", ["email"], unique=False)

    # notifications
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False, server_default=sa.text("'general'")),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("action_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"], unique=False)
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "is_read"], unique=False)
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"], unique=False)

    # platform_llm_usage
    op.create_table(
        "platform_llm_usage",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False, server_default=sa.text("'openrouter'")),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_usd", sa.Numeric(18, 8), server_default=sa.text("0"), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("request_json", sa.Text(), nullable=True),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("diagnosis_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_llm_usage_purpose", "platform_llm_usage", ["purpose"], unique=False)
    op.create_index("ix_platform_llm_usage_created", "platform_llm_usage", ["created_at"], unique=False)
    op.create_index("ix_platform_llm_usage_tenant", "platform_llm_usage", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_platform_llm_usage_tenant", table_name="platform_llm_usage")
    op.drop_index("ix_platform_llm_usage_created", table_name="platform_llm_usage")
    op.drop_index("ix_platform_llm_usage_purpose", table_name="platform_llm_usage")
    op.drop_table("platform_llm_usage")

    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_project_invitations_email", table_name="project_invitations")
    op.drop_index("ix_project_invitations_project_id", table_name="project_invitations")
    op.drop_index("ix_project_invitations_token_hash", table_name="project_invitations")
    op.drop_table("project_invitations")
