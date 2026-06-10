"""create trace graph tables

Revision ID: 0081_create_trace_graph_tables
Revises: 0080_add_replay_job_claim_leases
Create Date: 2026-06-11 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0081_create_trace_graph_tables"
down_revision = "0080_add_replay_job_claim_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trace_spans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("span_id", sa.String(length=128), nullable=False),
        sa.Column("parent_span_id", sa.String(length=128), nullable=True),
        sa.Column("call_id", sa.String(length=64), nullable=True),
        sa.Column("event_id", sa.String(length=128), nullable=True),
        sa.Column("span_type", sa.String(length=64), server_default=sa.text("'other'"), nullable=False),
        sa.Column("span_name", sa.String(length=255), nullable=True),
        sa.Column("span_index", sa.Integer(), nullable=True),
        sa.Column("agent_name", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'completed'"), nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("cost_total", sa.Numeric(18, 8), server_default=sa.text("0"), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=True),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("tool_json", sa.Text(), nullable=True),
        sa.Column("retrieval_json", sa.Text(), nullable=True),
        sa.Column("memory_json", sa.Text(), nullable=True),
        sa.Column("handoff_json", sa.Text(), nullable=True),
        sa.Column("policy_json", sa.Text(), nullable=True),
        sa.Column("outcome_json", sa.Text(), nullable=True),
        sa.Column("versions_json", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("capture_source", sa.String(length=64), nullable=True),
        sa.Column("masking_version", sa.String(length=64), nullable=True),
        sa.Column("pii_masked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "span_id", name="ux_trace_spans_project_span"),
        sa.UniqueConstraint("project_id", "event_id", name="ux_trace_spans_project_event"),
    )
    op.create_index("ix_trace_spans_project_trace", "trace_spans", ["project_id", "trace_id"])
    op.create_index(
        "ix_trace_spans_project_trace_index",
        "trace_spans",
        ["project_id", "trace_id", "span_index"],
    )
    op.create_index(
        "ix_trace_spans_project_type_created",
        "trace_spans",
        ["project_id", "span_type", "created_at"],
    )
    op.create_index("ix_trace_spans_project_call", "trace_spans", ["project_id", "call_id"])
    op.create_index("ix_trace_spans_project_parent", "trace_spans", ["project_id", "parent_span_id"])

    op.create_table(
        "trace_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("root_span_id", sa.String(length=128), nullable=True),
        sa.Column("root_call_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'completed'"), nullable=False),
        sa.Column("span_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("agent_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("agents_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("providers_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_latency_ms", sa.Float(), nullable=True),
        sa.Column("total_cost_usd", sa.Numeric(18, 8), server_default=sa.text("0"), nullable=False),
        sa.Column("error_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("has_failure", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("has_outcome", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("completeness_warnings_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("capture_completeness_score", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("projection_error", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "trace_id", name="ux_trace_runs_project_trace"),
    )
    op.create_index("ix_trace_runs_project_started", "trace_runs", ["project_id", "started_at"])
    op.create_index(
        "ix_trace_runs_project_status_started",
        "trace_runs",
        ["project_id", "status", "started_at"],
    )
    op.create_index(
        "ix_trace_runs_project_failure_started",
        "trace_runs",
        ["project_id", "has_failure", "started_at"],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table_name in ("trace_spans", "trace_runs"):
            op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
            op.execute(f"DROP POLICY IF EXISTS {table_name}_project_isolation ON {table_name}")
            op.execute(
                f"""
                CREATE POLICY {table_name}_project_isolation
                ON {table_name}
                USING (project_id = current_setting('app.current_tenant_id', true))
                WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
                """
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table_name in ("trace_runs", "trace_spans"):
            op.execute(f"DROP POLICY IF EXISTS {table_name}_project_isolation ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_trace_runs_project_failure_started", table_name="trace_runs")
    op.drop_index("ix_trace_runs_project_status_started", table_name="trace_runs")
    op.drop_index("ix_trace_runs_project_started", table_name="trace_runs")
    op.drop_table("trace_runs")
    op.drop_index("ix_trace_spans_project_parent", table_name="trace_spans")
    op.drop_index("ix_trace_spans_project_call", table_name="trace_spans")
    op.drop_index("ix_trace_spans_project_type_created", table_name="trace_spans")
    op.drop_index("ix_trace_spans_project_trace_index", table_name="trace_spans")
    op.drop_index("ix_trace_spans_project_trace", table_name="trace_spans")
    op.drop_table("trace_spans")
