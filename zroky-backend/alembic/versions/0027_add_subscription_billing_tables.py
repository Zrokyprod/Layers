"""Add subscription billing tables

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-05

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0027"
down_revision = "0026_add_invitations_notifications_platform_llm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("monthly_cost_usd", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("annual_cost_usd", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("max_projects", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("max_members_per_project", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("max_calls_per_month", sa.Integer(), nullable=True),
        sa.Column("max_tokens_per_month", sa.Integer(), nullable=True),
        sa.Column("features_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_subscription_plans_slug", "subscription_plans", ["slug"], unique=True)
    op.create_index("ix_subscription_plans_active", "subscription_plans", ["is_active"])

    op.create_table(
        "tenant_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "plan_id",
            sa.String(36),
            sa.ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("billing_interval", sa.String(16), nullable=False, server_default=sa.text("'monthly'")),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "current_period_start",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "current_period_end",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seats", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_tenant_subscriptions_tenant", "tenant_subscriptions", ["tenant_id"], unique=True)
    op.create_index("ix_tenant_subscriptions_plan", "tenant_subscriptions", ["plan_id"])
    op.create_index("ix_tenant_subscriptions_status", "tenant_subscriptions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tenant_subscriptions_status", table_name="tenant_subscriptions")
    op.drop_index("ix_tenant_subscriptions_plan", table_name="tenant_subscriptions")
    op.drop_index("ix_tenant_subscriptions_tenant", table_name="tenant_subscriptions")
    op.drop_table("tenant_subscriptions")

    op.drop_index("ix_subscription_plans_active", table_name="subscription_plans")
    op.drop_index("ix_subscription_plans_slug", table_name="subscription_plans")
    op.drop_table("subscription_plans")
