"""add google_id to users table

Revision ID: 0034_add_google_id_to_users
Revises: 0033_create_diagnosis_ui_state
Create Date: 2026-05-08 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0034_add_google_id_to_users"
down_revision = "0033_create_diagnosis_ui_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_id", sa.String(length=64), nullable=True))
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_google_id ON users (google_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_users_google_id")
    op.drop_column("users", "google_id")
