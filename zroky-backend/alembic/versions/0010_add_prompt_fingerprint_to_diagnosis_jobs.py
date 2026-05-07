"""add prompt_fingerprint to diagnosis_jobs

Revision ID: 0010_add_prompt_fingerprint_to_diagnosis_jobs
Revises: 0009_enable_rls_for_additional_tenant_tables
Create Date: 2026-04-25 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0010_add_prompt_fingerprint_to_diagnosis_jobs"
down_revision = "0009_enable_rls_for_additional_tenant_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "diagnosis_jobs",
        sa.Column("prompt_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_diagnosis_jobs_tenant_prompt_created",
        "diagnosis_jobs",
        ["tenant_id", "prompt_fingerprint", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_diagnosis_jobs_tenant_prompt_created", table_name="diagnosis_jobs")
    op.drop_column("diagnosis_jobs", "prompt_fingerprint")
