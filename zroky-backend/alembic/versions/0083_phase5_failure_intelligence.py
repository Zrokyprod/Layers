"""phase 5 failure intelligence

Revision ID: 0083_phase5_failure_intelligence
Revises: 0082_create_gateway_capture_health
Create Date: 2026-06-11 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0083_phase5_failure_intelligence"
down_revision = "0082_create_gateway_capture_health"
branch_labels = None
depends_on = None


_DETECTORS = (
    "LOOP_DETECTED",
    "COST_SPIKE",
    "ACCURACY_REGRESSION",
    "HALLUCINATION_RISK",
    "SCHEMA_VIOLATION",
    "LATENCY_REGRESSION",
    "TOOL_SELECTION_FAILURE",
    "TOOL_CALL_FAILURE",
    "TOOL_ARGUMENT_MISMATCH",
    "RAG_RETRIEVAL_MISSING",
    "RAG_GROUNDING_FAILURE",
    "RETRIEVAL_MISSING",
    "UNSAFE_ACTION",
    "TASK_OUTCOME_FAILURE",
    "TOKEN_USAGE_DRIFT",
    "TOKEN_OVERFLOW",
    "RATE_LIMIT",
    "AUTH_FAILURE",
    "PROVIDER_ERROR",
    "LATENCY_ANOMALY",
    "LATENCY_DRIFT",
    "ERROR_RATE_DRIFT",
    "EMPTY_OUTPUT",
    "OUTPUT_TRUNCATED",
    "OUTPUT_LENGTH_DRIFT",
    "REPEATED_OUTPUT",
    "BEHAVIORAL_DRIFT",
    "UNKNOWN",
)

_DOWNGRADE_DETECTORS = tuple(
    item
    for item in _DETECTORS
    if item not in {"RAG_GROUNDING_FAILURE", "UNSAFE_ACTION", "TASK_OUTCOME_FAILURE"}
)


def _detector_check(detectors: tuple[str, ...]) -> str:
    return "detector IN (" + ", ".join(f"'{item}'" for item in detectors) + ")"


def _replace_detector_check(detectors: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE anomalies DROP CONSTRAINT IF EXISTS ck_anomalies_detector")
    op.create_check_constraint("ck_anomalies_detector", "anomalies", _detector_check(detectors))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _replace_detector_check(_DETECTORS)

    op.create_table(
        "issue_occurrences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("issue_id", sa.String(length=36), nullable=False),
        sa.Column("occurrence_key", sa.String(length=160), nullable=False),
        sa.Column("call_id", sa.String(length=64), nullable=True),
        sa.Column("diagnosis_id", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=False),
        sa.Column("detector", sa.String(length=32), nullable=False),
        sa.Column("grouping_signature", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issue_id"], ["anomalies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "issue_id",
            "occurrence_key",
            name="ux_issue_occurrences_project_issue_key",
        ),
    )
    op.create_index(
        "ix_issue_occurrences_project_issue_seen",
        "issue_occurrences",
        ["project_id", "issue_id", "occurred_at"],
    )
    op.create_index("ix_issue_occurrences_project_call", "issue_occurrences", ["project_id", "call_id"])
    op.create_index("ix_issue_occurrences_project_trace", "issue_occurrences", ["project_id", "trace_id"])
    op.create_index("ix_issue_occurrences_project_user", "issue_occurrences", ["project_id", "user_id"])

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE issue_occurrences ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE issue_occurrences FORCE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS issue_occurrences_project_isolation ON issue_occurrences")
        op.execute(
            """
            CREATE POLICY issue_occurrences_project_isolation
            ON issue_occurrences
            USING (project_id = current_setting('app.current_tenant_id', true))
            WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS issue_occurrences_project_isolation ON issue_occurrences")
        op.execute("ALTER TABLE issue_occurrences NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE issue_occurrences DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_issue_occurrences_project_user", table_name="issue_occurrences")
    op.drop_index("ix_issue_occurrences_project_trace", table_name="issue_occurrences")
    op.drop_index("ix_issue_occurrences_project_call", table_name="issue_occurrences")
    op.drop_index("ix_issue_occurrences_project_issue_seen", table_name="issue_occurrences")
    op.drop_table("issue_occurrences")

    if bind.dialect.name == "postgresql":
        _replace_detector_check(_DOWNGRADE_DETECTORS)
