from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CONNECTOR_MANIFEST_SCHEMA_VERSION = "zroky.connector_manifest.v1"
READ_ONLY_HTTP_METHODS = {"GET", "HEAD"}
RAW_SECRET_KEYS = {"api_key", "apikey", "authorization", "bearer", "client_secret", "password", "secret", "token"}
WRITE_SCOPE_RE = re.compile(r"(^|[.:/_-])(write|admin|manage|delete|create|update|modify|full)([.:/_-]|$)", re.I)
MUTATING_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|merge|grant|revoke|call|execute|copy|vacuum|analyze)\b",
    re.I,
)


ConnectorPrimitive = Literal["generic_rest", "webhook_callback", "postgres_read"]
ConnectorAuthType = Literal["none", "api_key", "bearer", "basic", "oauth", "hmac"]


class ConnectorAuthManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ConnectorAuthType
    credential_ref: str | None = Field(default=None, min_length=1, max_length=512)
    allowed_scopes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("allowed_scopes")
    @classmethod
    def _read_only_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        write_scopes = [scope for scope in value if WRITE_SCOPE_RE.search(scope)]
        if write_scopes:
            raise ValueError(f"connector scopes must be read-only: {', '.join(write_scopes)}")
        return value


class ConnectorTestReadManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_ref: str = Field(min_length=1, max_length=255)
    expected_found: bool = True


class ConnectorReadManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str = "GET"
    path_template: str | None = Field(default=None, min_length=1)
    query: str | None = Field(default=None, min_length=1)
    callback_schema: dict[str, Any] | None = None

    @field_validator("method")
    @classmethod
    def _read_only_method(cls, value: str) -> str:
        method = value.upper()
        if method not in READ_ONLY_HTTP_METHODS:
            raise ValueError(f"connector read method must be read-only: {method}")
        return method

    @field_validator("query")
    @classmethod
    def _read_only_query(cls, value: str | None) -> str | None:
        if value is not None and MUTATING_SQL_RE.search(value):
            raise ValueError("connector SQL query must be read-only")
        return value


class ConnectorCorrelationRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_field: str = Field(min_length=1, max_length=255)
    source_field: str = Field(min_length=1, max_length=255)


class ConnectorFreshnessRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_age_seconds: int = Field(default=300, ge=1, le=86_400)


class ConnectorManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = CONNECTOR_MANIFEST_SCHEMA_VERSION
    manifest_id: str = Field(min_length=1, max_length=255)
    connector_id: str = Field(min_length=1, max_length=255)
    primitive: ConnectorPrimitive
    source_binding: str = Field(min_length=1, max_length=255)
    connector_capability: str = Field(min_length=1, max_length=255)
    auth: ConnectorAuthManifest
    read: ConnectorReadManifest
    test_read: ConnectorTestReadManifest
    object_schema: dict[str, Any] = Field(min_length=1)
    correlation: ConnectorCorrelationRule
    freshness: ConnectorFreshnessRule = Field(default_factory=ConnectorFreshnessRule)
    expected_effect_mapping: dict[str, str] = Field(min_length=1)
    evidence_template_id: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def _validate_manifest(self) -> "ConnectorManifest":
        _reject_raw_secret_fields(self.model_dump())
        if self.primitive == "postgres_read" and not self.read.query:
            raise ValueError("postgres_read manifest requires read.query")
        if self.primitive == "generic_rest" and not self.read.path_template:
            raise ValueError("generic_rest manifest requires read.path_template")
        if self.primitive == "webhook_callback" and not self.read.callback_schema:
            raise ValueError("webhook_callback manifest requires read.callback_schema")
        return self


def validate_connector_manifest(payload: dict[str, Any]) -> ConnectorManifest:
    _reject_raw_secret_fields(payload)
    return ConnectorManifest.model_validate(payload)


def _reject_raw_secret_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in RAW_SECRET_KEYS:
                raise ValueError(f"connector manifest cannot contain raw secret field: {key}")
            _reject_raw_secret_fields(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_raw_secret_fields(child)
