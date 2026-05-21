"""create provider_drift_* tables (Wedge 2 — Provider Silent-Update Detector)

Revision ID: 0064_create_provider_drift_tables
Revises: 0063_add_feature_interest_votes
Create Date: 2026-05-18 14:30:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 — Wedge 2 / Public Drift Watch):

  Five append-only tables forming the Provider Silent-Update Detector
  (a.k.a. "Provider Drift Watch", PDW). All tables are PUBLIC service
  data — there is no `project_id` and no Row-Level Security policy.
  Mixing this with tenant tables creates correlation risk, so we keep
  it isolated by namespace (`provider_drift_*`).

  - provider_drift_prompts:  the deterministic prompt suite (versioned).
                             Inserts happen via fixture loader on deploy.
  - provider_drift_models:   monitored models. Inserts via fixture loader.
  - provider_drift_runs:     one row per (run_date, model_id). Tracks
                             status + budget consumption. UNIQUE on
                             (run_date, model_id) — exactly-once daily.
  - provider_drift_probes:   per-(run, prompt) output row. Stores
                             output_text, output_embedding (JSON array
                             text), judge_pass, latency_ms, cost_usd,
                             outcome classification.
  - provider_drift_alerts:   emitted drift signals. Unique on
                             (model_id, category, current_date) so
                             re-runs of the aggregator are idempotent.

  No FKs to tenant tables. No `project_id`. No RLS — these are read by
  anonymous public endpoints.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0064_create_provider_drift_tables"
down_revision = "0063_add_feature_interest_votes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── provider_drift_prompts ──────────────────────────────────────────────
    op.create_table(
        "provider_drift_prompts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column(
            "category",
            sa.String(length=32),
            nullable=False,
            comment="'math' | 'refusal' | 'code' | 'summarization' | "
                    "'multi_turn' | 'tool_use' | 'factuality' | "
                    "'instruction_following'",
        ),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column(
            "max_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("512"),
        ),
        sa.Column(
            "expected_signal",
            sa.Text(),
            nullable=True,
            comment="JSON: structured judge criteria (e.g. expected substring, "
                    "must-refuse=true, expected_schema). Pure-functional; the "
                    "judge layer interprets this.",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Bump when prompt_text changes; old version retained for "
                    "history but only active rows are sampled by the runner.",
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "category IN ('math','refusal','code','summarization',"
            "'multi_turn','tool_use','factuality','instruction_following')",
            name="ck_provider_drift_prompts_category",
        ),
    )
    op.create_index(
        "ix_provider_drift_prompts_category_active",
        "provider_drift_prompts",
        ["category", "active"],
    )

    # ── provider_drift_models ───────────────────────────────────────────────
    op.create_table(
        "provider_drift_models",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column(
            "family",
            sa.String(length=32),
            nullable=False,
            comment="'gpt' | 'claude' | 'gemini' | 'llama' | etc.",
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "model_id",
            name="ux_provider_drift_models_provider_model",
        ),
        sa.CheckConstraint(
            "provider IN ('openai','anthropic','google','meta','mistral','xai','other')",
            name="ck_provider_drift_models_provider",
        ),
    )
    op.create_index(
        "ix_provider_drift_models_active",
        "provider_drift_models",
        ["active"],
    )

    # ── provider_drift_runs ─────────────────────────────────────────────────
    op.create_table(
        "provider_drift_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column(
            "run_date",
            sa.Date(),
            nullable=False,
            comment="UTC calendar date the run targets.",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="'pending' | 'running' | 'complete' | 'partial' | 'error'",
        ),
        sa.Column(
            "prompts_total",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "prompts_ok",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "prompts_error",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(18, 8),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["provider_drift_models.id"],
            name="fk_provider_drift_runs_model_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "model_id",
            "run_date",
            name="ux_provider_drift_runs_model_date",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','complete','partial','error')",
            name="ck_provider_drift_runs_status",
        ),
    )
    op.create_index(
        "ix_provider_drift_runs_run_date",
        "provider_drift_runs",
        ["run_date"],
    )
    op.create_index(
        "ix_provider_drift_runs_model_date",
        "provider_drift_runs",
        ["model_id", "run_date"],
    )

    # ── provider_drift_probes ───────────────────────────────────────────────
    op.create_table(
        "provider_drift_probes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("prompt_id", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column(
            "run_date",
            sa.Date(),
            nullable=False,
            comment="Denormalised from parent run for fast date-bucket scans.",
        ),
        sa.Column(
            "category",
            sa.String(length=32),
            nullable=False,
            comment="Denormalised from prompt for fast category aggregation.",
        ),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column(
            "output_embedding",
            sa.Text(),
            nullable=True,
            comment="JSON array of floats (1536-dim or 3072-dim). NULL when "
                    "outcome != 'ok' or embedder failed.",
        ),
        sa.Column(
            "embedding_model",
            sa.String(length=64),
            nullable=True,
            comment="Tag of the embedding model used; must remain stable to "
                    "compare cosines across days.",
        ),
        sa.Column(
            "judge_pass",
            sa.Boolean(),
            nullable=True,
            comment="True/False from judge; NULL if outcome != 'ok'.",
        ),
        sa.Column(
            "judge_score",
            sa.Float(),
            nullable=True,
            comment="Raw judge score (0-1) when the judge returns one.",
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "cost_usd",
            sa.Numeric(18, 8),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "outcome",
            sa.String(length=24),
            nullable=False,
            comment="'ok' | 'rate_limited' | 'timeout' | 'content_filtered' | "
                    "'budget_exceeded' | 'error'",
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["provider_drift_runs.id"],
            name="fk_provider_drift_probes_run_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"],
            ["provider_drift_prompts.id"],
            name="fk_provider_drift_probes_prompt_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["provider_drift_models.id"],
            name="fk_provider_drift_probes_model_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "run_id",
            "prompt_id",
            name="ux_provider_drift_probes_run_prompt",
        ),
        sa.CheckConstraint(
            "outcome IN ('ok','rate_limited','timeout','content_filtered',"
            "'budget_exceeded','error')",
            name="ck_provider_drift_probes_outcome",
        ),
    )
    op.create_index(
        "ix_provider_drift_probes_model_date_category",
        "provider_drift_probes",
        ["model_id", "run_date", "category"],
    )
    op.create_index(
        "ix_provider_drift_probes_prompt_date",
        "provider_drift_probes",
        ["prompt_id", "run_date"],
    )

    # ── provider_drift_alerts ───────────────────────────────────────────────
    op.create_table(
        "provider_drift_alerts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column(
            "current_date",
            sa.Date(),
            nullable=False,
            comment="UTC date the alert was computed for.",
        ),
        sa.Column("baseline_start", sa.Date(), nullable=False),
        sa.Column("baseline_end", sa.Date(), nullable=False),
        sa.Column(
            "pass_rate_current",
            sa.Float(),
            nullable=False,
            comment="Judge pass-rate on current_date (0-1).",
        ),
        sa.Column(
            "pass_rate_baseline",
            sa.Float(),
            nullable=False,
            comment="Mean judge pass-rate over baseline window (0-1).",
        ),
        sa.Column(
            "judge_z",
            sa.Float(),
            nullable=False,
            comment="Z-score of pass-rate vs baseline.",
        ),
        sa.Column(
            "embedding_z",
            sa.Float(),
            nullable=False,
            comment="Z-score of mean cosine-vs-centroid vs baseline.",
        ),
        sa.Column(
            "delta_pp",
            sa.Float(),
            nullable=False,
            comment="Signed delta in percentage points (current - baseline) * 100.",
        ),
        sa.Column(
            "severity",
            sa.String(length=16),
            nullable=False,
            comment="'info' | 'warn' | 'critical'",
        ),
        sa.Column(
            "headline",
            sa.String(length=255),
            nullable=False,
            comment="Pre-rendered human-readable summary.",
        ),
        sa.Column(
            "evidence_json",
            sa.Text(),
            nullable=True,
            comment="JSON: per-prompt deltas, sample outputs, etc.",
        ),
        sa.Column(
            "is_candidate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if only one metric crossed threshold (not in RSS).",
        ),
        sa.Column(
            "published_at",
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
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["provider_drift_models.id"],
            name="fk_provider_drift_alerts_model_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "model_id",
            "category",
            "current_date",
            name="ux_provider_drift_alerts_model_category_date",
        ),
        sa.CheckConstraint(
            "severity IN ('info','warn','critical')",
            name="ck_provider_drift_alerts_severity",
        ),
    )
    op.create_index(
        "ix_provider_drift_alerts_published",
        "provider_drift_alerts",
        ["published_at"],
    )
    op.create_index(
        "ix_provider_drift_alerts_model_date",
        "provider_drift_alerts",
        ["model_id", "current_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_drift_alerts_model_date", table_name="provider_drift_alerts"
    )
    op.drop_index(
        "ix_provider_drift_alerts_published", table_name="provider_drift_alerts"
    )
    op.drop_table("provider_drift_alerts")

    op.drop_index(
        "ix_provider_drift_probes_prompt_date", table_name="provider_drift_probes"
    )
    op.drop_index(
        "ix_provider_drift_probes_model_date_category",
        table_name="provider_drift_probes",
    )
    op.drop_table("provider_drift_probes")

    op.drop_index(
        "ix_provider_drift_runs_model_date", table_name="provider_drift_runs"
    )
    op.drop_index(
        "ix_provider_drift_runs_run_date", table_name="provider_drift_runs"
    )
    op.drop_table("provider_drift_runs")

    op.drop_index(
        "ix_provider_drift_models_active", table_name="provider_drift_models"
    )
    op.drop_table("provider_drift_models")

    op.drop_index(
        "ix_provider_drift_prompts_category_active",
        table_name="provider_drift_prompts",
    )
    op.drop_table("provider_drift_prompts")
