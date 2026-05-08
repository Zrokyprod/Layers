"""add email_verified_at and email_verification_token to users

Revision ID: 0035_add_email_verification_to_users
Revises: 0034_add_google_id_to_users
Create Date: 2026-05-08 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0035_add_email_verification_to_users"
down_revision = "0034_add_google_id_to_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("email_verification_token", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email_verification_token")
    op.drop_column("users", "email_verified_at")
