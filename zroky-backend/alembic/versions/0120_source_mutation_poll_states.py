"""Add source mutation poll state.

Revision ID: 0120_source_mutation_poll_states
Revises: 0119_action_receipts_ed25519_default
Create Date: 2026-07-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0120_source_mutation_poll_states"
down_revision = "0119_action_receipts_ed25519_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_mutation_poll_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("connector_type", sa.String(length=64), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("cursor_json", sa.Text(), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "connector_type", name="ux_source_mutation_poll_project_connector"),
    )
    op.create_index(
        "ix_source_mutation_poll_project_connector",
        "source_mutation_poll_states",
        ["project_id", "connector_type"],
        unique=False,
    )
    op.create_index(
        "ix_source_mutation_poll_last_polled",
        "source_mutation_poll_states",
        ["last_polled_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_source_mutation_poll_last_polled", table_name="source_mutation_poll_states")
    op.drop_index("ix_source_mutation_poll_project_connector", table_name="source_mutation_poll_states")
    op.drop_table("source_mutation_poll_states")
