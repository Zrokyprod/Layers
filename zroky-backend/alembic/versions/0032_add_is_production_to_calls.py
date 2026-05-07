"""Add is_production column and index to calls table

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-06

Rationale: replaces the per-query LIKE scans on payload_json / metadata_json that
were used to exclude synthetic/test calls from cost analytics. Writing the flag
once at ingest time and filtering on a boolean index is orders of magnitude
cheaper than scanning large TEXT columns on every analytics query.

Existing rows receive server_default=True (treated as production) which is safe —
they were already passing the old LIKE filters or they would have been excluded.
"""

from alembic import op
import sqlalchemy as sa


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calls",
        sa.Column(
            "is_production",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_index(
        "ix_calls_project_is_production_created",
        "calls",
        ["project_id", "is_production", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_calls_project_is_production_created", table_name="calls")
    op.drop_column("calls", "is_production")
