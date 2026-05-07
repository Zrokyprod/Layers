"""create project alerts and dashboard config tables

Revision ID: 0006_create_project_alerts_and_dashboard_configs
Revises: 0005_create_diagnosis_feedback_and_share_tokens
Create Date: 2026-04-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0006_create_project_alerts_and_dashboard_configs"
down_revision = "0005_create_diagnosis_feedback_and_share_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_alerts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("diagnosis_id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default=sa.text("'medium'"), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column("source", sa.String(length=64), server_default=sa.text("'diagnosis_engine'"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "diagnosis_id", "category", name="ux_project_alerts_tenant_diagnosis_category"),
    )
    op.create_index(
        "ix_project_alerts_tenant_status_created",
        "project_alerts",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_project_alerts_tenant_category",
        "project_alerts",
        ["tenant_id", "category"],
        unique=False,
    )

    op.create_table(
        "project_dashboard_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("monthly_budget_usd", sa.Float(), nullable=True),
        sa.Column("budget_threshold_percentage", sa.Float(), server_default=sa.text("80"), nullable=False),
        sa.Column("retention_days", sa.Integer(), server_default=sa.text("30"), nullable=False),
        sa.Column("pii_custom_patterns_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("notifications_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("provider_verifications_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="ux_project_dashboard_configs_tenant"),
    )
    op.create_index(
        "ix_project_dashboard_configs_updated_at",
        "project_dashboard_configs",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_dashboard_configs_updated_at", table_name="project_dashboard_configs")
    op.drop_table("project_dashboard_configs")

    op.drop_index("ix_project_alerts_tenant_category", table_name="project_alerts")
    op.drop_index("ix_project_alerts_tenant_status_created", table_name="project_alerts")
    op.drop_table("project_alerts")
