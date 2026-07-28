"""Add queryable outcome proof columns.

Revision ID: 0123_outcome_proof_columns
Revises: 0122_mcp_interception
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0123_outcome_proof_columns"
down_revision = "0122_mcp_interception"
branch_labels = None
depends_on = None


_CHECK_NAME = "ck_outcome_reconciliation_proof_status"
_CHECK_SQL = "proof_status IS NULL OR proof_status IN ('matched','mismatched','pending','unverifiable','partial','cancelled')"


def upgrade() -> None:
    op.add_column(
        "outcome_reconciliation_checks",
        sa.Column("proof_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "outcome_reconciliation_checks",
        sa.Column("proof_reason_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "outcome_reconciliation_checks",
        sa.Column("proof_observed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outcome_reconciliation_checks",
        sa.Column("proof_deadline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outcome_reconciliation_checks",
        sa.Column("proof_next_check_at", sa.DateTime(timezone=True), nullable=True),
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(_CHECK_NAME, "outcome_reconciliation_checks", _CHECK_SQL)
    else:
        with op.batch_alter_table("outcome_reconciliation_checks") as batch_op:
            batch_op.create_check_constraint(_CHECK_NAME, _CHECK_SQL)
    op.create_index(
        "ix_outcome_reconciliation_project_proof_checked",
        "outcome_reconciliation_checks",
        ["project_id", "proof_status", "checked_at"],
        unique=False,
    )
    op.create_index(
        "ix_outcome_reconciliation_pending_reverify",
        "outcome_reconciliation_checks",
        ["project_id", "proof_status", "proof_next_check_at"],
        unique=False,
    )
    op.execute(
        """
        UPDATE outcome_reconciliation_checks
        SET
            proof_status = CASE
                WHEN verdict = 'matched' THEN 'matched'
                WHEN verdict = 'mismatched' THEN 'mismatched'
                ELSE 'unverifiable'
            END,
            proof_reason_code = substr(COALESCE(reason, verdict), 1, 64)
        WHERE proof_status IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outcome_reconciliation_pending_reverify",
        table_name="outcome_reconciliation_checks",
    )
    op.drop_index(
        "ix_outcome_reconciliation_project_proof_checked",
        table_name="outcome_reconciliation_checks",
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint(_CHECK_NAME, "outcome_reconciliation_checks", type_="check")
    else:
        with op.batch_alter_table("outcome_reconciliation_checks") as batch_op:
            batch_op.drop_constraint(_CHECK_NAME, type_="check")
    op.drop_column("outcome_reconciliation_checks", "proof_next_check_at")
    op.drop_column("outcome_reconciliation_checks", "proof_deadline_at")
    op.drop_column("outcome_reconciliation_checks", "proof_observed_at")
    op.drop_column("outcome_reconciliation_checks", "proof_reason_code")
    op.drop_column("outcome_reconciliation_checks", "proof_status")
