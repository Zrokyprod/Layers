"""extend pilot_actions for Tier-2 auto-PR (Module 10)

Revision ID: 0061_extend_pilot_actions_for_tier2
Revises: 0060_add_project_default_golden_set
Create Date: 2026-05-14 22:30:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §6.3 + §17.1 risk #1):
  Adds three columns to `pilot_actions` to support Tier-2 auto-PR
  behavior end-to-end. None of these are required for Tier-1
  (auto-revert) actions — they all stay NULL on tier-1 rows.

  • pr_url
        Populated once a Tier-2 action has actually opened a PR on
        the customer's repo (or a "dry-run://..." sentinel when the
        action ran against the DryRunPRClient). NULL while the row
        is still in `pending` state. VARCHAR(512) sized to match
        GitHub's URL limits with headroom for self-hosted variants.

  • pr_fingerprint
        SHA-256 hex digest of (project_id, anomaly_id, fix_kind,
        normalized_patch_body). Used to short-circuit repeat
        dispatches: if a Tier-2 evaluation produces the same patch
        for the same anomaly twice (e.g. a worker retry after a
        transient network error), the second dispatch maps to the
        first row's pr_url instead of opening a duplicate PR on the
        customer's repo. Index (project_id, pr_fingerprint) makes
        this O(1) and forms the idempotency boundary.

  • replay_run_id_gate
        The ReplayRun id whose pass-rate cleared the §17.1 risk-#1
        replay-pass gate (>= 0.95 by policy default). Stamped at
        Tier-2 *evaluation* time, before the PR is opened, so even
        a failed PR-creation attempt preserves the gate evidence
        for audit. NULL on tier-1/tier-3 rows. Foreign-key
        omitted to match the project_id convention across 0049 /
        0050 / 0052 / 0054 (RLS is the tenant boundary).

  No CHECK constraints are added because the columns must be NULL
  on tier-1 and tier-3 rows; the invariant is enforced at the
  application layer (`pilot_pr_dispatch.evaluate_tier2_dispatch`).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0061_extend_pilot_actions_for_tier2"
down_revision = "0060_add_project_default_golden_set"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pilot_actions",
        sa.Column("pr_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "pilot_actions",
        sa.Column("pr_fingerprint", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "pilot_actions",
        sa.Column("replay_run_id_gate", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_pilot_actions_project_pr_fingerprint",
        "pilot_actions",
        ["project_id", "pr_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pilot_actions_project_pr_fingerprint",
        table_name="pilot_actions",
    )
    op.drop_column("pilot_actions", "replay_run_id_gate")
    op.drop_column("pilot_actions", "pr_fingerprint")
    op.drop_column("pilot_actions", "pr_url")
