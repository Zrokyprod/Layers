"""Add support tickets and messages tables

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-05

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("subject", sa.String(255), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(64), nullable=False, server_default=sa.text("'general'")),
        sa.Column("priority", sa.String(16), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'open'")),
        sa.Column("assigned_to", sa.String(255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), onupdate=sa.text("now()")),
    )
    op.create_index("ix_support_tickets_tenant", "support_tickets", ["tenant_id"])
    op.create_index("ix_support_tickets_user", "support_tickets", ["user_id"])
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"])
    op.create_index("ix_support_tickets_created_at", "support_tickets", ["created_at"])

    op.create_table(
        "support_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_type", sa.String(16), nullable=False, server_default=sa.text("'user'")),
        sa.Column("sender_subject", sa.String(255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_support_messages_ticket", "support_messages", ["ticket_id"])
    op.create_index("ix_support_messages_created_at", "support_messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_support_messages_created_at", table_name="support_messages")
    op.drop_index("ix_support_messages_ticket", table_name="support_messages")
    op.drop_table("support_messages")

    op.drop_index("ix_support_tickets_created_at", table_name="support_tickets")
    op.drop_index("ix_support_tickets_status", table_name="support_tickets")
    op.drop_index("ix_support_tickets_user", table_name="support_tickets")
    op.drop_index("ix_support_tickets_tenant", table_name="support_tickets")
    op.drop_table("support_tickets")
