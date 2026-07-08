"""add user totp mfa fields

Revision ID: 0121_add_user_totp_mfa
Revises: 0120_source_mutation_poll_states
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0121_add_user_totp_mfa"
down_revision = "0120_source_mutation_poll_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("totp_enabled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "totp_enabled_at")
    op.drop_column("users", "totp_secret")
