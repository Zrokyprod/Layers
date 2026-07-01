"""add action execution request

Revision ID: 0106_add_action_execution_request
Revises: 0105_create_action_post_execution_jobs
Create Date: 2026-06-28 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0106_add_action_execution_request"
down_revision = "0105_create_action_post_execution_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("action_intents") as batch_op:
        batch_op.add_column(sa.Column("execution_request_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("action_intents") as batch_op:
        batch_op.drop_column("execution_request_json")
