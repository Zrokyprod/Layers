"""add feature_interest_votes (Module 9 smoke-test alternative)

Revision ID: 0063_add_feature_interest_votes
Revises: 0062_add_subscription_sla_tier
Create Date: 2026-05-16 22:00:00.000000

Schema notes:
  Adds one new table to support coming-soon feature interest polls
  (e.g. `pilot.tier1_autonomy`). The customer dashboard renders a
  grayed-out feature row + a thumbs-up/thumbs-down poll; votes are
  stored here for the owner to aggregate via /v1/owner endpoints
  and the `scripts/show_feature_votes.py` CLI viewer.

  Unique on (subject, feature_key) so each user gets exactly one
  vote per feature globally (changeable via upsert). `project_id`
  is denormalized at vote time so admin queries can group/filter
  by project context, but is not part of the unique key.

  CHECK constraint enforces vote vocab ('interested',
  'not_interested') at the DB layer.

Plan ref: validates demand for Tier-1 autonomy (plan §6.3) before
the executor itself is built. If aggregate vote crosses the
`ships_after_threshold` in
`app/services/feature_interest_registry.py`, Module 9 proper is
prioritized.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0063_add_feature_interest_votes"
down_revision = "0062_add_subscription_sla_tier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_interest_votes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column(
            "project_id",
            sa.String(length=64),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feature_key", sa.String(length=64), nullable=False),
        sa.Column("vote", sa.String(length=16), nullable=False),
        sa.Column("use_case", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "subject", "feature_key",
            name="ux_feature_votes_subject_feature",
        ),
        sa.CheckConstraint(
            "vote IN ('interested', 'not_interested')",
            name="ck_feature_votes_vote",
        ),
    )

    op.create_index(
        "ix_feature_votes_key_vote",
        "feature_interest_votes",
        ["feature_key", "vote"],
    )
    op.create_index(
        "ix_feature_votes_project",
        "feature_interest_votes",
        ["project_id"],
    )
    op.create_index(
        "ix_feature_votes_created",
        "feature_interest_votes",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_feature_votes_created", table_name="feature_interest_votes"
    )
    op.drop_index(
        "ix_feature_votes_project", table_name="feature_interest_votes"
    )
    op.drop_index(
        "ix_feature_votes_key_vote", table_name="feature_interest_votes"
    )
    op.drop_table("feature_interest_votes")
