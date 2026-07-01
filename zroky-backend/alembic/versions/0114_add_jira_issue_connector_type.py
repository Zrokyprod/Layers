"""Add Jira issue connector type.

Revision ID: 0114_add_jira_issue_connector_type
Revises: 0113_add_connector_oauth_refresh_token_fields
Create Date: 2026-06-30 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "0114_add_jira_issue_connector_type"
down_revision = "0113_add_connector_oauth_refresh_token_fields"
branch_labels = None
depends_on = None


_TABLE = "system_of_record_connector_configs"
_CHECK_NAME = "ck_sor_connector_type"
_OLD_CHECK = (
    "connector_type IN ('ledger_refund_api','customer_record_api','generic_rest_api',"
    "'postgres_read','hubspot_crm','zendesk_ticket','salesforce_crm','zoho_crm')"
)
_NEW_CHECK = (
    "connector_type IN ('ledger_refund_api','customer_record_api','generic_rest_api',"
    "'postgres_read','hubspot_crm','zendesk_ticket','salesforce_crm','zoho_crm',"
    "'jira_issue')"
)


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _NEW_CHECK)


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_of_record_connector_configs "
        "WHERE connector_type = 'jira_issue'"
    )
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _OLD_CHECK)
