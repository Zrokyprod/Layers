"""add api key expiry, rotation, and scope metadata

Revision ID: 0074_add_api_key_expiry_rotation_scopes
Revises: 0073_add_golden_set_ci_flags
Create Date: 2026-05-26 19:40:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0074_add_api_key_expiry_rotation_scopes"
down_revision = "0073_add_golden_set_ci_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column(
            "scopes_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[\"project:member\"]'"),
        ),
    )
    op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("api_keys", sa.Column("rotated_from_key_id", sa.String(length=36), nullable=True))
    op.create_index("ix_api_keys_project_expires", "api_keys", ["project_id", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_project_expires", table_name="api_keys")
    op.drop_column("api_keys", "rotated_from_key_id")
    op.drop_column("api_keys", "expires_at")
    op.drop_column("api_keys", "scopes_json")
