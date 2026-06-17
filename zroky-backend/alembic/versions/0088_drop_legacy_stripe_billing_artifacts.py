"""drop legacy Stripe billing artifacts after provider-neutral migration

Revision ID: 0088_drop_legacy_stripe_billing_artifacts
Revises: 0087_razorpay_only_billing
Create Date: 2026-06-13 00:00:00.000000

This migration intentionally removes Stripe-era schema through a forward
revision instead of rewriting already-applied historical migrations.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0088_drop_legacy_stripe_billing_artifacts"
down_revision = "0087_razorpay_only_billing"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_names(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {index["name"] for index in _inspector().get_indexes(table_name)}


def _unique_constraint_names(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {
        constraint["name"]
        for constraint in _inspector().get_unique_constraints(table_name)
        if constraint.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()

    if _has_table("stripe_events"):
        op.drop_table("stripe_events")

    legacy_columns = _column_names("subscriptions")
    if "ix_subscriptions_stripe_customer_id" in _index_names("subscriptions"):
        op.drop_index(
            "ix_subscriptions_stripe_customer_id",
            table_name="subscriptions",
        )

    drop_customer = "stripe_customer_id" in legacy_columns
    drop_subscription = "stripe_sub_id" in legacy_columns
    if not drop_customer and not drop_subscription:
        return

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("subscriptions") as batch_op:
            if "ux_subscriptions_stripe_sub_id" in _unique_constraint_names(
                "subscriptions"
            ):
                batch_op.drop_constraint(
                    "ux_subscriptions_stripe_sub_id",
                    type_="unique",
                )
            if drop_subscription:
                batch_op.drop_column("stripe_sub_id")
            if drop_customer:
                batch_op.drop_column("stripe_customer_id")
        return

    if "ux_subscriptions_stripe_sub_id" in _unique_constraint_names("subscriptions"):
        op.drop_constraint(
            "ux_subscriptions_stripe_sub_id",
            "subscriptions",
            type_="unique",
        )
    if drop_subscription:
        op.drop_column("subscriptions", "stripe_sub_id")
    if drop_customer:
        op.drop_column("subscriptions", "stripe_customer_id")


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = _column_names("subscriptions")
    add_customer = "stripe_customer_id" not in existing_columns
    add_subscription = "stripe_sub_id" not in existing_columns

    if bind.dialect.name == "sqlite":
        if add_customer or add_subscription:
            with op.batch_alter_table("subscriptions") as batch_op:
                if add_customer:
                    batch_op.add_column(
                        sa.Column(
                            "stripe_customer_id",
                            sa.String(length=64),
                            nullable=True,
                        )
                    )
                if add_subscription:
                    batch_op.add_column(
                        sa.Column(
                            "stripe_sub_id",
                            sa.String(length=64),
                            nullable=True,
                        )
                    )
                if (
                    "ux_subscriptions_stripe_sub_id"
                    not in _unique_constraint_names("subscriptions")
                ):
                    batch_op.create_unique_constraint(
                        "ux_subscriptions_stripe_sub_id",
                        ["stripe_sub_id"],
                    )
    else:
        if add_customer:
            op.add_column(
                "subscriptions",
                sa.Column("stripe_customer_id", sa.String(length=64), nullable=True),
            )
        if add_subscription:
            op.add_column(
                "subscriptions",
                sa.Column("stripe_sub_id", sa.String(length=64), nullable=True),
            )
        if "ux_subscriptions_stripe_sub_id" not in _unique_constraint_names(
            "subscriptions"
        ):
            op.create_unique_constraint(
                "ux_subscriptions_stripe_sub_id",
                "subscriptions",
                ["stripe_sub_id"],
            )

    if "ix_subscriptions_stripe_customer_id" not in _index_names("subscriptions"):
        op.create_index(
            "ix_subscriptions_stripe_customer_id",
            "subscriptions",
            ["stripe_customer_id"],
        )

    if not _has_table("stripe_events"):
        op.create_table(
            "stripe_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("stripe_event_id", sa.String(length=64), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("stripe_created_at", sa.DateTime(timezone=True), nullable=True),
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
                "stripe_event_id",
                name="ux_stripe_events_stripe_event_id",
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
