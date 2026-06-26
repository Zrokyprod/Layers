"""add postgres read connector config

Revision ID: 0104_add_postgres_read_connector_config
Revises: 0103_add_slack_approval_user_allowlist
Create Date: 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0104_add_postgres_read_connector_config"
down_revision = "0103_add_slack_approval_user_allowlist"
branch_labels = None
depends_on = None


_TABLE = "system_of_record_connector_configs"
_CHECK_NAME = "ck_sor_connector_type"
_UP_CHECK = (
    "connector_type IN ("
    "'ledger_refund_api','customer_record_api','generic_rest_api','postgres_read'"
    ")"
)
_DOWN_CHECK = (
    "connector_type IN ('ledger_refund_api','customer_record_api','generic_rest_api')"
)


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.add_column(sa.Column("read_query", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("database_url_ciphertext", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("database_url_fingerprint", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("database_url_last4", sa.String(length=8), nullable=True))
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _UP_CHECK)


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_of_record_connector_configs "
        "WHERE connector_type = 'postgres_read'"
    )
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(_CHECK_NAME, _DOWN_CHECK)
        batch_op.drop_column("database_url_last4")
        batch_op.drop_column("database_url_fingerprint")
        batch_op.drop_column("database_url_ciphertext")
        batch_op.drop_column("read_query")
