"""Add commerce system-of-record connector types.

Revision ID: 0118_add_commerce_connector_types
Revises: 0117_add_razorpay_refund_connector_type
Create Date: 2026-07-05
"""

from alembic import op


revision = "0118_add_commerce_connector_types"
down_revision = "0117_add_razorpay_refund_connector_type"
branch_labels = None
depends_on = None


_TABLE = "system_of_record_connector_configs"
_CHECK_NAME = "ck_sor_connector_type"
_OLD_CHECK = (
    "connector_type IN ('ledger_refund_api','customer_record_api','generic_rest_api',"
    "'postgres_read','hubspot_crm','zendesk_ticket','salesforce_crm','zoho_crm',"
    "'jira_issue','stripe_refund','razorpay_refund','netsuite_finance')"
)
_NEW_CHECK = (
    "connector_type IN ('ledger_refund_api','customer_record_api','generic_rest_api',"
    "'postgres_read','hubspot_crm','zendesk_ticket','salesforce_crm','zoho_crm',"
    "'jira_issue','stripe_refund','stripe_payment','razorpay_refund',"
    "'netsuite_finance','shopify_admin')"
)


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _NEW_CHECK)


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_of_record_connector_configs "
        "WHERE connector_type IN ('stripe_payment','shopify_admin')"
    )
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _OLD_CHECK)
