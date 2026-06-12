from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine


def _load_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0088_drop_legacy_stripe_billing_artifacts.py"
    )
    spec = importlib.util.spec_from_file_location(
        "billing_migration_0088",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _create_0087_billing_schema(connection) -> None:
    connection.exec_driver_sql(
        """
        CREATE TABLE subscriptions (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            org_id VARCHAR(64) NOT NULL,
            stripe_customer_id VARCHAR(64),
            stripe_sub_id VARCHAR(64),
            plan_code VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            seats INTEGER NOT NULL DEFAULT 1,
            current_period_end DATETIME,
            trial_end DATETIME,
            payment_provider VARCHAR(32) NOT NULL DEFAULT 'razorpay',
            payment_customer_ref VARCHAR(128),
            payment_subscription_ref VARCHAR(128),
            payment_request_ref VARCHAR(128),
            sla_tier VARCHAR(16) NOT NULL DEFAULT 'none',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ux_subscriptions_org UNIQUE (org_id),
            CONSTRAINT ux_subscriptions_stripe_sub_id UNIQUE (stripe_sub_id),
            CONSTRAINT ux_subscriptions_payment_subscription_ref
                UNIQUE (payment_subscription_ref)
        )
        """
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_subscriptions_stripe_customer_id "
        "ON subscriptions (stripe_customer_id)"
    )
    connection.exec_driver_sql(
        """
        CREATE TABLE stripe_events (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            stripe_event_id VARCHAR(64) NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            stripe_created_at DATETIME,
            received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME,
            result VARCHAR(16) NOT NULL DEFAULT 'pending',
            error_message TEXT,
            affected_org_id VARCHAR(64),
            payload_json TEXT NOT NULL,
            CONSTRAINT ux_stripe_events_stripe_event_id UNIQUE (stripe_event_id)
        )
        """
    )


def _schema_state(db_path: Path) -> tuple[bool, set[str], set[str]]:
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(subscriptions)").fetchall()
        }
        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(subscriptions)").fetchall()
        }
        return "stripe_events" in tables, columns, indexes
    finally:
        conn.close()


def test_0088_sqlite_upgrade_and_downgrade_stripe_artifacts(tmp_path: Path) -> None:
    db_path = tmp_path / "billing_migration_0088.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    migration = _load_migration()

    with engine.begin() as connection:
        _create_0087_billing_schema(connection)
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = migration.op
        migration.op = operations
        try:
            migration.upgrade()
        finally:
            migration.op = original_op

    has_stripe_events, columns, indexes = _schema_state(db_path)
    assert has_stripe_events is False
    assert "stripe_customer_id" not in columns
    assert "stripe_sub_id" not in columns
    assert "ix_subscriptions_stripe_customer_id" not in indexes

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = migration.op
        migration.op = operations
        try:
            migration.downgrade()
        finally:
            migration.op = original_op

    has_stripe_events, columns, indexes = _schema_state(db_path)
    assert has_stripe_events is True
    assert {"stripe_customer_id", "stripe_sub_id"} <= columns
    assert "ix_subscriptions_stripe_customer_id" in indexes

    engine.dispose()
