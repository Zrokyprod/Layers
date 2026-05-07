"""create diagnosis fix watch table

Revision ID: 0008_create_diagnosis_fix_watches
Revises: 0007_add_user_auth_columns
Create Date: 2026-04-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0008_create_diagnosis_fix_watches"
down_revision = "0007_add_user_auth_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_fix_watches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("diagnosis_id", sa.String(length=64), nullable=False),
        sa.Column("target_categories_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("watch_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "diagnosis_id", name="ux_diagnosis_fix_watches_tenant_diagnosis"),
    )
    op.create_index(
        "ix_diagnosis_fix_watches_tenant_resolved_at",
        "diagnosis_fix_watches",
        ["tenant_id", "resolved_at"],
        unique=False,
    )
    op.create_index(
        "ix_diagnosis_fix_watches_watch_expires_at",
        "diagnosis_fix_watches",
        ["watch_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_diagnosis_fix_watches_watch_expires_at", table_name="diagnosis_fix_watches")
    op.drop_index("ix_diagnosis_fix_watches_tenant_resolved_at", table_name="diagnosis_fix_watches")
    op.drop_table("diagnosis_fix_watches")
