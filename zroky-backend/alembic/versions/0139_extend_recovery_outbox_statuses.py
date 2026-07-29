"""extend recovery outbox statuses

Revision ID: 0139_extend_recovery_outbox_statuses
Revises: 0138_add_final_outcome_graph_ledger_columns
Create Date: 2026-07-30
"""

from __future__ import annotations

from alembic import op


revision = "0139_extend_recovery_outbox_statuses"
down_revision = "0138_add_final_outcome_graph_ledger_columns"
branch_labels = None
depends_on = None


_CHECK_NAME = "ck_final_domain_outbox_jobs_status"
_NEW_CHECK = "status IN ('pending','claimed','running','completed','failed','succeeded','retrying','dead')"
_OLD_CHECK = "status IN ('pending','claimed','running','succeeded','retrying','dead')"


def upgrade() -> None:
    with op.batch_alter_table("final_domain_outbox_jobs") as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _NEW_CHECK)


def downgrade() -> None:
    with op.batch_alter_table("final_domain_outbox_jobs") as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _OLD_CHECK)
