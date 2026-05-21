"""add fix verification columns to diagnosis_pull_requests

Revision ID: 0045_add_fix_verification_columns
Revises: 0044_create_policy_documents
Create Date: 2026-05-12 02:00:00.000000

Adds replay-sandbox and judge-verdict columns required by the W9-10
fix verification pipeline:
  - replay_id           TEXT    — ID of the replay job in zroky-replay-worker
  - replay_status       VARCHAR — pending | running | pass | fail | error | skipped
  - replay_completed_at TSTZ    — when the replay run finished
  - judge_verdict       VARCHAR — pass | fail | inconclusive | null (not yet run)
  - judge_model         VARCHAR — model slug used for judging (e.g. claude-haiku-3-5)
  - judge_confidence    FLOAT   — 0.0–1.0 confidence of the verdict
  - judge_ran_at        TSTZ    — when the judge evaluation ran

Enforcement rule (grep lint):
  No PR is opened without replay_status = 'pass'.
"""

from alembic import op
import sqlalchemy as sa


revision = "0045_add_fix_verification_columns"
down_revision = "0044_create_policy_documents"
branch_labels = None
depends_on = None

_TABLE = "diagnosis_pull_requests"

_REPLAY_STATUSES = "replay_status IN ('pending','running','pass','fail','error','skipped')"
_JUDGE_VERDICTS = "judge_verdict IN ('pass','fail','inconclusive')"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("replay_id", sa.Text(), nullable=True))
    op.add_column(
        _TABLE,
        sa.Column(
            "replay_status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column(
        _TABLE, sa.Column("replay_completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(_TABLE, sa.Column("judge_verdict", sa.String(length=16), nullable=True))
    op.add_column(_TABLE, sa.Column("judge_model", sa.String(length=64), nullable=True))
    op.add_column(_TABLE, sa.Column("judge_confidence", sa.Float(), nullable=True))
    op.add_column(
        _TABLE, sa.Column("judge_ran_at", sa.DateTime(timezone=True), nullable=True)
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_diag_pr_replay_status",
            _TABLE,
            _REPLAY_STATUSES,
        )
        op.create_check_constraint(
            "ck_diag_pr_judge_verdict",
            _TABLE,
            f"judge_verdict IS NULL OR {_JUDGE_VERDICTS}",
        )

    op.create_index(
        "ix_diag_pr_tenant_replay_status",
        _TABLE,
        ["tenant_id", "replay_status"],
    )
    op.create_index(
        "ix_diag_pr_tenant_judge_verdict",
        _TABLE,
        ["tenant_id", "judge_verdict"],
    )


def downgrade() -> None:
    op.drop_index("ix_diag_pr_tenant_judge_verdict", table_name=_TABLE)
    op.drop_index("ix_diag_pr_tenant_replay_status", table_name=_TABLE)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("ck_diag_pr_judge_verdict", _TABLE, type_="check")
        op.drop_constraint("ck_diag_pr_replay_status", _TABLE, type_="check")

    op.drop_column(_TABLE, "judge_ran_at")
    op.drop_column(_TABLE, "judge_confidence")
    op.drop_column(_TABLE, "judge_model")
    op.drop_column(_TABLE, "judge_verdict")
    op.drop_column(_TABLE, "replay_completed_at")
    op.drop_column(_TABLE, "replay_status")
    op.drop_column(_TABLE, "replay_id")
