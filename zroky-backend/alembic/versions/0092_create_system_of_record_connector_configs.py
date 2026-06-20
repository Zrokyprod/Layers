"""create system-of-record connector configs

Revision ID: 0092_create_system_of_record_connector_configs
Revises: 0091_create_outcome_reconciliation_checks
Create Date: 2026-06-21 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0092_create_system_of_record_connector_configs"
down_revision = "0091_create_outcome_reconciliation_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_of_record_connector_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("connector_type", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column(
            "path_template",
            sa.String(length=512),
            nullable=False,
            server_default=sa.text("'/refunds/{refund_id}'"),
        ),
        sa.Column("record_path", sa.String(length=255), nullable=True),
        sa.Column("query_json", sa.Text(), nullable=True),
        sa.Column("bearer_token_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("bearer_token_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("bearer_token_last4", sa.String(length=8), nullable=True),
        sa.Column("kms_key_id", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_subject", sa.String(length=255), nullable=True),
        sa.Column("updated_by_subject", sa.String(length=255), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "connector_type IN ('ledger_refund_api')",
            name="ck_sor_connector_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "connector_type",
            name="ux_sor_connector_project_type",
        ),
    )
    op.create_index(
        "ix_sor_connector_project_type_active",
        "system_of_record_connector_configs",
        ["project_id", "connector_type", "is_active"],
    )
    op.create_index(
        "ix_sor_connector_project_updated",
        "system_of_record_connector_configs",
        ["project_id", "updated_at"],
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        "ALTER TABLE system_of_record_connector_configs ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE system_of_record_connector_configs FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        "DROP POLICY IF EXISTS sor_connector_configs_tenant_isolation "
        "ON system_of_record_connector_configs"
    )
    op.execute(
        """
        CREATE POLICY sor_connector_configs_tenant_isolation
        ON system_of_record_connector_configs
        USING (project_id = current_setting('app.current_tenant_id', true))
        WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS sor_connector_configs_tenant_isolation "
            "ON system_of_record_connector_configs"
        )
        op.execute(
            "ALTER TABLE system_of_record_connector_configs NO FORCE ROW LEVEL SECURITY"
        )
        op.execute(
            "ALTER TABLE system_of_record_connector_configs DISABLE ROW LEVEL SECURITY"
        )

    op.drop_index(
        "ix_sor_connector_project_updated",
        table_name="system_of_record_connector_configs",
    )
    op.drop_index(
        "ix_sor_connector_project_type_active",
        table_name="system_of_record_connector_configs",
    )
    op.drop_table("system_of_record_connector_configs")
