"""create verified action kernel

Revision ID: 0097_create_verified_action_kernel
Revises: 0096_add_generic_rest_connector_type
Create Date: 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0097_create_verified_action_kernel"
down_revision = "0096_add_generic_rest_connector_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_contract_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("contract_key", sa.String(length=160), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("action_type", sa.String(length=160), nullable=False),
        sa.Column("operation_kind", sa.String(length=32), nullable=False),
        sa.Column("domain_family", sa.String(length=64), nullable=False),
        sa.Column("schema_digest", sa.String(length=80), nullable=False),
        sa.Column("schema_json", sa.Text(), nullable=False),
        sa.Column("risk_class", sa.String(length=8), server_default=sa.text("'R2'"), nullable=False),
        sa.Column("verification_profile_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("connector_family", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "operation_kind IN ('READ_SENSITIVE','EXPORT','CREATE','UPDATE','DELETE','TRANSFER','SEND','APPROVE','GRANT','EXECUTE','DEPLOY','ROTATE_OR_REVOKE')",
            name="ck_action_contract_versions_operation_kind",
        ),
        sa.CheckConstraint("risk_class IN ('R0','R1','R2','R3','R4')", name="ck_action_contract_versions_risk_class"),
        sa.CheckConstraint("status IN ('active','retired')", name="ck_action_contract_versions_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "contract_key", "version", name="ux_action_contract_versions_project_key_version"),
    )
    op.create_index("ix_action_contract_versions_project_action", "action_contract_versions", ["project_id", "action_type"])
    op.create_index("ix_action_contract_versions_project_status", "action_contract_versions", ["project_id", "status"])

    op.create_table(
        "action_intents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("contract_version_id", sa.String(length=36), nullable=False),
        sa.Column("contract_key", sa.String(length=160), nullable=False),
        sa.Column("contract_version", sa.String(length=32), nullable=False),
        sa.Column("action_type", sa.String(length=160), nullable=False),
        sa.Column("operation_kind", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=64), server_default=sa.text("'production'"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("intent_digest", sa.String(length=80), nullable=False),
        sa.Column("canonical_intent_json", sa.Text(), nullable=False),
        sa.Column("principal_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("actor_chain_json", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("purpose_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("resource_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("parameters_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("verification_profile", sa.String(length=160), nullable=True),
        sa.Column("trace_context_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'validated'"), nullable=False),
        sa.Column("runtime_policy_decision_id", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('validated','deciding','denied','approval_pending','authorized','expired')",
            name="ck_action_intents_status",
        ),
        sa.ForeignKeyConstraint(["contract_version_id"], ["action_contract_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["runtime_policy_decision_id"], ["runtime_policy_decisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "idempotency_key", name="ux_action_intents_project_idempotency"),
    )
    op.create_index("ix_action_intents_project_created", "action_intents", ["project_id", "created_at"])
    op.create_index("ix_action_intents_project_digest", "action_intents", ["project_id", "intent_digest"])
    op.create_index(
        "ix_action_intents_project_policy_decision",
        "action_intents",
        ["project_id", "runtime_policy_decision_id"],
    )
    op.create_index("ix_action_intents_project_status", "action_intents", ["project_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_action_intents_project_status", table_name="action_intents")
    op.drop_index("ix_action_intents_project_policy_decision", table_name="action_intents")
    op.drop_index("ix_action_intents_project_digest", table_name="action_intents")
    op.drop_index("ix_action_intents_project_created", table_name="action_intents")
    op.drop_table("action_intents")
    op.drop_index("ix_action_contract_versions_project_status", table_name="action_contract_versions")
    op.drop_index("ix_action_contract_versions_project_action", table_name="action_contract_versions")
    op.drop_table("action_contract_versions")
