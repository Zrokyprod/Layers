"""create replay_runs + replay_run_traces (Pilot tier batch-replay engine)

Revision ID: 0050_create_replay_runs_and_traces
Revises: 0049_create_golden_sets_and_traces
Create Date: 2026-05-13 16:30:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §5.2 / §6.4):
  - replay_runs:        one batch invocation of "replay every trace in this
                        golden set against the current model+prompt config".
                        Triggered manually, by GitHub Action, or on schedule.
                        Aggregate pass/fail summary lives in summary_json.
  - replay_run_traces:  per-trace outcome inside a run. judge_scores_json
                        carries the multi-judge score breakdown; diff_metric
                        is the headline composite delta vs the golden output.
  - These are DISTINCT from the legacy `replay_jobs` table (single-fix
    customer-hosted replay). `replay_runs` is server-side, batch-scoped, and
    keyed by golden_set_id.
  - project_id is denormalised onto replay_run_traces so the RLS policy can
    filter by tenant without a JOIN through replay_runs (same pattern as
    golden_traces).
  - Foreign keys:
        replay_runs.golden_set_id          → golden_sets.id  ON DELETE CASCADE
        replay_run_traces.replay_run_id    → replay_runs.id  ON DELETE CASCADE
        replay_run_traces.golden_trace_id  → golden_traces.id ON DELETE SET NULL
            (preserve historical run record even if the trace is later removed)
        replay_run_traces.call_id_replayed → calls.id        ON DELETE SET NULL
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0050_create_replay_runs_and_traces"
down_revision = "0049_create_golden_sets_and_traces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── replay_runs ──────────────────────────────────────────────────────────
    op.create_table(
        "replay_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("golden_set_id", sa.String(length=36), nullable=False),
        sa.Column(
            "trigger",
            sa.String(length=16),
            nullable=False,
            comment="'manual' | 'github' | 'schedule'",
        ),
        sa.Column("git_sha", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="'pending' | 'running' | 'pass' | 'fail' | 'error'",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "summary_json",
            sa.Text(),
            nullable=True,
            comment="JSON: aggregate pass/fail counts + per-judge averages",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["golden_set_id"],
            ["golden_sets.id"],
            name="fk_replay_runs_golden_set_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "trigger IN ('manual', 'github', 'schedule')",
            name="ck_replay_runs_trigger",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'pass', 'fail', 'error')",
            name="ck_replay_runs_status",
        ),
    )
    op.create_index(
        "ix_replay_runs_project_created",
        "replay_runs",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_replay_runs_project_status",
        "replay_runs",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_replay_runs_golden_set_id",
        "replay_runs",
        ["golden_set_id"],
    )

    # ── replay_run_traces ────────────────────────────────────────────────────
    op.create_table(
        "replay_run_traces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("replay_run_id", sa.String(length=36), nullable=False),
        sa.Column("golden_trace_id", sa.String(length=36), nullable=True),
        sa.Column(
            "project_id",
            sa.String(length=64),
            nullable=False,
            comment="Denormalised from parent replay_run for RLS without JOIN",
        ),
        sa.Column("call_id_replayed", sa.String(length=64), nullable=True),
        sa.Column(
            "judge_scores_json",
            sa.Text(),
            nullable=True,
            comment="JSON: { judge_name: score } from multi-judge ensemble",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            comment="'pass' | 'fail' | 'error'",
        ),
        sa.Column(
            "diff_metric",
            sa.Float(),
            nullable=True,
            comment="Composite delta vs golden output; smaller = closer match",
        ),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["replay_run_id"],
            ["replay_runs.id"],
            name="fk_replay_run_traces_run_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["golden_trace_id"],
            ["golden_traces.id"],
            name="fk_replay_run_traces_golden_trace_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["call_id_replayed"],
            ["calls.id"],
            name="fk_replay_run_traces_call_id_replayed",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('pass', 'fail', 'error')",
            name="ck_replay_run_traces_status",
        ),
    )
    op.create_index(
        "ix_replay_run_traces_run_id",
        "replay_run_traces",
        ["replay_run_id"],
    )
    op.create_index(
        "ix_replay_run_traces_golden_trace_id",
        "replay_run_traces",
        ["golden_trace_id"],
    )
    op.create_index(
        "ix_replay_run_traces_project_created",
        "replay_run_traces",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_replay_run_traces_run_status",
        "replay_run_traces",
        ["replay_run_id", "status"],
    )

    # ── RLS (Postgres only) ──────────────────────────────────────────────────
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table_name in ("replay_runs", "replay_run_traces"):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")
        op.execute(
            f"""
            CREATE POLICY {table_name}_tenant_isolation
            ON {table_name}
            USING (project_id = current_setting('app.current_tenant_id', true))
            WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table_name in ("replay_run_traces", "replay_runs"):
            op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_replay_run_traces_run_status", table_name="replay_run_traces")
    op.drop_index("ix_replay_run_traces_project_created", table_name="replay_run_traces")
    op.drop_index("ix_replay_run_traces_golden_trace_id", table_name="replay_run_traces")
    op.drop_index("ix_replay_run_traces_run_id", table_name="replay_run_traces")
    op.drop_table("replay_run_traces")

    op.drop_index("ix_replay_runs_golden_set_id", table_name="replay_runs")
    op.drop_index("ix_replay_runs_project_status", table_name="replay_runs")
    op.drop_index("ix_replay_runs_project_created", table_name="replay_runs")
    op.drop_table("replay_runs")
