"""create anomalies table (Phase A of issues → anomalies rename)

Revision ID: 0051_create_anomalies
Revises: 0050_create_replay_runs_and_traces
Create Date: 2026-05-13 17:00:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §5.2 / §5.3 / §6):
  - Phase A of a two-phase rename: we create `anomalies` alongside the
    legacy `issues` table. App code will dual-write until Phase B (a
    later migration) backfills, switches reads, and drops `issues`.
  - One row per unique (project_id, fingerprint) group where fingerprint
    is a hash of (detector, model, prompt_fingerprint, agent, …) produced
    by the detector pipeline.
  - `detector` enumerates the retained + Pilot-tier detectors:
        Watch tier:  'LOOP_DETECTED', 'COST_SPIKE'
        Pilot tier:  'ACCURACY_REGRESSION', 'HALLUCINATION_RISK',
                     'SCHEMA_VIOLATION', 'LATENCY_REGRESSION'
    Demoted-to-guidance detectors (TOKEN_OVERFLOW, RATE_LIMIT, AUTH_FAILURE,
    PROVIDER_ERROR) do NOT create anomaly rows — they are SDK-side preflight
    warnings only (plan §6.1).
  - `evidence_json` carries the Diagnose engine output:
        { "candidates": [{signal, confidence, delta, evidence}, ...], ... }
    ranked by confidence (plan §6.2).
  - `sample_call_ids_json` is a JSON array of representative call IDs used
    by the dashboard to jump into concrete examples.
  - RLS: enable + force, tenant-isolation policy on project_id.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0051_create_anomalies"
down_revision = "0050_create_replay_runs_and_traces"
branch_labels = None
depends_on = None


_DETECTOR_SET = (
    "'LOOP_DETECTED', 'COST_SPIKE', "
    "'ACCURACY_REGRESSION', 'HALLUCINATION_RISK', "
    "'SCHEMA_VIOLATION', 'LATENCY_REGRESSION'"
)


def upgrade() -> None:
    op.create_table(
        "anomalies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column(
            "detector",
            sa.String(length=32),
            nullable=False,
            comment="Detector code; see anomaly detector enumeration.",
        ),
        sa.Column(
            "severity",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'low'"),
            comment="'low' | 'medium' | 'high' | 'critical'",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'open'"),
            comment="'open' | 'acknowledged' | 'resolved' | 'muted'",
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "occurrence_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "sample_call_ids_json",
            sa.Text(),
            nullable=True,
            comment="JSON array of representative call IDs (top-N)",
        ),
        sa.Column(
            "evidence_json",
            sa.Text(),
            nullable=True,
            comment="JSON: diagnose-engine output {candidates:[...]} ranked by confidence",
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
            "project_id", "fingerprint",
            name="ux_anomalies_project_fingerprint",
        ),
        sa.CheckConstraint(
            f"detector IN ({_DETECTOR_SET})",
            name="ck_anomalies_detector",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_anomalies_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved', 'muted')",
            name="ck_anomalies_status",
        ),
    )

    # ── lookup indexes ────────────────────────────────────────────────────────
    op.create_index(
        "ix_anomalies_project_status",
        "anomalies",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_anomalies_project_status_last_seen",
        "anomalies",
        ["project_id", "status", "last_seen_at"],
    )
    op.create_index(
        "ix_anomalies_project_severity",
        "anomalies",
        ["project_id", "severity"],
    )
    op.create_index(
        "ix_anomalies_project_detector",
        "anomalies",
        ["project_id", "detector"],
    )
    op.create_index(
        "ix_anomalies_project_last_seen",
        "anomalies",
        ["project_id", "last_seen_at"],
    )
    op.create_index(
        "ix_anomalies_fingerprint",
        "anomalies",
        ["fingerprint"],
    )

    # ── RLS (Postgres only) ──────────────────────────────────────────────────
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE anomalies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE anomalies FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS anomalies_tenant_isolation ON anomalies")
    op.execute(
        """
        CREATE POLICY anomalies_tenant_isolation
        ON anomalies
        USING (project_id = current_setting('app.current_tenant_id', true))
        WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS anomalies_tenant_isolation ON anomalies")
        op.execute("ALTER TABLE anomalies NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE anomalies DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_anomalies_fingerprint", table_name="anomalies")
    op.drop_index("ix_anomalies_project_last_seen", table_name="anomalies")
    op.drop_index("ix_anomalies_project_detector", table_name="anomalies")
    op.drop_index("ix_anomalies_project_severity", table_name="anomalies")
    op.drop_index("ix_anomalies_project_status_last_seen", table_name="anomalies")
    op.drop_index("ix_anomalies_project_status", table_name="anomalies")
    op.drop_table("anomalies")
