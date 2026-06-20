"""create outcome reconciliation checks

Revision ID: 0091_create_outcome_reconciliation_checks
Revises: 0090_contracts_releases_repository_runner
Create Date: 2026-06-20 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0091_create_outcome_reconciliation_checks"
down_revision = "0090_contracts_releases_repository_runner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outcome_reconciliation_checks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("call_id", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("runtime_policy_decision_id", sa.String(length=36), nullable=True),
        sa.Column("action_type", sa.String(length=64), nullable=True),
        sa.Column("connector_type", sa.String(length=64), nullable=False, server_default=sa.text("'api_record'")),
        sa.Column("system_ref", sa.String(length=255), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("amount_usd", sa.Numeric(14, 4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("claimed_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("actual_json", sa.Text(), nullable=True),
        sa.Column("comparison_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "verdict IN ('matched','mismatched','not_verified')",
            name="ck_outcome_reconciliation_verdict",
        ),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["runtime_policy_decision_id"], ["runtime_policy_decisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="ux_outcome_reconciliation_project_idempotency",
        ),
    )
    op.create_index(
        "ix_outcome_reconciliation_project_checked",
        "outcome_reconciliation_checks",
        ["project_id", "checked_at"],
    )
    op.create_index(
        "ix_outcome_reconciliation_project_verdict_checked",
        "outcome_reconciliation_checks",
        ["project_id", "verdict", "checked_at"],
    )
    op.create_index(
        "ix_outcome_reconciliation_call",
        "outcome_reconciliation_checks",
        ["call_id"],
    )
    op.create_index(
        "ix_outcome_reconciliation_trace",
        "outcome_reconciliation_checks",
        ["project_id", "trace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_outcome_reconciliation_trace", table_name="outcome_reconciliation_checks")
    op.drop_index("ix_outcome_reconciliation_call", table_name="outcome_reconciliation_checks")
    op.drop_index("ix_outcome_reconciliation_project_verdict_checked", table_name="outcome_reconciliation_checks")
    op.drop_index("ix_outcome_reconciliation_project_checked", table_name="outcome_reconciliation_checks")
    op.drop_table("outcome_reconciliation_checks")
