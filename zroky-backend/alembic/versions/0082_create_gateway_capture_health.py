"""create gateway capture health

Revision ID: 0082_create_gateway_capture_health
Revises: 0081_create_trace_graph_tables
Create Date: 2026-06-11 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0082_create_gateway_capture_health"
down_revision = "0081_create_trace_graph_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gateway_capture_health",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("gateway_id", sa.String(length=128), nullable=False),
        sa.Column("emit_mode", sa.String(length=32), nullable=True),
        sa.Column("durability_mode", sa.String(length=32), nullable=True),
        sa.Column("capture_status", sa.String(length=32), server_default=sa.text("'unknown'"), nullable=False),
        sa.Column("spool_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("spool_backlog", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("spool_bytes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("spool_max_bytes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("spool_reserved_bytes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("spool_oldest_age_seconds", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("spool_high_watermark", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("emit_failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("enqueue_failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("flush_failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("flushed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("loss_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("backpressure_rejections", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("version", sa.String(length=64), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "gateway_id", name="ux_gateway_capture_health_project_gateway"),
    )
    op.create_index(
        "ix_gateway_capture_health_project_status",
        "gateway_capture_health",
        ["project_id", "capture_status"],
    )
    op.create_index(
        "ix_gateway_capture_health_project_heartbeat",
        "gateway_capture_health",
        ["project_id", "heartbeat_at"],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE gateway_capture_health ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE gateway_capture_health FORCE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS gateway_capture_health_project_isolation ON gateway_capture_health")
        op.execute(
            """
            CREATE POLICY gateway_capture_health_project_isolation
            ON gateway_capture_health
            USING (project_id = current_setting('app.current_tenant_id', true))
            WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS gateway_capture_health_project_isolation ON gateway_capture_health")
        op.execute("ALTER TABLE gateway_capture_health NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE gateway_capture_health DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_gateway_capture_health_project_heartbeat", table_name="gateway_capture_health")
    op.drop_index("ix_gateway_capture_health_project_status", table_name="gateway_capture_health")
    op.drop_table("gateway_capture_health")
