"""add severity and blast_radius_usd to issues

Revision ID: 0046_add_issue_severity_blast_radius
Revises: 0045_add_fix_verification_columns
Create Date: 2026-05-12 09:00:00.000000

Adds two new columns to the `issues` table:
  - severity       VARCHAR(16) NOT NULL DEFAULT 'low'   — critical/high/medium/low
  - blast_radius_usd NUMERIC(18,8) NOT NULL DEFAULT 0   — cumulative cost of all occurrences
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046_add_issue_severity_blast_radius"
down_revision = "0045_add_fix_verification_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "issues",
        sa.Column(
            "severity",
            sa.String(16),
            nullable=False,
            server_default="low",
        ),
    )
    op.add_column(
        "issues",
        sa.Column(
            "blast_radius_usd",
            sa.Numeric(18, 8),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index("ix_issues_project_severity", "issues", ["project_id", "severity"])


def downgrade() -> None:
    op.drop_index("ix_issues_project_severity", table_name="issues")
    op.drop_column("issues", "blast_radius_usd")
    op.drop_column("issues", "severity")
