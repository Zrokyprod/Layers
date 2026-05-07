"""0007 — Add auth columns to users table (password_hash, github_id, display_name)."""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0007_add_user_auth_columns"
down_revision = "0006_create_project_alerts_and_dashboard_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("github_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(120), nullable=True),
    )
    # Unique constraint on email (may already have non-unique index from 0003)
    with op.batch_alter_table("users") as batch_op:
        try:
            batch_op.create_unique_constraint("ux_users_email", ["email"])
        except Exception:
            pass  # already exists in some DB backends
        try:
            batch_op.create_unique_constraint("ux_users_github_id", ["github_id"])
        except Exception:
            pass
        try:
            batch_op.create_unique_constraint("ux_users_subject", ["subject"])
        except Exception:
            pass


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        for constraint in ("ux_users_email", "ux_users_github_id", "ux_users_subject"):
            try:
                batch_op.drop_constraint(constraint, type_="unique")
            except Exception:
                pass
        batch_op.drop_column("display_name")
        batch_op.drop_column("github_id")
        batch_op.drop_column("password_hash")
