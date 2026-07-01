"""add action intent agent binding

Revision ID: 0107_add_action_intent_agent_id
Revises: 0106_add_action_execution_request
Create Date: 2026-06-28 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0107_add_action_intent_agent_id"
down_revision = "0106_add_action_execution_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("action_intents") as batch_op:
        batch_op.add_column(sa.Column("agent_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_action_intents_agent_id",
            "agents",
            ["agent_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_action_intents_project_agent_created",
        "action_intents",
        ["project_id", "agent_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_action_intents_project_agent_created", table_name="action_intents")
    with op.batch_alter_table("action_intents") as batch_op:
        batch_op.drop_constraint("fk_action_intents_agent_id", type_="foreignkey")
        batch_op.drop_column("agent_id")
