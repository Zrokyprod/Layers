"""add generic rest connector type

Revision ID: 0096_add_generic_rest_connector_type
Revises: 0095_extend_agents_for_tool_control_profiles
Create Date: 2026-06-25 00:00:00.000000
"""
from __future__ import annotations

from alembic import op


revision = "0096_add_generic_rest_connector_type"
down_revision = "0095_extend_agents_for_tool_control_profiles"
branch_labels = None
depends_on = None


_TABLE = "system_of_record_connector_configs"
_CHECK_NAME = "ck_sor_connector_type"
_UP_CHECK = "connector_type IN ('ledger_refund_api','customer_record_api','generic_rest_api')"
_DOWN_CHECK = "connector_type IN ('ledger_refund_api','customer_record_api')"


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _UP_CHECK)


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_of_record_connector_configs "
        "WHERE connector_type = 'generic_rest_api'"
    )
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _DOWN_CHECK)
