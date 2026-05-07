"""add retention purge indexes

Revision ID: 0020_add_retention_purge_indexes
Revises: 0019_add_loop_signal_columns_to_calls
Create Date: 2026-04-28
"""

from alembic import op


revision = "0020_add_retention_purge_indexes"
down_revision = "0019_add_loop_signal_columns_to_calls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_diagnosis_jobs_tenant_created",
        "diagnosis_jobs",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_diagnosis_feedback_tenant_created",
        "diagnosis_feedback",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_diagnosis_share_tokens_tenant_expires",
        "diagnosis_share_tokens",
        ["tenant_id", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_diagnosis_fix_watches_tenant_watch_expires",
        "diagnosis_fix_watches",
        ["tenant_id", "watch_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_project_alerts_tenant_created",
        "project_alerts",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_alerts_tenant_created", table_name="project_alerts")
    op.drop_index("ix_diagnosis_fix_watches_tenant_watch_expires", table_name="diagnosis_fix_watches")
    op.drop_index("ix_diagnosis_share_tokens_tenant_expires", table_name="diagnosis_share_tokens")
    op.drop_index("ix_diagnosis_feedback_tenant_created", table_name="diagnosis_feedback")
    op.drop_index("ix_diagnosis_jobs_tenant_created", table_name="diagnosis_jobs")
