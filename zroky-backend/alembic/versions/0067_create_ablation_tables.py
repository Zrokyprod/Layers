"""create ablation_jobs and ablation_axes tables — Ablation Root-Cause Attribution.

Revision ID: 0067_create_ablation_tables
Revises: 0066_create_outcome_events
Create Date: 2026-05-20 00:00:00.000000

Schema notes (Ablation Root-Cause Attribution):

  ablation_jobs:
      One job per root-cause analysis triggered on a failing call.
      The job runs through 5 phases (determinism probe → control group
      selection → axis statistical comparison → optional confirmation
      replay → LLM synthesis) and produces a determinism_class tag and
      a human-readable root_cause_narrative.

      Triggered by:
        POST /v1/ablation   { call_id, diagnosis_job_id? }

      Status lifecycle:
        pending → running → done | error | insufficient_data

      determinism_class tags:
        deterministic   — same prompt_fingerprint → consistent high fail rate
                          Action: fix system prompt or model choice
        stochastic      — same fingerprint, variable fail rate
                          Action: lower temperature, add retry policy, add seed
        environmental   — error_code signals infra failure
                          Action: fix tool timeout / fallback / retrieval

  ablation_axes:
      One row per variable axis tested in an ablation job.
      Each axis carries a confidence score [0-1] representing how much
      changing that axis correlates with the difference between
      failure and control-group success.

      axis_type values:
        model_version       — call.model vs control group model distribution
        prompt_template     — prompt_fingerprint divergence
        tool_behavior       — tool_calls_made / timeout_triggered patterns
        latency_env         — latency_ms z-score vs control group
        input_class         — output embedding cluster difference
        retry_pattern       — fallback_chain / retry_metadata patterns

      evidence_json holds the raw statistical evidence:
        {
          "failing_value": "anthropic/claude-3-haiku",
          "control_dominant_value": "anthropic/claude-3-sonnet",
          "control_group_size": 12,
          "matching_control_fraction": 0.33,  # fraction with same axis value
          "population_fail_rate": 0.78,
          "control_group_fail_rate": 0.08,
          "statistical_separation": 0.86      # key metric → confidence
        }
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0067_create_ablation_tables"
down_revision = "0066_create_outcome_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ablation_jobs ──────────────────────────────────────────────────────────
    op.create_table(
        "ablation_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column(
            "call_id",
            sa.String(64),
            nullable=False,
            comment="The failing call being analysed.",
        ),
        sa.Column(
            "diagnosis_job_id",
            sa.String(36),
            nullable=True,
            comment="Optional FK to diagnosis_jobs row that triggered this job.",
        ),
        sa.Column(
            "status",
            sa.String(24),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="pending | running | done | error | insufficient_data",
        ),
        sa.Column(
            "determinism_class",
            sa.String(24),
            nullable=True,
            comment="deterministic | stochastic | environmental | unknown",
        ),
        sa.Column(
            "determinism_probe_json",
            sa.Text(),
            nullable=True,
            comment="Raw statistics from the determinism probe phase.",
        ),
        sa.Column(
            "control_group_size",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "root_cause_narrative",
            sa.Text(),
            nullable=True,
            comment="LLM-generated root cause explanation.",
        ),
        sa.Column(
            "fix_suggestion",
            sa.Text(),
            nullable=True,
            comment="LLM-generated specific fix action.",
        ),
        sa.Column(
            "fix_difficulty",
            sa.String(8),
            nullable=True,
            comment="easy | medium | hard",
        ),
        sa.Column(
            "synthesis_confidence",
            sa.Numeric(4, 3),
            nullable=True,
            comment="LLM synthesis overall confidence 0-1.",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending','running','done','error','insufficient_data')",
            name="ck_ablation_jobs_status",
        ),
        sa.CheckConstraint(
            "determinism_class IS NULL OR determinism_class IN "
            "('deterministic','stochastic','environmental','unknown')",
            name="ck_ablation_jobs_det_class",
        ),
    )
    op.create_index(
        "ix_ablation_jobs_project_call",
        "ablation_jobs",
        ["project_id", "call_id"],
    )
    op.create_index(
        "ix_ablation_jobs_project_created",
        "ablation_jobs",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_ablation_jobs_diagnosis",
        "ablation_jobs",
        ["diagnosis_job_id"],
        postgresql_where=sa.text("diagnosis_job_id IS NOT NULL"),
    )

    # ── ablation_axes ──────────────────────────────────────────────────────────
    op.create_table(
        "ablation_axes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("ablation_job_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column(
            "axis_type",
            sa.String(32),
            nullable=False,
            comment=(
                "model_version | prompt_template | tool_behavior | "
                "latency_env | input_class | retry_pattern"
            ),
        ),
        sa.Column(
            "axis_label",
            sa.String(255),
            nullable=False,
            comment="Human-readable label shown in the dashboard.",
        ),
        sa.Column(
            "failing_value",
            sa.Text(),
            nullable=True,
            comment="The axis value observed in the failing trace.",
        ),
        sa.Column(
            "confidence",
            sa.Numeric(5, 4),
            nullable=False,
            server_default=sa.text("0"),
            comment="Causal confidence 0-1: how much changing this axis explains the failure.",
        ),
        sa.Column(
            "evidence_json",
            sa.Text(),
            nullable=True,
            comment="Raw statistical evidence: distribution comparison, separation score, etc.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_ablation_axes_confidence"),
    )
    op.create_index(
        "ix_ablation_axes_job_id",
        "ablation_axes",
        ["ablation_job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ablation_axes_job_id", table_name="ablation_axes")
    op.drop_table("ablation_axes")
    op.drop_index("ix_ablation_jobs_diagnosis", table_name="ablation_jobs")
    op.drop_index("ix_ablation_jobs_project_created", table_name="ablation_jobs")
    op.drop_index("ix_ablation_jobs_project_call", table_name="ablation_jobs")
    op.drop_table("ablation_jobs")
