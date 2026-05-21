"""create golden_sets + golden_traces (Pilot tier golden-replay foundation)

Revision ID: 0049_create_golden_sets_and_traces
Revises: 0048_create_event_counts_ledger
Create Date: 2026-05-13 16:00:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §5.2):
  - golden_sets:    a named collection of canonical traces per project. Owns
                    the judge config used when replaying every trace in the
                    set.
  - golden_traces:  one captured call promoted to "expected behaviour". Stores
                    the expected output + token/cost/latency baselines and
                    per-trace judge criteria.
  - project_id is denormalised onto golden_traces so the Postgres RLS policy
    can filter by tenant without a JOIN through golden_sets.
  - Both tables enable + force RLS on Postgres; the policy reads
    current_setting('app.current_tenant_id', true) — same convention as the
    other tenant-scoped tables (issues, calls, …).
  - JSON blobs are stored as TEXT for SQLite/Postgres compatibility; the
    application layer is responsible for json.loads / json.dumps.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0049_create_golden_sets_and_traces"
down_revision = "0048_create_event_counts_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── golden_sets ──────────────────────────────────────────────────────────
    op.create_table(
        "golden_sets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "judge_config_json",
            sa.Text(),
            nullable=True,
            comment="JSON blob: judge model, prompts, thresholds, weights",
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
        sa.UniqueConstraint("project_id", "name", name="ux_golden_sets_project_name"),
    )
    op.create_index(
        "ix_golden_sets_project_created",
        "golden_sets",
        ["project_id", "created_at"],
    )

    # ── golden_traces ────────────────────────────────────────────────────────
    op.create_table(
        "golden_traces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("golden_set_id", sa.String(length=36), nullable=False),
        sa.Column(
            "project_id",
            sa.String(length=64),
            nullable=False,
            comment="Denormalised from parent golden_set for RLS without JOIN",
        ),
        sa.Column("call_id", sa.String(length=64), nullable=True),
        sa.Column("expected_output_text", sa.Text(), nullable=True),
        sa.Column("expected_tokens", sa.Integer(), nullable=True),
        sa.Column("expected_cost_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("expected_latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "criteria_json",
            sa.Text(),
            nullable=True,
            comment="JSON blob: per-trace judge criteria + expected_schema_json",
        ),
        sa.Column(
            "weight",
            sa.Numeric(8, 4),
            nullable=False,
            server_default=sa.text("1.0"),
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
        sa.ForeignKeyConstraint(
            ["golden_set_id"],
            ["golden_sets.id"],
            name="fk_golden_traces_golden_set_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["calls.id"],
            name="fk_golden_traces_call_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_golden_traces_set_id",
        "golden_traces",
        ["golden_set_id"],
    )
    op.create_index(
        "ix_golden_traces_project_created",
        "golden_traces",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_golden_traces_call_id",
        "golden_traces",
        ["call_id"],
    )

    # ── RLS (Postgres only) ──────────────────────────────────────────────────
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table_name in ("golden_sets", "golden_traces"):
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
        for table_name in ("golden_traces", "golden_sets"):
            op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_golden_traces_call_id", table_name="golden_traces")
    op.drop_index("ix_golden_traces_project_created", table_name="golden_traces")
    op.drop_index("ix_golden_traces_set_id", table_name="golden_traces")
    op.drop_table("golden_traces")

    op.drop_index("ix_golden_sets_project_created", table_name="golden_sets")
    op.drop_table("golden_sets")
