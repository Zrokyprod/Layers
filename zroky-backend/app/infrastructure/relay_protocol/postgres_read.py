from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.infrastructure.relay_protocol import RelayReadCommand
from app.services.outcome_reconciliation import SourceRecord
from app.services.system_of_record_connectors import ConnectorConfigError, PostgresReadOnlyConnector


class PostgresReadManifest(BaseModel):
    source_binding: str = Field(min_length=1, max_length=255)
    connector_capability: str = Field(min_length=1, max_length=255)
    database_url: str = Field(min_length=1)
    query: str = Field(min_length=1)
    fixed_params: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)


def execute_manifest_bound_postgres_read(
    command: RelayReadCommand,
    manifest: PostgresReadManifest,
    *,
    allow_sqlite_for_tests: bool = False,
) -> SourceRecord:
    if command.operation != "read":
        raise ConnectorConfigError("postgres relay command must be read-only")
    if command.source_binding != manifest.source_binding:
        raise ConnectorConfigError("postgres relay command source_binding does not match manifest")
    if command.connector_capability != manifest.connector_capability:
        raise ConnectorConfigError("postgres relay command connector_capability does not match manifest")

    source = PostgresReadOnlyConnector(
        database_url=manifest.database_url,
        query=manifest.query,
        params={**manifest.fixed_params, **command.selector},
        timeout_seconds=manifest.timeout_seconds,
        allow_sqlite_for_tests=allow_sqlite_for_tests,
    ).fetch()
    return SourceRecord(
        record=source.record,
        record_found=source.record_found,
        metadata={
            **(source.metadata or {}),
            "relay_schema_version": command.schema_version,
            "command_digest": command.command_digest,
            "source_binding": command.source_binding,
            "connector_capability": command.connector_capability,
        },
    )
