"""add diagnosis pull request links table

Revision ID: 0012_add_diagnosis_pull_requests
Revises: 0011_add_agent_name_loop_index_to_diagnosis_jobs
Create Date: 2026-04-25 02:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0012_add_diagnosis_pull_requests"
down_revision = "0011_add_agent_name_loop_index_to_diagnosis_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_pull_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("diagnosis_id", sa.String(length=64), nullable=False),
        sa.Column("repository_owner", sa.String(length=255), nullable=False),
        sa.Column("repository_name", sa.String(length=255), nullable=False),
        sa.Column("base_branch", sa.String(length=255), nullable=False),
        sa.Column("branch_name", sa.String(length=255), nullable=False),
        sa.Column("pull_request_number", sa.Integer(), nullable=False),
        sa.Column("pull_request_url", sa.String(length=2048), nullable=False),
        sa.Column("pull_request_title", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("generated_patch", sa.Text(), nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "diagnosis_id", "branch_name", name="ux_diag_pr_tenant_diag_branch"),
        sa.UniqueConstraint("tenant_id", "diagnosis_id", "pull_request_url", name="ux_diag_pr_tenant_diag_url"),
    )
    op.create_index(
        "ix_diag_pr_tenant_diagnosis",
        "diagnosis_pull_requests",
        ["tenant_id", "diagnosis_id"],
        unique=False,
    )
    op.create_index(
        "ix_diag_pr_tenant_created",
        "diagnosis_pull_requests",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_diag_pr_tenant_created", table_name="diagnosis_pull_requests")
    op.drop_index("ix_diag_pr_tenant_diagnosis", table_name="diagnosis_pull_requests")
    op.drop_table("diagnosis_pull_requests")
