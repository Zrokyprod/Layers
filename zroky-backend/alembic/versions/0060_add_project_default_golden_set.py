"""add projects.default_golden_set_id (Module 9 — GitHub-Action dispatch surface)

Revision ID: 0060_add_project_default_golden_set
Revises: 0059_create_stripe_events
Create Date: 2026-05-14 22:00:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §6.4 + §4.4):
  - The `zroky/regression-ci@v1` GitHub Action POSTs to
    `/v1/replay/dispatch` with an API key + git_sha but typically NO
    explicit `golden_set_id` — the customer's CI workflow just says
    "run the project's default golden set against this commit".
  - This migration adds an OPTIONAL pointer from each project to its
    "default" golden set so the dispatch endpoint can resolve which
    set to replay when the Action does not name one.
  - Column is nullable: pre-existing projects (and any project that
    hasn't yet been wired up to a golden set) leave this NULL and the
    dispatch endpoint returns 422 "no default golden set; pass
    golden_set_id explicitly". This is preferable to a sentinel
    default because (a) different projects use different sets and
    (b) silently picking the first row would cause cross-set runs.
  - **No FK on `golden_sets.id`** — matches the project_id convention
    across migrations 0049/0050/0052/0053/0054. RLS on
    `golden_sets.project_id` already enforces tenant isolation, and
    avoiding the FK keeps SQLite test fixtures simple.
  - Application layer enforces:
        (a) the referenced golden set belongs to the same project,
        (b) clearing the pointer when the referenced golden set is
            deleted (not handled at DB level — service layer drops it
            in `delete_golden_set` if it matches).
  - Index added so the rare "list all projects defaulting to set X"
    query (used by the dashboard's "set is in use" badge) stays fast.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0060_add_project_default_golden_set"
down_revision = "0059_create_stripe_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "default_golden_set_id",
            sa.String(64),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_projects_default_golden_set_id",
        "projects",
        ["default_golden_set_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_projects_default_golden_set_id",
        table_name="projects",
    )
    op.drop_column("projects", "default_golden_set_id")
