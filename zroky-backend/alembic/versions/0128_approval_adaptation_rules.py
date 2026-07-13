"""Add owner-approved, bounded approval adaptation rules.

Revision ID: 0128_approval_adaptation_rules
Revises: 0127_tenant_verification_dispatch
Create Date: 2026-07-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0128_approval_adaptation_rules"
down_revision = "0127_tenant_verification_dispatch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approval_adaptation_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("scope_hash", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("action_type", sa.String(length=160), nullable=False),
        sa.Column("operation_kind", sa.String(length=32), nullable=False),
        sa.Column("contract_key", sa.String(length=160), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("evidence_approved_count", sa.Integer(), nullable=False),
        sa.Column("evidence_matched_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("activated_by_subject", sa.String(length=255), nullable=True),
        sa.Column("revoked_by_subject", sa.String(length=255), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "operation_kind IN ('UPDATE')",
            name="ck_approval_adaptation_rules_operation_kind",
        ),
        sa.CheckConstraint(
            "status IN ('active','revoked')",
            name="ck_approval_adaptation_rules_status",
        ),
        sa.CheckConstraint(
            "evidence_approved_count >= 1",
            name="ck_approval_adaptation_rules_approved_count",
        ),
        sa.CheckConstraint(
            "evidence_matched_count >= 1",
            name="ck_approval_adaptation_rules_matched_count",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approval_adaptation_rules_project_scope_status_expiry",
        "approval_adaptation_rules",
        ["project_id", "scope_hash", "status", "expires_at"],
    )
    op.create_index(
        "ix_approval_adaptation_rules_project_status_expiry",
        "approval_adaptation_rules",
        ["project_id", "status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_approval_adaptation_rules_project_status_expiry",
        table_name="approval_adaptation_rules",
    )
    op.drop_index(
        "ix_approval_adaptation_rules_project_scope_status_expiry",
        table_name="approval_adaptation_rules",
    )
    op.drop_table("approval_adaptation_rules")
