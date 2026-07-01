"""Add NetSuite finance system-of-record connector type.

Revision ID: 0116_add_netsuite_finance_connector_type
Revises: 0115_add_stripe_refund_connector_type
Create Date: 2026-06-30
"""

from alembic import op


revision = "0116_add_netsuite_finance_connector_type"
down_revision = "0115_add_stripe_refund_connector_type"
branch_labels = None
depends_on = None


_TABLE = "system_of_record_connector_configs"
_CHECK_NAME = "ck_sor_connector_type"
_OLD_CHECK = (
    "connector_type IN ('ledger_refund_api','customer_record_api','generic_rest_api',"
    "'postgres_read','hubspot_crm','zendesk_ticket','salesforce_crm','zoho_crm',"
    "'jira_issue','stripe_refund')"
)
_NEW_CHECK = (
    "connector_type IN ('ledger_refund_api','customer_record_api','generic_rest_api',"
    "'postgres_read','hubspot_crm','zendesk_ticket','salesforce_crm','zoho_crm',"
    "'jira_issue','stripe_refund','netsuite_finance')"
)


def upgrade() -> None:
    op.drop_constraint(_CHECK_NAME, _TABLE, type_="check")
    op.create_check_constraint(_CHECK_NAME, _TABLE, _NEW_CHECK)


def downgrade() -> None:
    op.execute(
        "UPDATE system_of_record_connector_configs "
        "SET is_active = false "
        "WHERE connector_type = 'netsuite_finance'"
    )
    op.drop_constraint(_CHECK_NAME, _TABLE, type_="check")
    op.create_check_constraint(_CHECK_NAME, _TABLE, _OLD_CHECK)
