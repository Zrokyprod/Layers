"""add golden trace draft status and source evidence

Revision ID: 0076_add_golden_trace_status_source_evidence
Revises: 0075_add_evaluation_settings_json
Create Date: 2026-05-29 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0076_add_golden_trace_status_source_evidence"
down_revision = "0075_add_evaluation_settings_json"
branch_labels = None
depends_on = None


_CHECK_NAME = "ck_golden_traces_status"
_CHECK_SQL = "status IN ('draft', 'active')"


def upgrade() -> None:
    op.add_column(
        "golden_traces",
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
    )
    op.add_column(
        "golden_traces",
        sa.Column("source_output_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "golden_traces",
        sa.Column("source_evidence_json", sa.Text(), nullable=True),
    )

    op.execute(
        """
        UPDATE golden_traces
        SET status = 'active'
        WHERE COALESCE(
            NULLIF(TRIM(expected_output_text), ''),
            NULLIF(TRIM(criteria_json), '')
        ) IS NOT NULL
        """
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(_CHECK_NAME, "golden_traces", _CHECK_SQL)
    else:
        with op.batch_alter_table("golden_traces") as batch_op:
            batch_op.create_check_constraint(_CHECK_NAME, _CHECK_SQL)

    op.create_index(
        "ix_golden_traces_set_status",
        "golden_traces",
        ["golden_set_id", "status"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint(_CHECK_NAME, "golden_traces", type_="check")
    else:
        with op.batch_alter_table("golden_traces") as batch_op:
            batch_op.drop_constraint(_CHECK_NAME, type_="check")

    op.drop_index("ix_golden_traces_set_status", table_name="golden_traces")
    op.drop_column("golden_traces", "source_evidence_json")
    op.drop_column("golden_traces", "source_output_text")
    op.drop_column("golden_traces", "status")
