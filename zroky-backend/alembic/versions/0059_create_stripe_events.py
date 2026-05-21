"""create stripe_events table for webhook idempotency

Revision ID: 0059_create_stripe_events
Revises: 0058_create_provider_keys_vault
Create Date: 2026-05-14 12:00:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §11.3 + §17.1 risk #3):
  - Stripe at-least-once delivers webhooks; the SAME event id can arrive
    twice (network retry) AND two webhooks for the same subscription
    can arrive out of order. Both failure modes are mitigated by the
    same row in this table.
  - `stripe_event_id` is UNIQUE. The webhook handler does:
      1) INSERT-or-conflict on stripe_event_id   → idempotent claim
      2) Apply the event to subscriptions/entitlements
      3) UPDATE processed_at + result on success
    A duplicate delivery hits the UNIQUE constraint and the handler
    short-circuits with HTTP 200 (Stripe stops retrying).
  - `payload_json` keeps the full raw event for audit / replay. We
    write it on first insert; later re-deliveries don't overwrite.
  - Global table — no `org_id`. The webhook authenticates via Stripe's
    HMAC-SHA256 signature, not a tenant header. The dispatcher resolves
    the affected `org_id` from the event payload (customer/subscription
    metadata) and writes audit on the corresponding `subscriptions` row.
  - `event_type` indexed so the founder console can pull "all
    invoice.payment_failed events in last 24h" cheaply.
  - `result` enum: 'pending' | 'applied' | 'skipped' | 'failed'.
    'skipped' covers events we don't handle (e.g. customer.created)
    so the row still records "we saw it" for completeness.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0059_create_stripe_events"
down_revision = "0058_create_provider_keys_vault"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "stripe_event_id",
            sa.String(length=64),
            nullable=False,
            comment="Stripe's evt_xxx id; UNIQUE — primary idempotency key",
        ),
        sa.Column(
            "event_type",
            sa.String(length=64),
            nullable=False,
            comment=(
                "'checkout.session.completed' | 'customer.subscription.updated' "
                "| 'customer.subscription.deleted' | 'invoice.paid' | "
                "'invoice.payment_failed' | other (skipped)"
            ),
        ),
        sa.Column(
            "stripe_created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Stripe's `created` field; useful for ordering",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the dispatcher finished applying this event",
        ),
        sa.Column(
            "result",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="'pending' | 'applied' | 'skipped' | 'failed'",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Truncated exception string when result='failed'",
        ),
        sa.Column(
            "affected_org_id",
            sa.String(length=64),
            nullable=True,
            comment=(
                "Resolved org_id (= subscriptions.org_id) when known; NULL "
                "when the event arrived before the subscription row existed."
            ),
        ),
        sa.Column(
            "payload_json",
            sa.Text(),
            nullable=False,
            comment="Full raw event JSON for audit/replay",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stripe_event_id", name="ux_stripe_events_stripe_event_id"
        ),
        sa.CheckConstraint(
            "result IN ('pending', 'applied', 'skipped', 'failed')",
            name="ck_stripe_events_result",
        ),
    )
    op.create_index(
        "ix_stripe_events_event_type",
        "stripe_events",
        ["event_type"],
    )
    op.create_index(
        "ix_stripe_events_received_at",
        "stripe_events",
        ["received_at"],
    )
    op.create_index(
        "ix_stripe_events_affected_org_id",
        "stripe_events",
        ["affected_org_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stripe_events_affected_org_id", table_name="stripe_events")
    op.drop_index("ix_stripe_events_received_at", table_name="stripe_events")
    op.drop_index("ix_stripe_events_event_type", table_name="stripe_events")
    op.drop_table("stripe_events")
