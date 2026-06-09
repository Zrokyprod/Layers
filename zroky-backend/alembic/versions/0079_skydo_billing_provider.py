"""add Skydo billing provider fields and event log

Revision ID: 0079_skydo_billing_provider
Revises: 0078_create_discovery_scan_state
Create Date: 2026-06-07 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0079_skydo_billing_provider"
down_revision = "0078_create_discovery_scan_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "payment_provider",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'skydo'"),
        ),
    )
    op.add_column(
        "subscriptions",
        sa.Column("payment_customer_ref", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("payment_subscription_ref", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("payment_request_ref", sa.String(length=128), nullable=True),
    )
    op.create_unique_constraint(
        "ux_subscriptions_payment_subscription_ref",
        "subscriptions",
        ["payment_subscription_ref"],
    )
    op.create_index(
        "ix_subscriptions_payment_provider",
        "subscriptions",
        ["payment_provider"],
    )
    op.create_index(
        "ix_subscriptions_payment_customer_ref",
        "subscriptions",
        ["payment_customer_ref"],
    )
    op.create_index(
        "ix_subscriptions_payment_request_ref",
        "subscriptions",
        ["payment_request_ref"],
    )

    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("provider_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "result",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("affected_org_id", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_event_id",
            name="ux_billing_events_provider_event_id",
        ),
        sa.CheckConstraint(
            "result IN ('pending', 'applied', 'skipped', 'failed')",
            name="ck_billing_events_result",
        ),
    )
    op.create_index("ix_billing_events_provider", "billing_events", ["provider"])
    op.create_index("ix_billing_events_event_type", "billing_events", ["event_type"])
    op.create_index(
        "ix_billing_events_received_at", "billing_events", ["received_at"]
    )
    op.create_index(
        "ix_billing_events_affected_org_id", "billing_events", ["affected_org_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_billing_events_affected_org_id", table_name="billing_events")
    op.drop_index("ix_billing_events_received_at", table_name="billing_events")
    op.drop_index("ix_billing_events_event_type", table_name="billing_events")
    op.drop_index("ix_billing_events_provider", table_name="billing_events")
    op.drop_table("billing_events")

    op.drop_index("ix_subscriptions_payment_request_ref", table_name="subscriptions")
    op.drop_index("ix_subscriptions_payment_customer_ref", table_name="subscriptions")
    op.drop_index("ix_subscriptions_payment_provider", table_name="subscriptions")
    op.drop_constraint(
        "ux_subscriptions_payment_subscription_ref",
        "subscriptions",
        type_="unique",
    )
    op.drop_column("subscriptions", "payment_request_ref")
    op.drop_column("subscriptions", "payment_subscription_ref")
    op.drop_column("subscriptions", "payment_customer_ref")
    op.drop_column("subscriptions", "payment_provider")
