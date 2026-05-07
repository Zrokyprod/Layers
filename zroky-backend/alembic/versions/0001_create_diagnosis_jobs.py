"""create diagnosis_jobs table

Revision ID: 0001_create_diagnosis_jobs
Revises:
Create Date: 2026-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_create_diagnosis_jobs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("diagnosis_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_diagnosis_jobs_tenant_status",
        "diagnosis_jobs",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "ux_diagnosis_jobs_tenant_diagnosis",
        "diagnosis_jobs",
        ["tenant_id", "diagnosis_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_diagnosis_jobs_tenant_diagnosis", table_name="diagnosis_jobs")
    op.drop_index("ix_diagnosis_jobs_tenant_status", table_name="diagnosis_jobs")
    op.drop_table("diagnosis_jobs")
