"""add zendesk ticket connector type

Revision ID: 0110_add_zendesk_ticket_connector_type
Revises: 0109_add_hubspot_crm_connector_type
Create Date: 2026-06-30 00:00:00.000000
"""
from __future__ import annotations

from alembic import op


revision = "0110_add_zendesk_ticket_connector_type"
down_revision = "0109_add_hubspot_crm_connector_type"
branch_labels = None
depends_on = None


_TABLE = "system_of_record_connector_configs"
_CHECK_NAME = "ck_sor_connector_type"
_UP_CHECK = (
    "connector_type IN ("
    "'ledger_refund_api','customer_record_api','generic_rest_api',"
    "'postgres_read','hubspot_crm','zendesk_ticket'"
    ")"
)
_DOWN_CHECK = (
    "connector_type IN ("
    "'ledger_refund_api','customer_record_api','generic_rest_api',"
    "'postgres_read','hubspot_crm'"
    ")"
)


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _UP_CHECK)


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_of_record_connector_configs "
        "WHERE connector_type = 'zendesk_ticket'"
    )
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _DOWN_CHECK)
