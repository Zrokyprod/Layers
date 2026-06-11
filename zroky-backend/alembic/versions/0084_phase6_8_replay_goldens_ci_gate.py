"""phase 6-8 replay proof, goldens history, ci gate overrides

Revision ID: 0084_phase6_8_replay_goldens_ci_gate
Revises: 0083_phase5_failure_intelligence
Create Date: 2026-06-11 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0084_phase6_8_replay_goldens_ci_gate"
down_revision = "0083_phase5_failure_intelligence"
branch_labels = None
depends_on = None


def _replace_replay_status_checks() -> None:
    op.execute("ALTER TABLE replay_runs DROP CONSTRAINT IF EXISTS ck_replay_runs_status")
    op.create_check_constraint(
        "ck_replay_runs_status",
        "replay_runs",
        "status IN ('pending', 'running', 'pass', 'warn', 'fail', 'not_verified', 'error')",
    )
    op.execute("ALTER TABLE replay_run_traces DROP CONSTRAINT IF EXISTS ck_replay_run_traces_status")
    op.create_check_constraint(
        "ck_replay_run_traces_status",
        "replay_run_traces",
        "status IN ('pass', 'fail', 'not_verified', 'error')",
    )


def _restore_replay_status_checks() -> None:
    op.execute("ALTER TABLE replay_runs DROP CONSTRAINT IF EXISTS ck_replay_runs_status")
    op.create_check_constraint(
        "ck_replay_runs_status",
        "replay_runs",
        "status IN ('pending', 'running', 'pass', 'fail', 'error')",
    )
    op.execute("ALTER TABLE replay_run_traces DROP CONSTRAINT IF EXISTS ck_replay_run_traces_status")
    op.create_check_constraint(
        "ck_replay_run_traces_status",
        "replay_run_traces",
        "status IN ('pass', 'fail', 'error')",
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _replace_replay_status_checks()

    op.create_table(
        "golden_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("golden_set_id", sa.String(length=36), nullable=True),
        sa.Column("golden_trace_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["golden_set_id"], ["golden_sets.id"], name="fk_golden_history_set_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["golden_trace_id"], ["golden_traces.id"], name="fk_golden_history_trace_id", ondelete="SET NULL"),
    )
    op.create_index("ix_golden_history_project_created", "golden_history", ["project_id", "created_at"])
    op.create_index("ix_golden_history_set_created", "golden_history", ["golden_set_id", "created_at"])
    op.create_index("ix_golden_history_trace_created", "golden_history", ["golden_trace_id", "created_at"])

    op.create_table(
        "ci_gate_overrides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("original_status", sa.String(length=16), nullable=False),
        sa.Column("effective_status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["replay_runs.id"], name="fk_ci_gate_overrides_run_id", ondelete="CASCADE"),
        sa.CheckConstraint(
            "original_status IN ('pass', 'fail', 'warn', 'not_verified', 'error')",
            name="ck_ci_gate_overrides_original_status",
        ),
        sa.CheckConstraint(
            "effective_status IN ('pass', 'warn')",
            name="ck_ci_gate_overrides_effective_status",
        ),
    )
    op.create_index("ix_ci_gate_overrides_project_run_created", "ci_gate_overrides", ["project_id", "run_id", "created_at"])
    op.create_index("ix_ci_gate_overrides_run_created", "ci_gate_overrides", ["run_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ci_gate_overrides_run_created", table_name="ci_gate_overrides")
    op.drop_index("ix_ci_gate_overrides_project_run_created", table_name="ci_gate_overrides")
    op.drop_table("ci_gate_overrides")

    op.drop_index("ix_golden_history_trace_created", table_name="golden_history")
    op.drop_index("ix_golden_history_set_created", table_name="golden_history")
    op.drop_index("ix_golden_history_project_created", table_name="golden_history")
    op.drop_table("golden_history")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _restore_replay_status_checks()
