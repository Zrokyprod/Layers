"""add final outcome graph ledger columns

Revision ID: 0138_add_final_outcome_graph_ledger_columns
Revises: 0137_drop_mcp_interception_tables
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0138_add_final_outcome_graph_ledger_columns"
down_revision = "0137_drop_mcp_interception_tables"
branch_labels = None
depends_on = None


_CLASSIFICATION_CHECK = (
    "classification IN ("
    "'verified','wrong','missing','stale','duplicate','conflicted','forbidden','unknown','pending'"
    ")"
)
_CHECK_NAME = "ck_final_outcome_graphs_classification"


def upgrade() -> None:
    with op.batch_alter_table("final_outcome_graphs") as batch_op:
        batch_op.add_column(sa.Column("classification", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("reason_code", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("last_checked_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("next_check_at", sa.DateTime(), nullable=True))
        batch_op.create_check_constraint(_CHECK_NAME, _CLASSIFICATION_CHECK)
    op.create_index(
        "ix_final_outcome_graphs_scope_class_created",
        "final_outcome_graphs",
        ["project_id", "environment", "classification", "created_at"],
    )
    op.create_index(
        "ix_final_outcome_graphs_project_class_next",
        "final_outcome_graphs",
        ["project_id", "classification", "next_check_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_final_outcome_graphs_project_class_next", table_name="final_outcome_graphs")
    op.drop_index("ix_final_outcome_graphs_scope_class_created", table_name="final_outcome_graphs")
    with op.batch_alter_table("final_outcome_graphs") as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.drop_column("next_check_at")
        batch_op.drop_column("last_checked_at")
        batch_op.drop_column("reason_code")
        batch_op.drop_column("classification")
