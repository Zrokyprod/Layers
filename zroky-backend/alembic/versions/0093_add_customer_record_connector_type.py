"""add customer record connector type

Revision ID: 0093_add_customer_record_connector_type
Revises: 0092_create_system_of_record_connector_configs
Create Date: 2026-06-21 00:00:00.000000
"""
from __future__ import annotations

from alembic import op


revision = "0093_add_customer_record_connector_type"
down_revision = "0092_create_system_of_record_connector_configs"
branch_labels = None
depends_on = None


_TABLE = "system_of_record_connector_configs"
_CHECK_NAME = "ck_sor_connector_type"
_UP_CHECK = "connector_type IN ('ledger_refund_api','customer_record_api')"
_DOWN_CHECK = "connector_type IN ('ledger_refund_api')"


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _UP_CHECK)


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_of_record_connector_configs "
        "WHERE connector_type = 'customer_record_api'"
    )
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _DOWN_CHECK)
