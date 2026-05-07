"""add agent_name and loop query index to diagnosis_jobs

Revision ID: 0011_add_agent_name_loop_index_to_diagnosis_jobs
Revises: 0010_add_prompt_fingerprint_to_diagnosis_jobs
Create Date: 2026-04-25 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0011_add_agent_name_loop_index_to_diagnosis_jobs"
down_revision = "0010_add_prompt_fingerprint_to_diagnosis_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "diagnosis_jobs",
        sa.Column("agent_name", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_diagnosis_jobs_tenant_agent_prompt_created",
        "diagnosis_jobs",
        ["tenant_id", "agent_name", "prompt_fingerprint", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_diagnosis_jobs_tenant_agent_prompt_created", table_name="diagnosis_jobs")
    op.drop_column("diagnosis_jobs", "agent_name")
