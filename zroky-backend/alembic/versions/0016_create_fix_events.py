"""create fix events table

Revision ID: 0016_create_fix_events
Revises: 0015_create_calls_and_link_diagnosis_jobs
Create Date: 2026-04-26 02:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_create_fix_events"
down_revision = "0015_create_calls_and_link_diagnosis_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fix_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("diagnosis_id", sa.String(length=64), nullable=False),
        sa.Column("fix_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), server_default=sa.text("'dashboard'"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("timestamp_bucket", sa.String(length=16), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("metadata", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.CheckConstraint(
            "event_type in ('shown','copied','pr_generated','pr_merged','applied','resolved','ignored','regressed')",
            name="ck_fix_events_event_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "idempotency_key", name="ux_fix_events_project_idempotency"),
        sa.UniqueConstraint(
            "project_id",
            "fix_id",
            "event_type",
            "timestamp_bucket",
            name="ux_fix_events_project_fix_type_bucket",
        ),
    )
    op.create_index("ix_fix_events_project_timestamp", "fix_events", ["project_id", "timestamp"], unique=False)
    op.create_index(
        "ix_fix_events_project_diagnosis",
        "fix_events",
        ["project_id", "diagnosis_id"],
        unique=False,
    )
    op.create_index("ix_fix_events_project_fix", "fix_events", ["project_id", "fix_id"], unique=False)
    op.create_index(
        "ix_fix_events_project_type_timestamp",
        "fix_events",
        ["project_id", "event_type", "timestamp"],
        unique=False,
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE fix_events ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE fix_events FORCE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS fix_events_project_isolation ON fix_events")
        op.execute(
            """
            CREATE POLICY fix_events_project_isolation
            ON fix_events
            USING (project_id = current_setting('app.current_tenant_id', true))
            WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS fix_events_project_isolation ON fix_events")
        op.execute("ALTER TABLE fix_events NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE fix_events DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_fix_events_project_type_timestamp", table_name="fix_events")
    op.drop_index("ix_fix_events_project_fix", table_name="fix_events")
    op.drop_index("ix_fix_events_project_diagnosis", table_name="fix_events")
    op.drop_index("ix_fix_events_project_timestamp", table_name="fix_events")
    op.drop_table("fix_events")
