"""create action timeline and receipts

Revision ID: 0099_create_action_timeline_and_receipts
Revises: 0098_create_action_runner_foundation
Create Date: 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0099_create_action_timeline_and_receipts"
down_revision = "0098_create_action_runner_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_timeline_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("action_intent_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_digest", sa.String(length=80), nullable=False),
        sa.Column("event_payload_json", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["action_intent_id"], ["action_intents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_action_timeline_events_project_intent_created",
        "action_timeline_events",
        ["project_id", "action_intent_id", "created_at"],
    )
    op.create_index(
        "ix_action_timeline_events_project_type_created",
        "action_timeline_events",
        ["project_id", "event_type", "created_at"],
    )

    op.create_table(
        "action_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("action_intent_id", sa.String(length=36), nullable=False),
        sa.Column("receipt_digest", sa.String(length=80), nullable=False),
        sa.Column("receipt_json", sa.Text(), nullable=False),
        sa.Column("evidence_hash", sa.String(length=80), nullable=True),
        sa.Column("signature_algorithm", sa.String(length=32), server_default=sa.text("'HMAC-SHA256'"), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.Column("signing_key_id", sa.String(length=128), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["action_intent_id"], ["action_intents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "action_intent_id", name="ux_action_receipts_project_intent"),
    )
    op.create_index("ix_action_receipts_project_created", "action_receipts", ["project_id", "created_at"])
    op.create_index("ix_action_receipts_project_digest", "action_receipts", ["project_id", "receipt_digest"])


def downgrade() -> None:
    op.drop_index("ix_action_receipts_project_digest", table_name="action_receipts")
    op.drop_index("ix_action_receipts_project_created", table_name="action_receipts")
    op.drop_table("action_receipts")
    op.drop_index("ix_action_timeline_events_project_type_created", table_name="action_timeline_events")
    op.drop_index("ix_action_timeline_events_project_intent_created", table_name="action_timeline_events")
    op.drop_table("action_timeline_events")
