"""add persisted evaluation settings

Revision ID: 0075_add_evaluation_settings_json
Revises: 0074_add_api_key_expiry_rotation_scopes
Create Date: 2026-05-26 19:45:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0075_add_evaluation_settings_json"
down_revision = "0074_add_api_key_expiry_rotation_scopes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_dashboard_configs",
        sa.Column("evaluation_settings_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("project_dashboard_configs", "evaluation_settings_json")
