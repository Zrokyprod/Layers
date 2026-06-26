"""create usage meter counts

Revision ID: 0101_create_usage_meter_counts
Revises: 0100_create_source_mutation_records
Create Date: 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0101_create_usage_meter_counts"
down_revision = "0100_create_source_mutation_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_meter_counts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False, comment="YYYY-MM"),
        sa.Column("meter_key", sa.String(length=80), nullable=False),
        sa.Column("usage_count", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_usage_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "month",
            "meter_key",
            name="ux_usage_meter_counts_tenant_month_meter",
        ),
    )
    op.create_index(
        "ix_usage_meter_counts_tenant_month",
        "usage_meter_counts",
        ["tenant_id", "month"],
    )
    op.create_index(
        "ix_usage_meter_counts_tenant_meter_month",
        "usage_meter_counts",
        ["tenant_id", "meter_key", "month"],
    )


def downgrade() -> None:
    op.drop_index("ix_usage_meter_counts_tenant_meter_month", table_name="usage_meter_counts")
    op.drop_index("ix_usage_meter_counts_tenant_month", table_name="usage_meter_counts")
    op.drop_table("usage_meter_counts")
