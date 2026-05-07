"""Add feature flags table

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-05

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled_globally", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("enabled_tenants_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("disabled_tenants_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), onupdate=sa.text("now()")),
    )
    op.create_index("ix_feature_flags_key", "feature_flags", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_feature_flags_key", table_name="feature_flags")
    op.drop_table("feature_flags")
