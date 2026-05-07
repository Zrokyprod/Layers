"""add pricing validation and rollback drill config fields

Revision ID: 0014_add_pricing_and_rollback_config_fields
Revises: 0013_create_audit_logs_table
Create Date: 2026-04-25 15:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0014_add_pricing_and_rollback_config_fields"
down_revision = "0013_create_audit_logs_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_dashboard_configs",
        sa.Column("pricing_validation_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "project_dashboard_configs",
        sa.Column("rollback_drill_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("project_dashboard_configs", "rollback_drill_json")
    op.drop_column("project_dashboard_configs", "pricing_validation_json")
