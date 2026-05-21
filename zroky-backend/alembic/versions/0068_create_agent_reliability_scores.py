"""create agent_reliability_scores table — Agent Reliability Scorecard.

Revision ID: 0068_create_agent_reliability_scores
Revises: 0067_create_ablation_tables
Create Date: 2026-05-20 00:00:00.000000

Schema notes (Agent Reliability Scorecard):

  agent_reliability_scores:
      One row per (project_id, agent_name, score_date).
      Computed daily by the reliability service from existing production
      data — no new telemetry collection required.

      health_score [0-100]:
          Composite weighted score shown in the dashboard leaderboard.
          Components (each normalised to 0-100, weights in parentheses):
            fail_rate_score        (35%) — 100 × (1 - fail_rate)
            cost_efficiency_score  (25%) — relative cost per completed call
                                           vs. project median
            determinism_score      (25%) — penalises deterministic failures
                                           more heavily than stochastic/env
            regression_trend_score (15%) — week-over-week fail rate delta

      determinism_breakdown_json:
          Counts by class: {deterministic, stochastic, environmental, unknown}
          Sourced from ablation_jobs for this agent in the score_date window.

      Unique constraint (project_id, agent_name, score_date) — idempotent
      recomputation: upsert replaces the row.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0068_create_agent_reliability_scores"
down_revision = "0067_create_ablation_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_reliability_scores",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("agent_name", sa.String(255), nullable=False),
        sa.Column(
            "score_date",
            sa.Date(),
            nullable=False,
            comment="UTC calendar date for which this score was computed.",
        ),
        sa.Column(
            "health_score",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0"),
            comment="Composite 0-100 reliability score.",
        ),
        sa.Column(
            "fail_rate",
            sa.Numeric(6, 5),
            nullable=False,
            server_default=sa.text("0"),
            comment="Raw fail rate in [0,1] for the 7-day window ending score_date.",
        ),
        sa.Column(
            "fail_rate_score",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cost_efficiency_score",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "determinism_score",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "regression_trend_score",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "call_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Total calls in the 7-day window.",
        ),
        sa.Column(
            "avg_cost_usd",
            sa.Numeric(18, 8),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "p95_latency_ms",
            sa.Numeric(10, 2),
            nullable=True,
            comment="95th-percentile latency for this agent in the window.",
        ),
        sa.Column(
            "prev_week_fail_rate",
            sa.Numeric(6, 5),
            nullable=True,
            comment="Fail rate 7-14 days before score_date — used for trend.",
        ),
        sa.Column(
            "determinism_breakdown_json",
            sa.Text(),
            nullable=True,
            comment='{"deterministic":N, "stochastic":N, "environmental":N, "unknown":N}',
        ),
        sa.Column(
            "top_failure_axis",
            sa.String(32),
            nullable=True,
            comment="Most frequent top-axis from ablation_jobs for this agent.",
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "agent_name", "score_date",
            name="ux_agent_reliability_project_agent_date",
        ),
        sa.CheckConstraint("health_score >= 0 AND health_score <= 100", name="ck_ars_health_score"),
    )
    op.create_index(
        "ix_ars_project_date",
        "agent_reliability_scores",
        ["project_id", "score_date"],
    )
    op.create_index(
        "ix_ars_project_agent",
        "agent_reliability_scores",
        ["project_id", "agent_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_ars_project_agent", table_name="agent_reliability_scores")
    op.drop_index("ix_ars_project_date", table_name="agent_reliability_scores")
    op.drop_table("agent_reliability_scores")
