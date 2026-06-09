"""create discovery_scan_state

Revision ID: 0078_create_discovery_scan_state
Revises: 0077_create_discovery_tables
Create Date: 2026-06-06 00:00:00.000000

Discovery scans are scheduled/idempotent work. This table stores the latest
processed production call per project so repeated scans do not re-score the
same rows and inflate anomaly occurrence counts.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0078_create_discovery_scan_state"
down_revision = "0077_create_discovery_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_scan_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("last_scanned_call_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scanned_call_id", sa.String(length=36), nullable=True),
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
        sa.UniqueConstraint("project_id", name="uq_discovery_scan_state_project_id"),
    )
    op.create_index(
        "ix_discovery_scan_state_project_watermark",
        "discovery_scan_state",
        ["project_id", "last_scanned_call_created_at"],
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE discovery_scan_state ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE discovery_scan_state FORCE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS discovery_scan_state_tenant_isolation ON discovery_scan_state"
    )
    op.execute(
        """
        CREATE POLICY discovery_scan_state_tenant_isolation
        ON discovery_scan_state
        USING (project_id = current_setting('app.current_tenant_id', true))
        WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS discovery_scan_state_tenant_isolation ON discovery_scan_state"
        )
        op.execute("ALTER TABLE discovery_scan_state NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE discovery_scan_state DISABLE ROW LEVEL SECURITY")

    op.drop_index(
        "ix_discovery_scan_state_project_watermark",
        table_name="discovery_scan_state",
    )
    op.drop_table("discovery_scan_state")
