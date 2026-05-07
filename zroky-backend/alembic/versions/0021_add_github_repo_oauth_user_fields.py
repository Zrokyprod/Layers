"""add user github repo oauth fields

Revision ID: 0021_add_github_repo_oauth_user_fields
Revises: 0020_add_retention_purge_indexes
Create Date: 2026-04-28 16:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0021_add_github_repo_oauth_user_fields"
down_revision = "0020_add_retention_purge_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("github_login", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("github_token_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("github_token_scopes", sa.String(length=1024), nullable=True))
    op.add_column("users", sa.Column("github_token_connected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("github_token_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "github_token_updated_at")
    op.drop_column("users", "github_token_connected_at")
    op.drop_column("users", "github_token_scopes")
    op.drop_column("users", "github_token_encrypted")
    op.drop_column("users", "github_login")
