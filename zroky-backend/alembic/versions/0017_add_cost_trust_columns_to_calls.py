"""add cost trust columns to calls

Revision ID: 0017_add_cost_trust_columns_to_calls
Revises: 0016_create_fix_events
Create Date: 2026-04-27 03:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_add_cost_trust_columns_to_calls"
down_revision = "0016_create_fix_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("reasoning_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("calls", sa.Column("reasoning_cost_total", sa.Float(), server_default=sa.text("0"), nullable=False))
    op.add_column("calls", sa.Column("cache_savings_total", sa.Float(), server_default=sa.text("0"), nullable=False))
    op.add_column("calls", sa.Column("pricing_version", sa.String(length=64), nullable=True))
    op.add_column("calls", sa.Column("pricing_last_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calls", sa.Column("cost_confidence", sa.String(length=32), server_default=sa.text("'degraded'"), nullable=False))
    op.add_column("calls", sa.Column("confidence_reason", sa.String(length=120), nullable=True))
    op.create_index("ix_calls_project_pricing_updated", "calls", ["project_id", "pricing_last_updated_at"], unique=False)
    op.create_index("ix_calls_project_cost_confidence", "calls", ["project_id", "cost_confidence"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_calls_project_cost_confidence", table_name="calls")
    op.drop_index("ix_calls_project_pricing_updated", table_name="calls")
    op.drop_column("calls", "confidence_reason")
    op.drop_column("calls", "cost_confidence")
    op.drop_column("calls", "pricing_last_updated_at")
    op.drop_column("calls", "pricing_version")
    op.drop_column("calls", "cache_savings_total")
    op.drop_column("calls", "reasoning_cost_total")
    op.drop_column("calls", "reasoning_tokens")
