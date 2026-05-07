"""add currency audit columns to calls

Revision ID: 0018_add_currency_audit_columns_to_calls
Revises: 0017_add_cost_trust_columns_to_calls
Create Date: 2026-04-27 04:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_add_currency_audit_columns_to_calls"
down_revision = "0017_add_cost_trust_columns_to_calls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("pricing_source", sa.String(length=32), nullable=True))
    op.add_column("calls", sa.Column("cost_currency", sa.String(length=3), server_default=sa.text("'USD'"), nullable=False))
    op.add_column("calls", sa.Column("token_unit", sa.String(length=32), server_default=sa.text("'tokens'"), nullable=False))
    op.add_column("calls", sa.Column("exchange_rate_usd_to_inr", sa.Numeric(precision=18, scale=8), nullable=True))
    op.add_column("calls", sa.Column("exchange_rate_timestamp", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calls", sa.Column("exchange_rate_source", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_calls_project_exchange_rate_timestamp",
        "calls",
        ["project_id", "exchange_rate_timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_calls_project_exchange_rate_timestamp", table_name="calls")
    op.drop_column("calls", "exchange_rate_source")
    op.drop_column("calls", "exchange_rate_timestamp")
    op.drop_column("calls", "exchange_rate_usd_to_inr")
    op.drop_column("calls", "token_unit")
    op.drop_column("calls", "cost_currency")
    op.drop_column("calls", "pricing_source")
