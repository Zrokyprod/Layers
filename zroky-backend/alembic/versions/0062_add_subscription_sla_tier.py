"""add subscriptions.sla_tier (Module 12; plan section 11.4 Reliability SLA)

Revision ID: 0062_add_subscription_sla_tier
Revises: 0061_extend_pilot_actions_for_tier2
Create Date: 2026-05-15 00:00:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 section 11.4):
  Adds one column to `subscriptions` to support the locked-decision
  Reliability SLA contract clause (replaces the deferred Insurance
  add-on per section 17.2 decision 2).

  • sla_tier  ENUM('none','team','enterprise')  DEFAULT 'none'
        Identifies which SLA tier (and therefore which refund-on-miss
        contract clause) applies to an org's billing period. Default
        'none' so existing rows + new orgs are inert until the Founder
        Console (Module 13) explicitly upgrades a customer.
        Values:
          'none'        — Free / Starter / Pro tiers; no SLA refund.
          'team'        — Team tier; standard SLA contract (max 1x
                          monthly fee refund per affected period).
          'enterprise'  — Enterprise tier; bespoke contract (clause
                          parity with team; bounded liability still 1x).

  No FK relations. The application layer (Module 12 sweep tasks +
  Module 13 admin write-path) is the source of truth for transitions.

  Why a column on `subscriptions` and not a separate `sla_contracts`
  table:
    - One-row-per-org cardinality matches `subscriptions.org_id`.
    - The SLA tier moves with the customer's plan (you can't have
      a Team-SLA on a Free plan), so coupling them in one row makes
      the resolver join-free.
    - Section 11.4 explicitly says `subscriptions.sla_tier`, not a
      separate table.

CHECK constraint vocab is enforced at insert/update time. The Postgres
path adds the constraint directly; the SQLite path uses a batch_alter
because SQLite cannot ADD CHECK on an existing table.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0062_add_subscription_sla_tier"
down_revision = "0061_extend_pilot_actions_for_tier2"
branch_labels = None
depends_on = None


_CHECK_NAME = "ck_subscriptions_sla_tier"
_CHECK_SQL = "sla_tier IN ('none', 'team', 'enterprise')"


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "sla_tier",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Production path — non-blocking on small tables, locks the
        # schema briefly. `subscriptions` is one-row-per-org so the
        # row count is always small relative to other tables.
        op.create_check_constraint(
            _CHECK_NAME, "subscriptions", _CHECK_SQL,
        )
    else:
        # SQLite path — has to rebuild the table to add a table-level
        # CHECK. Acceptable for tests (fresh DB) and self-host (small
        # tenant count). batch_alter_table is the documented escape
        # hatch.
        with op.batch_alter_table("subscriptions") as batch_op:
            batch_op.create_check_constraint(_CHECK_NAME, _CHECK_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint(
            _CHECK_NAME, "subscriptions", type_="check",
        )
    else:
        with op.batch_alter_table("subscriptions") as batch_op:
            batch_op.drop_constraint(_CHECK_NAME, type_="check")

    op.drop_column("subscriptions", "sla_tier")
