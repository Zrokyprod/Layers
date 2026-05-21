"""create pilot_actions + pilot_policies (Pilot tier autopilot engine)

Revision ID: 0052_create_pilot_actions_and_policies
Revises: 0051_create_anomalies
Create Date: 2026-05-13 17:30:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §5.2 / §6.3):
  - pilot_actions:  one row per autopilot decision against an anomaly.
                    tier ∈ {1,2,3} where:
                      tier 1 = auto-revert (e.g. model_rollback, fallback_swap, retry_tune)
                      tier 2 = auto-PR (open_pr)
                      tier 3 = alert (alert)
                    `audit_user` is null when the action came from autopilot,
                    set to the user_id of a manual override otherwise.
  - pilot_policies: one row per project. `policy_json` carries the per-tier
                    configuration: enable flags, allowed action types,
                    min_confidence thresholds, blast-radius caps, daily caps,
                    kill-switch — schema defined in plan §6.3.
                    Single-row-per-project enforced via unique(project_id).
  - Both tables: Postgres RLS by project_id.
  - Foreign keys:
        pilot_actions.anomaly_id → anomalies.id  ON DELETE CASCADE
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0052_create_pilot_actions_and_policies"
down_revision = "0051_create_anomalies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── pilot_actions ────────────────────────────────────────────────────────
    op.create_table(
        "pilot_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("anomaly_id", sa.String(length=36), nullable=False),
        sa.Column(
            "tier",
            sa.Integer(),
            nullable=False,
            comment="1 = auto-revert, 2 = auto-PR, 3 = alert",
        ),
        sa.Column(
            "action_type",
            sa.String(length=64),
            nullable=False,
            comment="e.g. 'model_rollback', 'fallback_swap', 'retry_tune', 'open_pr', 'alert'",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="'pending' | 'applied' | 'reverted' | 'failed' | 'skipped'",
        ),
        sa.Column(
            "payload_json",
            sa.Text(),
            nullable=True,
            comment="JSON: action-specific config snapshot",
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "audit_user",
            sa.String(length=64),
            nullable=True,
            comment="user_id of manual override; NULL when action came from autopilot",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["anomaly_id"],
            ["anomalies.id"],
            name="fk_pilot_actions_anomaly_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("tier IN (1, 2, 3)", name="ck_pilot_actions_tier"),
        sa.CheckConstraint(
            "status IN ('pending', 'applied', 'reverted', 'failed', 'skipped')",
            name="ck_pilot_actions_status",
        ),
    )
    op.create_index(
        "ix_pilot_actions_project_created",
        "pilot_actions",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_pilot_actions_project_status",
        "pilot_actions",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_pilot_actions_project_tier_status",
        "pilot_actions",
        ["project_id", "tier", "status"],
    )
    op.create_index(
        "ix_pilot_actions_anomaly_id",
        "pilot_actions",
        ["anomaly_id"],
    )

    # ── pilot_policies ───────────────────────────────────────────────────────
    op.create_table(
        "pilot_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column(
            "policy_json",
            sa.Text(),
            nullable=False,
            comment="JSON: per-tier enable flags, allowed actions, min_confidence, caps, kill-switch (plan §6.3)",
        ),
        sa.Column(
            "updated_by",
            sa.String(length=64),
            nullable=True,
            comment="user_id of last editor",
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
        sa.UniqueConstraint("project_id", name="ux_pilot_policies_project"),
    )

    # ── RLS (Postgres only) ──────────────────────────────────────────────────
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table_name in ("pilot_actions", "pilot_policies"):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")
        op.execute(
            f"""
            CREATE POLICY {table_name}_tenant_isolation
            ON {table_name}
            USING (project_id = current_setting('app.current_tenant_id', true))
            WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table_name in ("pilot_policies", "pilot_actions"):
            op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

    op.drop_table("pilot_policies")

    op.drop_index("ix_pilot_actions_anomaly_id", table_name="pilot_actions")
    op.drop_index("ix_pilot_actions_project_tier_status", table_name="pilot_actions")
    op.drop_index("ix_pilot_actions_project_status", table_name="pilot_actions")
    op.drop_index("ix_pilot_actions_project_created", table_name="pilot_actions")
    op.drop_table("pilot_actions")
