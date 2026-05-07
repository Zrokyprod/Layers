"""create users and project_memberships tables

Revision ID: 0003_create_users_and_project_memberships
Revises: 0002_create_projects_and_api_keys
Create Date: 2026-04-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_create_users_and_project_memberships"
down_revision = "0002_create_projects_and_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_users_subject", "users", ["subject"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    op.create_table(
        "project_memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), server_default=sa.text("'member'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="ux_project_memberships_project_user"),
    )
    op.create_index(
        "ix_project_memberships_project_active",
        "project_memberships",
        ["project_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_project_memberships_user_active",
        "project_memberships",
        ["user_id", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_memberships_user_active", table_name="project_memberships")
    op.drop_index("ix_project_memberships_project_active", table_name="project_memberships")
    op.drop_table("project_memberships")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ux_users_subject", table_name="users")
    op.drop_table("users")
