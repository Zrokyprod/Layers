"""0007 — Add auth columns to users table (password_hash, github_id, display_name)."""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0007_add_user_auth_columns"
down_revision = "0006_create_project_alerts_and_dashboard_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    try:
        op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    except Exception:
        pass
    try:
        op.add_column("users", sa.Column("github_id", sa.String(64), nullable=True))
    except Exception:
        pass
    try:
        op.add_column("users", sa.Column("display_name", sa.String(120), nullable=True))
    except Exception:
        pass
    # ux_users_subject unique index already created in 0003 — do not re-add.
    # ux_users_email: add unique constraint if not present (0003 only adds a non-unique ix).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users (email)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_github_id ON users (github_id)"
    )


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
