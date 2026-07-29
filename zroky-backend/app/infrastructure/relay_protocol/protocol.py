from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


RELAY_SCHEMA_VERSION = "zroky.customer_read_relay.v1"
BLOCKED_SELECTOR_KEYS = {"url", "base_url", "method", "headers", "body", "sql", "query", "password", "token", "secret"}


class RelayReadCommandRequest(BaseModel):
    environment: str = Field(default="production", min_length=1, max_length=64)
    source_binding: str = Field(min_length=1, max_length=255)
    connector_capability: str = Field(min_length=1, max_length=255)
    object_ref: str = Field(min_length=1, max_length=255)
    selector: dict[str, Any] = Field(default_factory=dict)
    max_freshness_seconds: int = Field(default=300, ge=1, le=86_400)
    ttl_seconds: int = Field(default=300, ge=1, le=3_600)

    @field_validator("environment")
    @classmethod
    def _clean_environment(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("selector")
    @classmethod
    def _reject_transport_and_secret_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        blocked = sorted(BLOCKED_SELECTOR_KEYS.intersection(k.lower() for k in value))
        if blocked:
            raise ValueError(f"selector cannot carry transport, query, or secret fields: {', '.join(blocked)}")
        return value


class RelayReadCommand(BaseModel):
    schema_version: str = RELAY_SCHEMA_VERSION
    command_id: str
    project_id: str
    environment: str
    operation: str = "read"
    source_binding: str
    connector_capability: str
    object_ref: str
    selector: dict[str, Any]
    max_freshness_seconds: int
    issued_at: datetime
    expires_at: datetime
    nonce: str
    command_digest: str


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def prepare_read_command(project_id: str, body: RelayReadCommandRequest) -> RelayReadCommand:
    issued_at = datetime.now(UTC)
    payload = {
        "schema_version": RELAY_SCHEMA_VERSION,
        "command_id": str(uuid4()),
        "project_id": project_id,
        "environment": body.environment,
        "operation": "read",
        "source_binding": body.source_binding,
        "connector_capability": body.connector_capability,
        "object_ref": body.object_ref,
        "selector": body.selector,
        "max_freshness_seconds": body.max_freshness_seconds,
        "issued_at": issued_at,
        "expires_at": issued_at + timedelta(seconds=body.ttl_seconds),
        "nonce": str(uuid4()),
    }
    payload["command_digest"] = _digest(payload)
    return RelayReadCommand(**payload)
