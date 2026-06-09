"""create behavioral_baselines (Discover pillar)

Revision ID: 0077_create_discovery_tables
Revises: 0076_add_golden_trace_status_source_evidence
Create Date: 2026-06-02 00:00:00.000000

Schema notes (ZROKY_DISCOVERY_ENGINE_PLAN.md §3, Option A):
  - `behavioral_baselines` — learned "normal" per (project, agent, workflow)
    behavior key, versioned. `status` ∈ learning|active|suspect|superseded.
    Learning/suspect baselines never surface findings.
  - DECISION (Option A): discovery does NOT introduce a parallel `findings`
    table. Surfaced deviations are written to the EXISTING `anomalies` table
    via a new detector source (`BEHAVIORAL_DRIFT`), so there is a single
    customer-facing "problem" concept (Issue, projected from Anomaly). This
    avoids duplicating the anomalies/issues model.
  - `behavioral_baselines` is the one genuinely-new persistent artifact the
    discovery engine needs.
  - RLS: enable + force, tenant-isolation policy on project_id (same
    convention as anomalies / golden_sets / digests).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0077_create_discovery_tables"
down_revision = "0076_add_golden_trace_status_source_evidence"
branch_labels = None
depends_on = None


# Anomalies detector CHECK — old (without BEHAVIORAL_DRIFT) and new (with it).
_ANOMALY_DETECTORS_BASE = (
    "'LOOP_DETECTED', 'COST_SPIKE', "
    "'ACCURACY_REGRESSION', 'HALLUCINATION_RISK', "
    "'SCHEMA_VIOLATION', 'LATENCY_REGRESSION', "
    "'TOOL_SELECTION_FAILURE', 'TOOL_CALL_FAILURE', "
    "'TOOL_ARGUMENT_MISMATCH', 'RAG_RETRIEVAL_MISSING', "
    "'RETRIEVAL_MISSING', 'TOKEN_USAGE_DRIFT', 'TOKEN_OVERFLOW', "
    "'RATE_LIMIT', 'AUTH_FAILURE', 'PROVIDER_ERROR', "
    "'LATENCY_ANOMALY', 'LATENCY_DRIFT', 'ERROR_RATE_DRIFT', "
    "'EMPTY_OUTPUT', 'OUTPUT_TRUNCATED', 'OUTPUT_LENGTH_DRIFT', "
    "'REPEATED_OUTPUT'"
)
_ANOMALY_DETECTOR_SET_OLD = f"detector IN ({_ANOMALY_DETECTORS_BASE}, 'UNKNOWN')"
_ANOMALY_DETECTOR_SET_NEW = (
    f"detector IN ({_ANOMALY_DETECTORS_BASE}, 'BEHAVIORAL_DRIFT', 'UNKNOWN')"
)


def upgrade() -> None:
    op.create_table(
        "behavioral_baselines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("agent_name", sa.String(length=255), nullable=True),
        sa.Column("workflow_name", sa.String(length=255), nullable=True),
        sa.Column(
            "behavior_key",
            sa.String(length=512),
            nullable=False,
            comment="Stable grouping key (project|agent|workflow with fallbacks).",
        ),
        sa.Column(
            "specificity",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'exact'"),
            comment="'exact' | 'agent_only' | 'project_only'",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'learning'"),
            comment="'learning' | 'active' | 'suspect' | 'superseded'",
        ),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("distinct_days", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_rate", sa.Numeric(8, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("window_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "features_json",
            sa.Text(),
            nullable=True,
            comment="JSON: learned distributions (tool seqs, critical tools, shapes, numeric stats, outcomes).",
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
            "project_id", "behavior_key", "version",
            name="ux_behavioral_baselines_key_version",
        ),
        sa.CheckConstraint(
            "specificity IN ('exact', 'agent_only', 'project_only')",
            name="ck_behavioral_baselines_specificity",
        ),
        sa.CheckConstraint(
            "status IN ('learning', 'active', 'suspect', 'superseded')",
            name="ck_behavioral_baselines_status",
        ),
    )
    op.create_index(
        "ix_behavioral_baselines_project_key_status",
        "behavioral_baselines",
        ["project_id", "behavior_key", "status"],
    )
    op.create_index(
        "ix_behavioral_baselines_project_status",
        "behavioral_baselines",
        ["project_id", "status"],
    )

    # ── RLS (Postgres only) ──────────────────────────────────────────────────
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE behavioral_baselines ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE behavioral_baselines FORCE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS behavioral_baselines_tenant_isolation ON behavioral_baselines"
    )
    op.execute(
        """
        CREATE POLICY behavioral_baselines_tenant_isolation
        ON behavioral_baselines
        USING (project_id = current_setting('app.current_tenant_id', true))
        WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
        """
    )

    # Extend the anomalies detector CHECK to allow the new BEHAVIORAL_DRIFT
    # source (Option A: discovery output lands in the existing anomalies table).
    op.drop_constraint("ck_anomalies_detector", "anomalies", type_="check")
    op.create_check_constraint(
        "ck_anomalies_detector",
        "anomalies",
        _ANOMALY_DETECTOR_SET_NEW,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Restore the original anomalies detector CHECK (without BEHAVIORAL_DRIFT).
        op.drop_constraint("ck_anomalies_detector", "anomalies", type_="check")
        op.create_check_constraint(
            "ck_anomalies_detector", "anomalies", _ANOMALY_DETECTOR_SET_OLD
        )

        op.execute(
            "DROP POLICY IF EXISTS behavioral_baselines_tenant_isolation ON behavioral_baselines"
        )
        op.execute("ALTER TABLE behavioral_baselines NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE behavioral_baselines DISABLE ROW LEVEL SECURITY")

    op.drop_index(
        "ix_behavioral_baselines_project_status", table_name="behavioral_baselines"
    )
    op.drop_index(
        "ix_behavioral_baselines_project_key_status", table_name="behavioral_baselines"
    )
    op.drop_table("behavioral_baselines")
