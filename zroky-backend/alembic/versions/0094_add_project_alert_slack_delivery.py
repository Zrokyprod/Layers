"""add project alert slack delivery proof

Revision ID: 0094_add_project_alert_slack_delivery
Revises: 0093_add_customer_record_connector_type
Create Date: 2026-06-24 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0094_add_project_alert_slack_delivery"
down_revision = "0093_add_customer_record_connector_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("project_alerts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "slack_delivery_status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'not_attempted'"),
            )
        )
        batch_op.add_column(sa.Column("slack_delivery_attempted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("slack_delivery_error", sa.String(length=255), nullable=True))

    op.create_index(
        "ix_project_alerts_tenant_slack_delivery",
        "project_alerts",
        ["tenant_id", "slack_delivery_status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_alerts_tenant_slack_delivery", table_name="project_alerts")
    with op.batch_alter_table("project_alerts") as batch_op:
        batch_op.drop_column("slack_delivery_error")
        batch_op.drop_column("slack_delivery_attempted_at")
        batch_op.drop_column("slack_delivery_status")
