"""create diagnosis_ui_state table

Revision ID: 0033_create_diagnosis_ui_state
Revises: 0032
Create Date: 2026-05-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0033_create_diagnosis_ui_state"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_ui_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("diagnosis_id", sa.String(length=64), nullable=False),
        sa.Column("assigned_subject", sa.String(length=255), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.UniqueConstraint("tenant_id", "diagnosis_id", name="ux_diagnosis_ui_state_tenant_diagnosis"),
    )
    op.create_index(
        "ix_diagnosis_ui_state_tenant_updated",
        "diagnosis_ui_state",
        ["tenant_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_diagnosis_ui_state_diagnosis_id",
        "diagnosis_ui_state",
        ["diagnosis_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_diagnosis_ui_state_diagnosis_id", table_name="diagnosis_ui_state")
    op.drop_index("ix_diagnosis_ui_state_tenant_updated", table_name="diagnosis_ui_state")
    op.drop_table("diagnosis_ui_state")
