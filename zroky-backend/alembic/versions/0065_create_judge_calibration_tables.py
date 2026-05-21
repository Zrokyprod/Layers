"""create golden_labels + judge_calibration_runs + judge_mode_overrides tables.

Revision ID: 0065_create_judge_calibration_tables
Revises: 0064_create_provider_drift_tables
Create Date: 2026-05-18 18:00:00.000000

Schema notes (Wedge — Calibrated Judge with Public Scores):

  Three new tables that turn the existing judge_engine + judge_calibration
  in-memory drift store into a persistent, auditable, public-facing
  scoreboard:

  - golden_labels:
      Human ground-truth verdicts attached to golden_traces. Multi-labeler
      ready: many rows per trace, only one with active=true. Versioned so
      label history is preserved even after edits. The presence of an
      active label is what makes a trace eligible for calibration.

      Tenant-scoped via project_id (denormalised from parent
      golden_traces.project_id) so RLS filters without a JOIN.

  - judge_calibration_runs:
      One row per (project_id, judge_model, run_date). Idempotent re-runs
      by UNIQUE constraint. Stores the canonical 3x3 confusion matrix as
      JSON; accuracy / precision / recall / F1 / Cohen's kappa are
      derived on read so future verdict-class additions don't migrate.

      The auto-downgrade safety net writes nothing here — it writes to
      judge_mode_overrides. This table is pure observation.

  - judge_mode_overrides:
      Per-(project_id, judge_model) override of "blocking" vs "advisory"
      mode. UNIQUE on (project_id, judge_model) — exactly one active
      mode per judge per project at a time. Hysteresis lives in code:
      writes here come from the calibration runner when accuracy crosses
      the down/up thresholds. Manual overrides (founder console) also
      write here with reason='manual'.

  All three tables follow the existing project_id-scoped pattern
  (migrations 0049/0050) and add identical Postgres RLS policies in a
  follow-up SQL when the tenant_isolation alembic helper runs.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0065_create_judge_calibration_tables"
down_revision = "0064_create_provider_drift_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── golden_labels ───────────────────────────────────────────────────────
    op.create_table(
        "golden_labels",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "golden_trace_id",
            sa.String(length=36),
            nullable=False,
            comment="FK to golden_traces.id (CASCADE on parent delete).",
        ),
        sa.Column(
            "project_id",
            sa.String(length=64),
            nullable=False,
            comment="Denormalised from parent trace for RLS-without-JOIN.",
        ),
        sa.Column(
            "labeler_user_id",
            sa.String(length=64),
            nullable=True,
            comment="User id of the human labeler. NULL for system-imported labels.",
        ),
        sa.Column(
            "verdict",
            sa.String(length=16),
            nullable=False,
            comment="'pass' | 'fail' | 'inconclusive' (human ground truth).",
        ),
        sa.Column(
            "rationale",
            sa.Text(),
            nullable=True,
            comment="Optional one-sentence justification supplied by the labeler.",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Monotonic per (golden_trace_id) — incremented on each edit.",
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="True for the row used by calibration; older rows kept for audit.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["golden_trace_id"],
            ["golden_traces.id"],
            name="fk_golden_labels_trace_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "verdict IN ('pass','fail','inconclusive')",
            name="ck_golden_labels_verdict",
        ),
    )
    op.create_index(
        "ix_golden_labels_trace_active",
        "golden_labels",
        ["golden_trace_id", "active"],
    )
    op.create_index(
        "ix_golden_labels_project_created",
        "golden_labels",
        ["project_id", "created_at"],
    )

    # ── judge_calibration_runs ──────────────────────────────────────────────
    op.create_table(
        "judge_calibration_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column(
            "judge_model",
            sa.String(length=128),
            nullable=False,
            comment="OpenRouter slug or 'ensemble:N' marker.",
        ),
        sa.Column(
            "run_date",
            sa.Date(),
            nullable=False,
            comment="UTC date the run was executed for.",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'complete'"),
            comment="'pending' | 'running' | 'complete' | 'partial' | 'error'",
        ),
        sa.Column(
            "sample_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "agreement_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Cells on the diagonal of the confusion matrix.",
        ),
        sa.Column(
            "accuracy",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
            comment="agreement_count / sample_count; 0 when no samples.",
        ),
        sa.Column(
            "kappa",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Cohen's kappa adjusting for chance agreement.",
        ),
        sa.Column(
            "low_confidence_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Fraction of judge verdicts with confidence < 0.5 (0..1).",
        ),
        sa.Column(
            "confusion_matrix_json",
            sa.Text(),
            nullable=True,
            comment="JSON: 3x3 dict {judge_v: {truth_v: count}}.",
        ),
        sa.Column(
            "per_class_metrics_json",
            sa.Text(),
            nullable=True,
            comment="JSON: per-verdict precision/recall/F1.",
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(18, 8),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "judge_model",
            "run_date",
            name="ux_judge_calibration_runs_project_model_date",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','complete','partial','error')",
            name="ck_judge_calibration_runs_status",
        ),
        sa.CheckConstraint(
            "accuracy >= 0 AND accuracy <= 1",
            name="ck_judge_calibration_runs_accuracy",
        ),
    )
    op.create_index(
        "ix_judge_calibration_runs_project_date",
        "judge_calibration_runs",
        ["project_id", "run_date"],
    )
    op.create_index(
        "ix_judge_calibration_runs_project_model_date",
        "judge_calibration_runs",
        ["project_id", "judge_model", "run_date"],
    )

    # ── judge_mode_overrides ────────────────────────────────────────────────
    op.create_table(
        "judge_mode_overrides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("judge_model", sa.String(length=128), nullable=False),
        sa.Column(
            "mode",
            sa.String(length=16),
            nullable=False,
            comment="'blocking' | 'advisory'",
        ),
        sa.Column(
            "reason",
            sa.String(length=64),
            nullable=False,
            comment="'accuracy_below_threshold' | 'manual' | 'restored'",
        ),
        sa.Column(
            "triggered_by_run_id",
            sa.String(length=36),
            nullable=True,
            comment="judge_calibration_runs.id that flipped this row, if any.",
        ),
        sa.Column(
            "accuracy_at_change",
            sa.Float(),
            nullable=True,
            comment="Snapshot of accuracy when the override was written (0..1).",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "judge_model",
            name="ux_judge_mode_overrides_project_model",
        ),
        sa.CheckConstraint(
            "mode IN ('blocking','advisory')",
            name="ck_judge_mode_overrides_mode",
        ),
    )
    op.create_index(
        "ix_judge_mode_overrides_project",
        "judge_mode_overrides",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_judge_mode_overrides_project", table_name="judge_mode_overrides"
    )
    op.drop_table("judge_mode_overrides")

    op.drop_index(
        "ix_judge_calibration_runs_project_model_date",
        table_name="judge_calibration_runs",
    )
    op.drop_index(
        "ix_judge_calibration_runs_project_date",
        table_name="judge_calibration_runs",
    )
    op.drop_table("judge_calibration_runs")

    op.drop_index(
        "ix_golden_labels_project_created", table_name="golden_labels"
    )
    op.drop_index(
        "ix_golden_labels_trace_active", table_name="golden_labels"
    )
    op.drop_table("golden_labels")
