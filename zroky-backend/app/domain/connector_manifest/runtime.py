from __future__ import annotations

from typing import Any

import httpx

from app.domain.connector_manifest.schema import ConnectorManifest
from app.infrastructure.relay_protocol import (
    GenericRestReadManifest,
    PostgresReadManifest,
    RelayReadCommand,
    execute_manifest_bound_generic_rest_read,
    execute_manifest_bound_postgres_read,
)
from app.services.outcome_reconciliation import SourceRecord
from app.services.system_of_record_connectors import ConnectorConfigError


def execute_connector_manifest_read(
    command: RelayReadCommand,
    manifest: ConnectorManifest,
    *,
    bearer_token: str | None = None,
    transport: httpx.BaseTransport | None = None,
    allow_sqlite_for_tests: bool = False,
) -> SourceRecord:
    if manifest.primitive == "generic_rest":
        return execute_manifest_bound_generic_rest_read(
            command,
            _generic_rest_manifest(manifest),
            bearer_token=bearer_token,
            transport=transport,
        )
    if manifest.primitive == "postgres_read":
        return execute_manifest_bound_postgres_read(
            command,
            _postgres_read_manifest(manifest),
            allow_sqlite_for_tests=allow_sqlite_for_tests,
        )
    raise ConnectorConfigError(f"connector primitive is not relay-readable: {manifest.primitive}")


def _generic_rest_manifest(manifest: ConnectorManifest) -> GenericRestReadManifest:
    return GenericRestReadManifest(
        source_binding=manifest.source_binding,
        connector_capability=manifest.connector_capability,
        base_url=_required(manifest.read.base_url, "generic_rest manifest requires read.base_url"),
        path_template=_required(manifest.read.path_template, "generic_rest manifest requires read.path_template"),
        query=manifest.read.query_params,
        record_path=manifest.read.record_path,
        timeout_seconds=manifest.read.timeout_seconds,
    )


def _postgres_read_manifest(manifest: ConnectorManifest) -> PostgresReadManifest:
    return PostgresReadManifest(
        source_binding=manifest.source_binding,
        connector_capability=manifest.connector_capability,
        database_url=_required(manifest.read.database_url, "postgres_read manifest requires read.database_url"),
        query=_required(manifest.read.query, "postgres_read manifest requires read.query"),
        fixed_params=manifest.read.fixed_params,
        timeout_seconds=manifest.read.timeout_seconds,
    )


def _required(value: Any | None, message: str) -> Any:
    if value is None:
        raise ConnectorConfigError(message)
    return value
