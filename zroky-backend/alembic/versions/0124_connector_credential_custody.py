"""Add versioned connector credential custody and bindings.

Revision ID: 0124_connector_credential_custody
Revises: 0123_outcome_proof_columns
Create Date: 2026-07-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0124_connector_credential_custody"
down_revision = "0123_outcome_proof_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("credential_kind", sa.String(length=32), nullable=False),
        sa.Column("custody_mode", sa.String(length=32), nullable=False),
        sa.Column("secret_ref", sa.String(length=512), nullable=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("key_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("key_last4", sa.String(length=8), nullable=True),
        sa.Column("kms_key_id", sa.String(length=128), nullable=True),
        sa.Column("scopes_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column(
            "allowed_connector_types_json",
            sa.Text(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotation_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_id", sa.String(length=36), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "credential_kind IN ('bearer_token','oauth_refresh_token','database_url')",
            name="ck_connector_credentials_kind",
        ),
        sa.CheckConstraint(
            "custody_mode IN ('zroky_managed','customer_managed','private_runner')",
            name="ck_connector_credentials_custody",
        ),
        sa.CheckConstraint(
            "(custody_mode = 'zroky_managed' AND ciphertext IS NOT NULL AND secret_ref IS NULL) "
            "OR (custody_mode IN ('customer_managed','private_runner') "
            "AND ciphertext IS NULL AND secret_ref IS NOT NULL)",
            name="ck_connector_credentials_custody_payload",
        ),
        sa.ForeignKeyConstraint(["supersedes_id"], ["connector_credentials.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", "version", name="ux_connector_credentials_project_name_version"),
    )
    op.create_index(
        "ix_connector_credentials_project_name_active",
        "connector_credentials",
        ["project_id", "name", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_connector_credentials_project_rotation_due",
        "connector_credentials",
        ["project_id", "rotation_due_at"],
        unique=False,
    )

    op.create_table(
        "connector_credential_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("credential_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_subject", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('created','rotated','bound','revoked','used')",
            name="ck_connector_credential_audit_event_type",
        ),
        sa.ForeignKeyConstraint(["credential_id"], ["connector_credentials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_connector_credential_audit_project_created",
        "connector_credential_audit_events",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_connector_credential_audit_credential_created",
        "connector_credential_audit_events",
        ["credential_id", "created_at"],
        unique=False,
    )

    with op.batch_alter_table("system_of_record_connector_configs") as batch_op:
        batch_op.add_column(sa.Column("bearer_credential_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("oauth_refresh_credential_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("database_url_credential_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_sor_connector_bearer_credential",
            "connector_credentials",
            ["bearer_credential_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_sor_connector_oauth_credential",
            "connector_credentials",
            ["oauth_refresh_credential_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_sor_connector_database_credential",
            "connector_credentials",
            ["database_url_credential_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_sor_connector_bearer_credential", ["bearer_credential_id"])
        batch_op.create_index("ix_sor_connector_oauth_credential", ["oauth_refresh_credential_id"])
        batch_op.create_index("ix_sor_connector_database_credential", ["database_url_credential_id"])


def downgrade() -> None:
    with op.batch_alter_table("system_of_record_connector_configs") as batch_op:
        batch_op.drop_index("ix_sor_connector_database_credential")
        batch_op.drop_index("ix_sor_connector_oauth_credential")
        batch_op.drop_index("ix_sor_connector_bearer_credential")
        batch_op.drop_constraint("fk_sor_connector_database_credential", type_="foreignkey")
        batch_op.drop_constraint("fk_sor_connector_oauth_credential", type_="foreignkey")
        batch_op.drop_constraint("fk_sor_connector_bearer_credential", type_="foreignkey")
        batch_op.drop_column("database_url_credential_id")
        batch_op.drop_column("oauth_refresh_credential_id")
        batch_op.drop_column("bearer_credential_id")
    op.drop_index(
        "ix_connector_credential_audit_credential_created",
        table_name="connector_credential_audit_events",
    )
    op.drop_index(
        "ix_connector_credential_audit_project_created",
        table_name="connector_credential_audit_events",
    )
    op.drop_table("connector_credential_audit_events")
    op.drop_index(
        "ix_connector_credentials_project_rotation_due",
        table_name="connector_credentials",
    )
    op.drop_index(
        "ix_connector_credentials_project_name_active",
        table_name="connector_credentials",
    )
    op.drop_table("connector_credentials")
