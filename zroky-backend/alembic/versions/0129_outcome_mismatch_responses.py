"""Add durable evidence-first response cases for confirmed outcome mismatches.

Revision ID: 0129_outcome_mismatch_responses
Revises: 0128_approval_adaptation_rules
Create Date: 2026-07-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0129_outcome_mismatch_responses"
down_revision = "0128_approval_adaptation_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    action_intent_column = sa.Column("action_intent_id", sa.String(length=36), nullable=True)
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("outcome_reconciliation_checks") as batch_op:
            batch_op.add_column(action_intent_column)
            batch_op.create_foreign_key(
                "fk_outcome_reconciliation_action_intent",
                "action_intents",
                ["action_intent_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index(
                "ix_outcome_reconciliation_action",
                ["project_id", "action_intent_id"],
            )
    else:
        op.add_column("outcome_reconciliation_checks", action_intent_column)
        op.create_foreign_key(
            "fk_outcome_reconciliation_action_intent",
            "outcome_reconciliation_checks",
            "action_intents",
            ["action_intent_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_outcome_reconciliation_action",
            "outcome_reconciliation_checks",
            ["project_id", "action_intent_id"],
        )
    op.create_table(
        "outcome_mismatch_responses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("reconciliation_check_id", sa.String(length=36), nullable=False),
        sa.Column("action_intent_id", sa.String(length=36), nullable=True),
        sa.Column("alert_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OPEN"),
        sa.Column("resolution_code", sa.String(length=32), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("remediation_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("acknowledged_by_subject", sa.String(length=255), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_subject", sa.String(length=255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('OPEN','ACKNOWLEDGED','RESOLVED')",
            name="ck_outcome_mismatch_responses_status",
        ),
        sa.CheckConstraint(
            "resolution_code IS NULL OR resolution_code IN ('confirmed_mismatch','expected_change','false_positive','unresolved')",
            name="ck_outcome_mismatch_responses_resolution_code",
        ),
        sa.ForeignKeyConstraint(
            ["reconciliation_check_id"],
            ["outcome_reconciliation_checks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["action_intent_id"], ["action_intents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["alert_id"], ["project_alerts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "reconciliation_check_id",
            name="ux_outcome_mismatch_responses_project_check",
        ),
    )
    op.create_index(
        "ix_outcome_mismatch_responses_project_status_created",
        "outcome_mismatch_responses",
        ["project_id", "status", "created_at"],
    )
    op.create_index(
        "ix_outcome_mismatch_responses_project_action",
        "outcome_mismatch_responses",
        ["project_id", "action_intent_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outcome_mismatch_responses_project_action",
        table_name="outcome_mismatch_responses",
    )
    op.drop_index(
        "ix_outcome_mismatch_responses_project_status_created",
        table_name="outcome_mismatch_responses",
    )
    op.drop_table("outcome_mismatch_responses")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("outcome_reconciliation_checks") as batch_op:
            batch_op.drop_index("ix_outcome_reconciliation_action")
            batch_op.drop_constraint("fk_outcome_reconciliation_action_intent", type_="foreignkey")
            batch_op.drop_column("action_intent_id")
    else:
        op.drop_index(
            "ix_outcome_reconciliation_action",
            table_name="outcome_reconciliation_checks",
        )
        op.drop_constraint(
            "fk_outcome_reconciliation_action_intent",
            "outcome_reconciliation_checks",
            type_="foreignkey",
        )
        op.drop_column("outcome_reconciliation_checks", "action_intent_id")
