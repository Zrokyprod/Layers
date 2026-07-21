from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import create_engine

from app.infrastructure.relay_protocol import (
    GenericRestReadManifest,
    PostgresReadManifest,
    RelayReadCommandRequest,
    execute_manifest_bound_generic_rest_read,
    execute_manifest_bound_postgres_read,
    prepare_read_command,
)
from app.services.system_of_record_connectors import ConnectorConfigError


def test_generic_rest_read_is_manifest_bound_and_redacts_secret() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"id": "ord_1", "status": "paid"}})

    command = prepare_read_command(
        "proj_1",
        RelayReadCommandRequest(
            source_binding="orders_api",
            connector_capability="order.read",
            object_ref="ord_1",
            selector={"record_ref": "ord_1"},
        ),
    )
    source = execute_manifest_bound_generic_rest_read(
        command,
        GenericRestReadManifest(
            source_binding="orders_api",
            connector_capability="order.read",
            base_url="https://orders.example/api",
            path_template="/orders/{record_ref}",
            query={"include": "state"},
            record_path="data",
        ),
        bearer_token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    assert str(requests[0].url) == "https://orders.example/api/orders/ord_1?include=state"
    assert source.record == {"id": "ord_1", "status": "paid", "record_ref": "ord_1"}
    assert source.metadata is not None
    assert source.metadata["source_binding"] == "orders_api"
    assert source.metadata["connector_capability"] == "order.read"
    assert source.metadata["command_digest"] == command.command_digest
    assert "secret-token" not in json.dumps(source.metadata)


def test_generic_rest_read_rejects_command_manifest_mismatch() -> None:
    command = prepare_read_command(
        "proj_1",
        RelayReadCommandRequest(
            source_binding="orders_api",
            connector_capability="order.read",
            object_ref="ord_1",
        ),
    )

    with pytest.raises(ConnectorConfigError):
        execute_manifest_bound_generic_rest_read(
            command,
            GenericRestReadManifest(
                source_binding="other_api",
                connector_capability="order.read",
                base_url="https://orders.example/api",
                path_template="/orders/{record_ref}",
            ),
        )


def test_generic_rest_manifest_requires_record_ref_template() -> None:
    with pytest.raises(ValueError):
        GenericRestReadManifest(
            source_binding="orders_api",
            connector_capability="order.read",
            base_url="https://orders.example/api",
            path_template="/orders",
        )


def test_postgres_read_is_manifest_bound_and_read_only(tmp_path) -> None:
    source_db = tmp_path / "source.db"
    engine = create_engine(f"sqlite:///{source_db}", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE refunds (refund_id TEXT PRIMARY KEY, status TEXT)")
        connection.exec_driver_sql("INSERT INTO refunds (refund_id, status) VALUES (?, ?)", ("rf_1", "posted"))
    engine.dispose()

    command = prepare_read_command(
        "proj_1",
        RelayReadCommandRequest(
            source_binding="finance_db",
            connector_capability="refund.read",
            object_ref="refund:rf_1",
            selector={"refund_id": "rf_1"},
        ),
    )
    source = execute_manifest_bound_postgres_read(
        command,
        PostgresReadManifest(
            source_binding="finance_db",
            connector_capability="refund.read",
            database_url=f"sqlite:///{source_db}",
            query="SELECT refund_id, status FROM refunds WHERE refund_id = :refund_id",
        ),
        allow_sqlite_for_tests=True,
    )

    assert source.record == {"refund_id": "rf_1", "status": "posted"}
    assert source.metadata is not None
    assert source.metadata["read_only"] is True
    assert source.metadata["source_binding"] == "finance_db"
    assert source.metadata["command_digest"] == command.command_digest
    assert str(source_db) not in json.dumps(source.metadata)


def test_postgres_read_rejects_mutating_manifest_query() -> None:
    command = prepare_read_command(
        "proj_1",
        RelayReadCommandRequest(
            source_binding="finance_db",
            connector_capability="refund.read",
            object_ref="refund:rf_1",
            selector={"refund_id": "rf_1"},
        ),
    )

    with pytest.raises(ConnectorConfigError):
        execute_manifest_bound_postgres_read(
            command,
            PostgresReadManifest(
                source_binding="finance_db",
                connector_capability="refund.read",
                database_url="postgresql://readonly:secret@db.example.com/app",
                query="UPDATE refunds SET status = 'posted'",
            ),
        )
