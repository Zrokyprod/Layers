from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine


def _load_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0125_canonicalize_private_runner_refs.py"
    )
    spec = importlib.util.spec_from_file_location(
        "connector_credential_migration_0125", migration_path
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_0125_canonicalizes_only_private_runner_refs(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'connector_credentials.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    migration = _load_migration()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE connector_credentials (
                id VARCHAR(36) PRIMARY KEY,
                custody_mode VARCHAR(32) NOT NULL,
                secret_ref VARCHAR(512)
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO connector_credentials (id, custody_mode, secret_ref)
            VALUES
                ('private', 'private_runner', 'runner://payments/stripe'),
                ('vault', 'customer_managed', 'vault://payments/stripe'),
                ('managed', 'zroky_managed', NULL)
            """
        )
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = migration.op
        migration.op = operations
        try:
            migration.upgrade()
        finally:
            migration.op = original_op

        rows = dict(
            connection.exec_driver_sql(
                "SELECT id, secret_ref FROM connector_credentials"
            ).all()
        )
        assert rows["private"] == "customer-runner-secret://payments/stripe"
        assert rows["vault"] == "vault://payments/stripe"
        assert rows["managed"] is None

        migration.op = operations
        try:
            migration.downgrade()
        finally:
            migration.op = original_op
        rows = dict(
            connection.exec_driver_sql(
                "SELECT id, secret_ref FROM connector_credentials"
            ).all()
        )
        assert rows["private"] == "runner://payments/stripe"

    engine.dispose()
