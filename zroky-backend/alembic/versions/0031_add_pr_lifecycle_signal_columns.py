"""Add PR lifecycle signal columns

Revision ID: 0031
Revises: 0030
Create Date: 2026-05-06

"""

from alembic import op
import sqlalchemy as sa


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("diagnosis_pull_requests", sa.Column("fix_id", sa.String(length=128), nullable=True))
    op.add_column("diagnosis_pull_requests", sa.Column("merge_commit_sha", sa.String(length=64), nullable=True))
    op.add_column("diagnosis_pull_requests", sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("diagnosis_pull_requests", sa.Column("last_ci_state", sa.String(length=32), nullable=True))
    op.add_column("diagnosis_pull_requests", sa.Column("last_ci_conclusion", sa.String(length=64), nullable=True))
    op.add_column("diagnosis_pull_requests", sa.Column("last_ci_completed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_diag_pr_tenant_fix", "diagnosis_pull_requests", ["tenant_id", "fix_id"])
    op.create_index(
        "ix_diag_pr_repo_number",
        "diagnosis_pull_requests",
        ["repository_owner", "repository_name", "pull_request_number"],
    )
    op.create_index(
        "ix_diag_pr_repo_branch",
        "diagnosis_pull_requests",
        ["repository_owner", "repository_name", "branch_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_diag_pr_repo_branch", table_name="diagnosis_pull_requests")
    op.drop_index("ix_diag_pr_repo_number", table_name="diagnosis_pull_requests")
    op.drop_index("ix_diag_pr_tenant_fix", table_name="diagnosis_pull_requests")

    op.drop_column("diagnosis_pull_requests", "last_ci_completed_at")
    op.drop_column("diagnosis_pull_requests", "last_ci_conclusion")
    op.drop_column("diagnosis_pull_requests", "last_ci_state")
    op.drop_column("diagnosis_pull_requests", "merged_at")
    op.drop_column("diagnosis_pull_requests", "merge_commit_sha")
    op.drop_column("diagnosis_pull_requests", "fix_id")
