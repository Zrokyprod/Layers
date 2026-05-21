"""create subscriptions + entitlements (Stripe-aligned billing rework, Phase A)

Revision ID: 0054_create_subscriptions_and_entitlements
Revises: 0053_create_digests
Create Date: 2026-05-13 18:30:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §5.2 / §10):
  - Phase A of the billing rewrite: we create the new Stripe-aligned
    `subscriptions` + `entitlements` tables alongside the legacy
    `subscription_plans` + `tenant_subscriptions`. App code (a later module)
    will dual-write, switch reads, then a follow-up migration drops the
    legacy pair.
  - `org_id` is the billing entity per plan §5.1. The `orgs` table does
    not yet exist; for now `org_id` equals the project_id of the org's
    primary project, populated by the app layer. When the `orgs` table is
    introduced, a FK constraint will be added without renaming columns.
  - No RLS on either table — billing data is owner/admin scope, controlled
    at the application layer. Matches the precedent of the legacy
    `subscription_plans` + `tenant_subscriptions` (also no RLS).
  - Subscription enums align with Stripe webhook event values:
      status: 'trialing' | 'active' | 'past_due' | 'canceled' | 'unpaid' | 'incomplete'
      plan_code: free-form short code ('free', 'watch', 'pilot', 'enterprise')
  - Entitlement `source` precedence at resolve time is:
      override > trial > plan
    Application resolver merges by priority.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0054_create_subscriptions_and_entitlements"
down_revision = "0053_create_digests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── subscriptions ────────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "org_id",
            sa.String(length=64),
            nullable=False,
            comment="Billing entity; equals project_id until orgs table is introduced",
        ),
        sa.Column(
            "stripe_customer_id",
            sa.String(length=64),
            nullable=True,
            comment="Stripe customer ID; NULL for free-tier or pre-Stripe rows",
        ),
        sa.Column(
            "stripe_sub_id",
            sa.String(length=64),
            nullable=True,
            comment="Stripe subscription ID; NULL until a Stripe sub is created",
        ),
        sa.Column(
            "plan_code",
            sa.String(length=32),
            nullable=False,
            comment="'free' | 'watch' | 'pilot' | 'enterprise' (free-form code)",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'active'"),
            comment="Stripe-aligned: trialing|active|past_due|canceled|unpaid|incomplete",
        ),
        sa.Column(
            "seats",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("org_id", name="ux_subscriptions_org"),
        sa.UniqueConstraint("stripe_sub_id", name="ux_subscriptions_stripe_sub_id"),
        sa.CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'canceled', 'unpaid', 'incomplete')",
            name="ck_subscriptions_status",
        ),
    )
    op.create_index(
        "ix_subscriptions_stripe_customer_id",
        "subscriptions",
        ["stripe_customer_id"],
    )
    op.create_index(
        "ix_subscriptions_status",
        "subscriptions",
        ["status"],
    )
    op.create_index(
        "ix_subscriptions_plan_code",
        "subscriptions",
        ["plan_code"],
    )
    op.create_index(
        "ix_subscriptions_current_period_end",
        "subscriptions",
        ["current_period_end"],
    )

    # ── entitlements ─────────────────────────────────────────────────────────
    op.create_table(
        "entitlements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column(
            "key",
            sa.String(length=64),
            nullable=False,
            comment="e.g. 'max_calls_per_month', 'pilot_enabled', 'replay_enabled'",
        ),
        sa.Column(
            "value_json",
            sa.Text(),
            nullable=False,
            comment="JSON-encoded scalar/array (int|bool|string|list)",
        ),
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            comment="'plan' | 'override' | 'trial' — resolver precedence: override > trial > plan",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "org_id", "key", "source",
            name="ux_entitlements_org_key_source",
        ),
        sa.CheckConstraint(
            "source IN ('plan', 'override', 'trial')",
            name="ck_entitlements_source",
        ),
    )
    op.create_index(
        "ix_entitlements_org_key",
        "entitlements",
        ["org_id", "key"],
    )
    op.create_index(
        "ix_entitlements_org_expires_at",
        "entitlements",
        ["org_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_entitlements_org_expires_at", table_name="entitlements")
    op.drop_index("ix_entitlements_org_key", table_name="entitlements")
    op.drop_table("entitlements")

    op.drop_index("ix_subscriptions_current_period_end", table_name="subscriptions")
    op.drop_index("ix_subscriptions_plan_code", table_name="subscriptions")
    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_stripe_customer_id", table_name="subscriptions")
    op.drop_table("subscriptions")
