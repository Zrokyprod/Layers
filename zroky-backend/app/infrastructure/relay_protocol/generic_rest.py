from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field, field_validator

from app.infrastructure.relay_protocol import RelayReadCommand
from app.services.outcome_reconciliation import SourceRecord
from app.services.system_of_record_connectors import ConnectorConfigError, GenericRestApiConnector


class GenericRestReadManifest(BaseModel):
    source_binding: str = Field(min_length=1, max_length=255)
    connector_capability: str = Field(min_length=1, max_length=255)
    base_url: str = Field(min_length=1)
    path_template: str = Field(default="/records/{record_ref}", min_length=1)
    path_value_keys: tuple[str, ...] = Field(default_factory=tuple)
    query: dict[str, Any] = Field(default_factory=dict)
    record_path: str | None = None
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    max_attempts: int = Field(default=2, ge=1, le=4)

    @field_validator("path_template")
    @classmethod
    def _must_use_record_ref(cls, value: str) -> str:
        if "{record_ref}" not in value:
            raise ValueError("generic REST path_template must use {record_ref}")
        return value


def execute_manifest_bound_generic_rest_read(
    command: RelayReadCommand,
    manifest: GenericRestReadManifest,
    *,
    bearer_token: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> SourceRecord:
    if command.operation != "read":
        raise ConnectorConfigError("generic REST relay command must be read-only")
    if command.source_binding != manifest.source_binding:
        raise ConnectorConfigError("generic REST relay command source_binding does not match manifest")
    if command.connector_capability != manifest.connector_capability:
        raise ConnectorConfigError("generic REST relay command connector_capability does not match manifest")

    record_ref = str(command.selector.get("record_ref") or command.object_ref).strip()
    if not record_ref:
        raise ConnectorConfigError("generic REST relay command requires a record_ref or object_ref")

    source = GenericRestApiConnector(
        base_url=manifest.base_url,
        record_ref=record_ref,
        bearer_token=bearer_token,
        path_template=manifest.path_template,
        path_values={key: command.selector[key] for key in manifest.path_value_keys if key in command.selector},
        query=manifest.query,
        record_path=manifest.record_path,
        timeout_seconds=manifest.timeout_seconds,
        max_attempts=manifest.max_attempts,
        transport=transport,
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
