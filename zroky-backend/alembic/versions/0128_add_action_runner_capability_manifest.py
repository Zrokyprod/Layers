"""add action runner capability manifest

Revision ID: 0128_add_action_runner_capability_manifest
Revises: 0127_create_final_connector_capability_drafts
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0128_add_action_runner_capability_manifest"
down_revision = "0127_create_final_connector_capability_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "action_runners",
        sa.Column("capability_manifest_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("action_runners", "capability_manifest_json")
