"""create source mutation records

Revision ID: 0100_create_source_mutation_records
Revises: 0099_create_action_timeline_and_receipts
Create Date: 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0100_create_source_mutation_records"
down_revision = "0099_create_action_timeline_and_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_mutation_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("mutation_id", sa.String(length=255), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("system_ref", sa.String(length=255), nullable=True),
        sa.Column("actor_type", sa.String(length=64), nullable=True),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("zroky_action_id", sa.String(length=36), nullable=True),
        sa.Column("action_receipt_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "classification IN ('matched_receipt','authorized_external','legacy_path','unmanaged_agent_action','policy_bypass','unknown_actor')",
            name="ck_source_mutation_records_classification",
        ),
        sa.ForeignKeyConstraint(["action_receipt_id"], ["action_receipts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["zroky_action_id"], ["action_intents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "source_system",
            "mutation_id",
            name="ux_source_mutation_project_source_mutation",
        ),
    )
    op.create_index("ix_source_mutation_project_action", "source_mutation_records", ["project_id", "zroky_action_id"])
    op.create_index(
        "ix_source_mutation_project_classification",
        "source_mutation_records",
        ["project_id", "classification", "occurred_at"],
    )
    op.create_index("ix_source_mutation_project_occurred", "source_mutation_records", ["project_id", "occurred_at"])
    op.create_index("ix_source_mutation_project_receipt", "source_mutation_records", ["project_id", "action_receipt_id"])
    op.create_index(
        "ix_source_mutation_project_resource",
        "source_mutation_records",
        ["project_id", "resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_source_mutation_project_resource", table_name="source_mutation_records")
    op.drop_index("ix_source_mutation_project_receipt", table_name="source_mutation_records")
    op.drop_index("ix_source_mutation_project_occurred", table_name="source_mutation_records")
    op.drop_index("ix_source_mutation_project_classification", table_name="source_mutation_records")
    op.drop_index("ix_source_mutation_project_action", table_name="source_mutation_records")
    op.drop_table("source_mutation_records")
