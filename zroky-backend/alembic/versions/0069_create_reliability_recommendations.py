"""create reliability_recommendations table — Reliability Intelligence Queue.

Revision ID: 0069_create_reliability_recommendations
Revises: 0068_create_agent_reliability_scores
Create Date: 2026-05-20 00:00:00.000000

Schema notes:

  reliability_recommendations:
      One row per prioritised action item, auto-generated daily from the
      intersection of ablation_jobs, outcome_events, and agent_reliability_scores.

      recommendation_type:
          axis_causal      — a specific ablation axis is causing failures
          determinism_high — agent has high deterministic fail rate with no open fix
          cost_spike       — cost_per_call spiked vs. rolling baseline
          score_drop       — health_score declined > 10 pts week-over-week

      priority (critical / high / medium / low):
          Derived from impact_score quantile across project recommendations.

      impact_score:
          determinism_confidence × avg_failure_cost_usd × call_count × (100 − health_score)
          Dimensionless; used for relative ranking only.

      status lifecycle:
          open → acknowledged → (resolved | dismissed | snoozed)

      Idempotent generation: same (project_id, agent_name, recommendation_type,
      top_axis, generated_date) is upserted — safe to regenerate daily.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0069_create_reliability_recommendations"
down_revision = "0068_create_agent_reliability_scores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reliability_recommendations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("agent_name", sa.String(255), nullable=False),
        sa.Column(
            "recommendation_type",
            sa.String(32),
            nullable=False,
            comment="axis_causal | determinism_high | cost_spike | score_drop",
        ),
        sa.Column(
            "priority",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'medium'"),
            comment="critical | high | medium | low",
        ),
        sa.Column(
            "title",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "detail",
            sa.Text(),
            nullable=True,
            comment="Long-form description from ablation synthesis or rule logic.",
        ),
        sa.Column(
            "fix_suggestion",
            sa.Text(),
            nullable=True,
            comment="Actionable fix text, sourced from AblationJob.fix_suggestion when available.",
        ),
        sa.Column(
            "fix_difficulty",
            sa.String(16),
            nullable=True,
            comment="easy | medium | hard — from ablation synthesis",
        ),
        sa.Column(
            "top_axis",
            sa.String(32),
            nullable=True,
            comment="Ablation axis driving this recommendation, if type=axis_causal.",
        ),
        sa.Column(
            "axis_confidence",
            sa.Numeric(5, 4),
            nullable=True,
        ),
        sa.Column(
            "estimated_monthly_impact_usd",
            sa.Numeric(18, 4),
            nullable=True,
            comment="Projected monthly dollar saving if this recommendation is actioned.",
        ),
        sa.Column(
            "impact_score",
            sa.Numeric(24, 6),
            nullable=False,
            server_default=sa.text("0"),
            comment="Dimensionless ranking score; higher = more urgent.",
        ),
        sa.Column(
            "health_score_at_generation",
            sa.Numeric(5, 2),
            nullable=True,
        ),
        sa.Column(
            "fail_rate_at_generation",
            sa.Numeric(6, 5),
            nullable=True,
        ),
        sa.Column(
            "call_count_window",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "ablation_job_id",
            sa.String(36),
            nullable=True,
            comment="Source AblationJob, if type=axis_causal.",
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'open'"),
            comment="open | acknowledged | resolved | dismissed | snoozed",
        ),
        sa.Column(
            "actioned_by",
            sa.String(255),
            nullable=True,
        ),
        sa.Column(
            "actioned_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "snoozed_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "generated_date",
            sa.Date(),
            nullable=False,
            comment="UTC calendar date on which this rec was generated.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "agent_name", "recommendation_type", "top_axis", "generated_date",
            name="ux_rec_project_agent_type_axis_date",
        ),
        sa.CheckConstraint(
            "priority IN ('critical','high','medium','low')",
            name="ck_rec_priority",
        ),
        sa.CheckConstraint(
            "status IN ('open','acknowledged','resolved','dismissed','snoozed')",
            name="ck_rec_status",
        ),
    )
    op.create_index("ix_rec_project_status", "reliability_recommendations", ["project_id", "status"])
    op.create_index("ix_rec_project_agent", "reliability_recommendations", ["project_id", "agent_name"])
    op.create_index("ix_rec_impact_score", "reliability_recommendations", ["project_id", "impact_score"])


def downgrade() -> None:
    op.drop_index("ix_rec_impact_score", table_name="reliability_recommendations")
    op.drop_index("ix_rec_project_agent", table_name="reliability_recommendations")
    op.drop_index("ix_rec_project_status", table_name="reliability_recommendations")
    op.drop_table("reliability_recommendations")
