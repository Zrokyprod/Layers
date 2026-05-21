"""create support_threads + support_messages (modern conversational support)

Revision ID: 0056_create_support_threads_and_messages
Revises: 0055_create_intel_signals
Create Date: 2026-05-13 19:30:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §5.2):
  - Phase A: new tables live alongside legacy `support_tickets`. App code
    (a later module) will switch reads/writes; a follow-up migration will
    drop `support_tickets`.
  - Naming collision: the LEGACY table was named `support_messages` (it
    held child messages of `support_tickets`). Plan §5.2 mandates that
    name for the NEW thread-message schema. We free the slot by renaming
    legacy `support_messages` → `support_ticket_messages` (which is also
    the semantically clearer name) and updating its indexes accordingly.
    The legacy ORM class is renamed to `SupportTicketMessage` in the same
    commit.
  - support_threads:  one conversation thread per row. `last_activity_at`
                      is bumped on every new message for inbox sort.
  - support_messages: append-only message log under a thread.
                      `sender_role ∈ {user, support, system}`. `system`
                      covers auto-generated notes (status changes, etc.).
                      `project_id` is denormalised for RLS-without-JOIN.
  - Foreign keys:
        support_threads.created_by_user_id → users.id           ON DELETE SET NULL
        support_messages.thread_id         → support_threads.id ON DELETE CASCADE
        support_messages.sender_user_id    → users.id           ON DELETE SET NULL
    (User deletion preserves the historical thread / message rows.)
  - `assigned_to` is a free-form String identifier (email or user_id), not
    a FK — support agents may be external email addresses.
  - Postgres RLS by project_id on both tables.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0056_create_support_threads_and_messages"
down_revision = "0055_create_intel_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── rename legacy support_messages → support_ticket_messages ─────────────
    # (frees the `support_messages` table name for the new thread-message schema)
    op.rename_table("support_messages", "support_ticket_messages")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER INDEX ix_support_messages_ticket RENAME TO ix_support_ticket_messages_ticket"
        )
        op.execute(
            "ALTER INDEX ix_support_messages_created_at RENAME TO ix_support_ticket_messages_created_at"
        )

    # ── support_threads ──────────────────────────────────────────────────────
    op.create_table(
        "support_threads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'open'"),
            comment="'open' | 'pending' | 'on_hold' | 'resolved' | 'closed'",
        ),
        sa.Column(
            "priority",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'medium'"),
            comment="'low' | 'medium' | 'high' | 'urgent'",
        ),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "assigned_to",
            sa.String(length=255),
            nullable=True,
            comment="Free-form agent identifier (email or user_id); not a FK",
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Bumped on every new message; drives inbox sort",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_support_threads_created_by_user_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'pending', 'on_hold', 'resolved', 'closed')",
            name="ck_support_threads_status",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')",
            name="ck_support_threads_priority",
        ),
    )
    op.create_index(
        "ix_support_threads_project_status_activity",
        "support_threads",
        ["project_id", "status", "last_activity_at"],
    )
    op.create_index(
        "ix_support_threads_project_last_activity",
        "support_threads",
        ["project_id", "last_activity_at"],
    )
    op.create_index(
        "ix_support_threads_project_status",
        "support_threads",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_support_threads_assigned_to",
        "support_threads",
        ["assigned_to"],
    )
    op.create_index(
        "ix_support_threads_created_by_user_id",
        "support_threads",
        ["created_by_user_id"],
    )

    # ── support_messages ─────────────────────────────────────────────────────
    op.create_table(
        "support_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column(
            "project_id",
            sa.String(length=64),
            nullable=False,
            comment="Denormalised from parent thread for RLS-without-JOIN",
        ),
        sa.Column("sender_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "sender_role",
            sa.String(length=16),
            nullable=False,
            comment="'user' | 'support' | 'system'",
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "attachments_json",
            sa.Text(),
            nullable=True,
            comment="JSON array of attachment refs",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["support_threads.id"],
            name="fk_support_messages_thread_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_user_id"],
            ["users.id"],
            name="fk_support_messages_sender_user_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "sender_role IN ('user', 'support', 'system')",
            name="ck_support_messages_sender_role",
        ),
    )
    op.create_index(
        "ix_support_messages_thread_created",
        "support_messages",
        ["thread_id", "created_at"],
    )
    op.create_index(
        "ix_support_messages_project_created",
        "support_messages",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_support_messages_sender_user_id",
        "support_messages",
        ["sender_user_id"],
    )

    # ── RLS (Postgres only) ──────────────────────────────────────────────────
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table_name in ("support_threads", "support_messages"):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")
        op.execute(
            f"""
            CREATE POLICY {table_name}_tenant_isolation
            ON {table_name}
            USING (project_id = current_setting('app.current_tenant_id', true))
            WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table_name in ("support_messages", "support_threads"):
            op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_support_messages_sender_user_id", table_name="support_messages")
    op.drop_index("ix_support_messages_project_created", table_name="support_messages")
    op.drop_index("ix_support_messages_thread_created", table_name="support_messages")
    op.drop_table("support_messages")

    op.drop_index("ix_support_threads_created_by_user_id", table_name="support_threads")
    op.drop_index("ix_support_threads_assigned_to", table_name="support_threads")
    op.drop_index("ix_support_threads_project_status", table_name="support_threads")
    op.drop_index("ix_support_threads_project_last_activity", table_name="support_threads")
    op.drop_index("ix_support_threads_project_status_activity", table_name="support_threads")
    op.drop_table("support_threads")

    # ── reverse the legacy support_messages rename ───────────────────────────
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER INDEX ix_support_ticket_messages_created_at RENAME TO ix_support_messages_created_at"
        )
        op.execute(
            "ALTER INDEX ix_support_ticket_messages_ticket RENAME TO ix_support_messages_ticket"
        )
    op.rename_table("support_ticket_messages", "support_messages")
