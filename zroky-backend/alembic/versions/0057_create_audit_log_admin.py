"""create audit_log_admin (admin/owner action trail)

Revision ID: 0057_create_audit_log_admin
Revises: 0056_create_support_threads_and_messages
Create Date: 2026-05-13 20:00:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §5.2):
  - Captures actions taken by ZROKY staff (owner, support, admin) and the
    platform itself (system) against tenant data or platform state.
    Distinct from the existing tenant-scoped `audit_logs` table.
  - NOT tenant-scoped: no project_id column, no RLS. Reads are restricted
    at the route layer (owner/admin endpoints only).
  - `before_json` / `after_json` snapshot entity state for diffs.
  - Foreign keys:
        audit_log_admin.actor_user_id → users.id  ON DELETE SET NULL
    (Preserves the trail even if the acting user is deleted.)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0057_create_audit_log_admin"
down_revision = "0056_create_support_threads_and_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log_admin",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.String(length=36),
            nullable=True,
            comment="NULL for system actions or after the user is deleted",
        ),
        sa.Column(
            "actor_role",
            sa.String(length=32),
            nullable=False,
            comment="'owner' | 'support' | 'admin' | 'system'",
        ),
        sa.Column(
            "action",
            sa.String(length=64),
            nullable=False,
            comment="e.g. 'project.suspend', 'user.impersonate', 'subscription.override'",
        ),
        sa.Column(
            "target_type",
            sa.String(length=32),
            nullable=True,
            comment="e.g. 'project', 'user', 'subscription'",
        ),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column(
            "ip",
            sa.String(length=45),
            nullable=True,
            comment="IPv4 or IPv6 address",
        ),
        sa.Column("ua", sa.String(length=512), nullable=True),
        sa.Column(
            "request_id",
            sa.String(length=64),
            nullable=True,
            comment="Correlated tracing ID",
        ),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_log_admin_actor_user_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "actor_role IN ('owner', 'support', 'admin', 'system')",
            name="ck_audit_log_admin_actor_role",
        ),
    )

    op.create_index(
        "ix_audit_log_admin_actor_created",
        "audit_log_admin",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_audit_log_admin_target",
        "audit_log_admin",
        ["target_type", "target_id", "created_at"],
    )
    op.create_index(
        "ix_audit_log_admin_action_created",
        "audit_log_admin",
        ["action", "created_at"],
    )
    op.create_index(
        "ix_audit_log_admin_created_at",
        "audit_log_admin",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_admin_created_at", table_name="audit_log_admin")
    op.drop_index("ix_audit_log_admin_action_created", table_name="audit_log_admin")
    op.drop_index("ix_audit_log_admin_target", table_name="audit_log_admin")
    op.drop_index("ix_audit_log_admin_actor_created", table_name="audit_log_admin")
    op.drop_table("audit_log_admin")
