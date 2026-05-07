"""Add first-class call attribution columns

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-06

"""

from alembic import op
import sqlalchemy as sa


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("agent_name", sa.String(length=255), nullable=True))
    op.add_column("calls", sa.Column("user_id", sa.String(length=255), nullable=True))
    op.add_column("calls", sa.Column("call_type", sa.String(length=32), nullable=True))

    op.create_index("ix_calls_project_agent_created", "calls", ["project_id", "agent_name", "created_at"])
    op.create_index("ix_calls_project_user_created", "calls", ["project_id", "user_id", "created_at"])
    op.create_index("ix_calls_project_call_type_created", "calls", ["project_id", "call_type", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_calls_project_call_type_created", table_name="calls")
    op.drop_index("ix_calls_project_user_created", table_name="calls")
    op.drop_index("ix_calls_project_agent_created", table_name="calls")

    op.drop_column("calls", "call_type")
    op.drop_column("calls", "user_id")
    op.drop_column("calls", "agent_name")
