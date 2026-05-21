"""create digests table (Pilot tier weekly summary)

Revision ID: 0053_create_digests
Revises: 0052_create_pilot_actions_and_policies
Create Date: 2026-05-13 18:00:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §5.2 / §4 service map):
  - One row per (project_id, week_start). Drives the weekly digest email
    rendered by `app/services/digest_engine.py` (promoted from
    `weekly_impact.py`) and read by `/v1/digest/{week}`.
  - `week_start` is a DATE (Monday convention) so SQL range queries can
    pick a window without parsing strings.
  - `summary_json` is the structured aggregate (counts, USD saved,
    incidents-caught, fix-cycle stats); `html_blob` is the pre-rendered
    HTML email body.
  - `sent_to_emails` is a JSON array of recipient addresses; `sent_at`
    NULL means "not yet sent" (queued).
  - RLS: enable + force, tenant-isolation policy on project_id.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0053_create_digests"
down_revision = "0052_create_pilot_actions_and_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "digests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column(
            "week_start",
            sa.Date(),
            nullable=False,
            comment="Monday of the digest week (UTC date)",
        ),
        sa.Column(
            "summary_json",
            sa.Text(),
            nullable=True,
            comment="JSON: aggregated metrics for the week",
        ),
        sa.Column(
            "html_blob",
            sa.Text(),
            nullable=True,
            comment="Pre-rendered HTML email body",
        ),
        sa.Column(
            "sent_to_emails",
            sa.Text(),
            nullable=True,
            comment="JSON array of recipient email addresses",
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="NULL = not yet sent (queued)",
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
            "project_id", "week_start",
            name="ux_digests_project_week",
        ),
    )

    op.create_index(
        "ix_digests_project_week_start",
        "digests",
        ["project_id", "week_start"],
    )
    op.create_index(
        "ix_digests_project_sent_at",
        "digests",
        ["project_id", "sent_at"],
    )
    op.create_index(
        "ix_digests_pending_sent_at",
        "digests",
        ["sent_at"],
    )

    # ── RLS (Postgres only) ──────────────────────────────────────────────────
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE digests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE digests FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS digests_tenant_isolation ON digests")
    op.execute(
        """
        CREATE POLICY digests_tenant_isolation
        ON digests
        USING (project_id = current_setting('app.current_tenant_id', true))
        WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS digests_tenant_isolation ON digests")
        op.execute("ALTER TABLE digests NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE digests DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_digests_pending_sent_at", table_name="digests")
    op.drop_index("ix_digests_project_sent_at", table_name="digests")
    op.drop_index("ix_digests_project_week_start", table_name="digests")
    op.drop_table("digests")
