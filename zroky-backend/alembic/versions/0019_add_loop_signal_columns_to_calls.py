"""add loop signal columns to calls

Revision ID: 0019_add_loop_signal_columns_to_calls
Revises: 0018_add_currency_audit_columns_to_calls
Create Date: 2026-04-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_add_loop_signal_columns_to_calls"
down_revision = "0018_add_currency_audit_columns_to_calls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("output_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("calls", sa.Column("tool_lifecycle_summary_json", sa.Text(), nullable=True))
    op.add_column("calls", sa.Column("retry_metadata_json", sa.Text(), nullable=True))
    op.create_index(
        "ix_calls_project_output_fingerprint_created",
        "calls",
        ["project_id", "output_fingerprint", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_calls_project_output_fingerprint_created", table_name="calls")
    op.drop_column("calls", "retry_metadata_json")
    op.drop_column("calls", "tool_lifecycle_summary_json")
    op.drop_column("calls", "output_fingerprint")
