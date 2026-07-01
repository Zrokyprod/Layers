"""add connector oauth refresh token fields

Revision ID: 0113_add_connector_oauth_refresh_token_fields
Revises: 0112_add_zoho_crm_connector_type
Create Date: 2026-06-30 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0113_add_connector_oauth_refresh_token_fields"
down_revision = "0112_add_zoho_crm_connector_type"
branch_labels = None
depends_on = None


_TABLE = "system_of_record_connector_configs"


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.add_column(
            sa.Column("oauth_refresh_token_ciphertext", sa.LargeBinary(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("oauth_refresh_token_fingerprint", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("oauth_refresh_token_last4", sa.String(length=8), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_column("oauth_refresh_token_last4")
        batch_op.drop_column("oauth_refresh_token_fingerprint")
        batch_op.drop_column("oauth_refresh_token_ciphertext")
