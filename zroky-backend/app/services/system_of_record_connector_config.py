"""Tenant-scoped system-of-record connector configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import OutcomeReconciliationCheck, SystemOfRecordConnectorConfig
from app.services.provider_key_cipher import (
    EnvelopeFormatError,
    VaultCipherUnavailable,
    decrypt_provider_key,
    encrypt_provider_key,
)
from app.services.system_of_record_connectors import (
    ConnectorConfigError,
    CustomerRecordApiConnector,
    LedgerRefundApiConnector,
    validate_customer_record_api_config,
    validate_ledger_refund_api_config,
)

CUSTOMER_RECORD_CONNECTOR_TYPE = "customer_record_api"
LEDGER_REFUND_CONNECTOR_TYPE = "ledger_refund_api"
VALID_CONNECTOR_TYPES = frozenset(
    {CUSTOMER_RECORD_CONNECTOR_TYPE, LEDGER_REFUND_CONNECTOR_TYPE}
)


class InvalidSystemOfRecordConnectorError(ValueError):
    """Raised when a connector config is invalid or unsupported."""


def _json_dumps(value: Any) -> str | None:
    if value in (None, {}, []):
        return None
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        loaded = json.loads(value)
    except Exception:
        return None
    return dict(loaded) if isinstance(loaded, Mapping) else None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_connector_type(connector_type: str) -> str:
    normalized = connector_type.strip().lower()
    if normalized not in VALID_CONNECTOR_TYPES:
        raise InvalidSystemOfRecordConnectorError(
            "connector_type must be one of: " + ", ".join(sorted(VALID_CONNECTOR_TYPES))
        )
    return normalized


def _normalize_query(
    query: Mapping[str, Any] | None,
) -> dict[str, str | int | float | bool] | None:
    if not query:
        return None
    normalized: dict[str, str | int | float | bool] = {}
    for raw_key, value in query.items():
        key = str(raw_key).strip()
        if not key or value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            normalized[key] = value
            continue
        raise InvalidSystemOfRecordConnectorError(
            "connector query values must be strings, numbers, or booleans"
        )
    return normalized or None


def get_connector_config(
    db: Session,
    *,
    project_id: str,
    connector_type: str = LEDGER_REFUND_CONNECTOR_TYPE,
) -> SystemOfRecordConnectorConfig | None:
    connector_type = _normalize_connector_type(connector_type)
    return db.execute(
        select(SystemOfRecordConnectorConfig).where(
            SystemOfRecordConnectorConfig.project_id == project_id,
            SystemOfRecordConnectorConfig.connector_type == connector_type,
        )
    ).scalar_one_or_none()


def upsert_ledger_refund_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str,
    path_template: str = "/refunds/{refund_id}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
    allow_private_hosts: bool = False,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_ledger_refund_api_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
            allow_private_hosts=allow_private_hosts,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = _normalize_query(query)
    row = get_connector_config(db, project_id=project_id)
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=LEDGER_REFUND_CONNECTOR_TYPE,
            created_by_subject=updated_by_subject,
            created_at=now,
        )

    row.base_url = str(normalized["base_url"])
    row.path_template = str(normalized["path_template"])
    row.record_path = normalized["record_path"]
    row.query_json = _json_dumps(normalized_query)
    row.updated_by_subject = updated_by_subject
    row.updated_at = now
    row.is_active = True

    if clear_bearer_token:
        row.bearer_token_ciphertext = None
        row.bearer_token_fingerprint = None
        row.bearer_token_last4 = None
        row.kms_key_id = None
    elif bearer_token is not None:
        cleaned = bearer_token.strip()
        if not cleaned:
            raise InvalidSystemOfRecordConnectorError(
                "bearer_token must not be empty when provided"
            )
        bundle = encrypt_provider_key(plaintext=cleaned, project_id=project_id)
        row.bearer_token_ciphertext = bundle.ciphertext
        row.bearer_token_fingerprint = bundle.key_fingerprint
        row.bearer_token_last4 = bundle.key_last4
        row.kms_key_id = bundle.kms_key_id

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def upsert_customer_record_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str,
    path_template: str = "/customers/{customer_id}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
    allow_private_hosts: bool = False,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_customer_record_api_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
            allow_private_hosts=allow_private_hosts,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = _normalize_query(query)
    row = get_connector_config(
        db, project_id=project_id, connector_type=CUSTOMER_RECORD_CONNECTOR_TYPE
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=CUSTOMER_RECORD_CONNECTOR_TYPE,
            created_by_subject=updated_by_subject,
            created_at=now,
        )

    row.base_url = str(normalized["base_url"])
    row.path_template = str(normalized["path_template"])
    row.record_path = normalized["record_path"]
    row.query_json = _json_dumps(normalized_query)
    row.updated_by_subject = updated_by_subject
    row.updated_at = now
    row.is_active = True

    if clear_bearer_token:
        row.bearer_token_ciphertext = None
        row.bearer_token_fingerprint = None
        row.bearer_token_last4 = None
        row.kms_key_id = None
    elif bearer_token is not None:
        cleaned = bearer_token.strip()
        if not cleaned:
            raise InvalidSystemOfRecordConnectorError(
                "bearer_token must not be empty when provided"
            )
        bundle = encrypt_provider_key(plaintext=cleaned, project_id=project_id)
        row.bearer_token_ciphertext = bundle.ciphertext
        row.bearer_token_fingerprint = bundle.key_fingerprint
        row.bearer_token_last4 = bundle.key_last4
        row.kms_key_id = bundle.kms_key_id

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def decrypt_connector_bearer_token(
    row: SystemOfRecordConnectorConfig,
    *,
    project_id: str,
) -> str | None:
    if not row.bearer_token_ciphertext:
        return None
    return decrypt_provider_key(
        ciphertext=row.bearer_token_ciphertext,
        project_id=project_id,
    )


def build_ledger_refund_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    refund_id: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
    allow_private_hosts: bool,
) -> LedgerRefundApiConnector:
    return LedgerRefundApiConnector(
        base_url=row.base_url,
        refund_id=refund_id,
        bearer_token=bearer_token,
        path_template=row.path_template or "/refunds/{refund_id}",
        query=_json_loads(row.query_json),
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        allow_private_hosts=allow_private_hosts,
    )


def build_customer_record_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    customer_id: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
    allow_private_hosts: bool,
) -> CustomerRecordApiConnector:
    return CustomerRecordApiConnector(
        base_url=row.base_url,
        customer_id=customer_id,
        bearer_token=bearer_token,
        path_template=row.path_template or "/customers/{customer_id}",
        query=_json_loads(row.query_json),
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        allow_private_hosts=allow_private_hosts,
    )


def mark_connector_tested(
    db: Session,
    row: SystemOfRecordConnectorConfig,
    *,
    tested_at: datetime,
) -> SystemOfRecordConnectorConfig:
    row.last_tested_at = tested_at
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _health_from_latest_check(
    row: OutcomeReconciliationCheck | None,
) -> dict[str, Any]:
    if row is None:
        return {
            "health_status": "not_verified",
            "last_verdict": None,
            "last_error": None,
            "last_http_status": None,
            "last_attempts": None,
            "last_checked_at": None,
        }

    metadata = _json_loads(row.metadata_json)
    connector_metadata = {}
    if metadata and isinstance(metadata.get("connector"), Mapping):
        connector_metadata = dict(metadata["connector"])

    if row.verdict == "matched":
        health_status = "healthy"
    elif row.verdict == "mismatched":
        health_status = "failing"
    else:
        health_status = "degraded"

    return {
        "health_status": health_status,
        "last_verdict": row.verdict,
        "last_error": connector_metadata.get("error"),
        "last_http_status": _as_int(connector_metadata.get("http_status")),
        "last_attempts": _as_int(connector_metadata.get("attempts")),
        "last_checked_at": row.checked_at,
    }


def get_connector_health_snapshot(
    db: Session,
    *,
    project_id: str,
    connector_type: str = LEDGER_REFUND_CONNECTOR_TYPE,
) -> dict[str, Any]:
    connector_type = _normalize_connector_type(connector_type)
    latest = db.execute(
        select(OutcomeReconciliationCheck)
        .where(
            OutcomeReconciliationCheck.project_id == project_id,
            OutcomeReconciliationCheck.connector_type == connector_type,
        )
        .order_by(
            desc(OutcomeReconciliationCheck.checked_at),
            desc(OutcomeReconciliationCheck.id),
        )
        .limit(1)
    ).scalar_one_or_none()
    return _health_from_latest_check(latest)


def serialize_connector_config(
    row: SystemOfRecordConnectorConfig | None,
    *,
    connector_type: str = LEDGER_REFUND_CONNECTOR_TYPE,
    health: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    connector_type = _normalize_connector_type(connector_type)
    health_payload = dict(health or {})
    if row is None:
        return {
            "connected": False,
            "connector_type": connector_type,
            "base_url": None,
            "path_template": None,
            "record_path": None,
            "query": None,
            "has_bearer_token": False,
            "bearer_token_last4": None,
            "last_tested_at": None,
            "created_at": None,
            "updated_at": None,
            "health_status": "not_configured",
            "last_verdict": None,
            "last_error": None,
            "last_http_status": None,
            "last_attempts": None,
            "last_checked_at": None,
        }
    return {
        "connected": bool(row.is_active),
        "connector_type": row.connector_type,
        "base_url": row.base_url,
        "path_template": row.path_template,
        "record_path": row.record_path,
        "query": _json_loads(row.query_json),
        "has_bearer_token": bool(row.bearer_token_ciphertext),
        "bearer_token_last4": row.bearer_token_last4,
        "last_tested_at": row.last_tested_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "health_status": health_payload.get("health_status") or "not_verified",
        "last_verdict": health_payload.get("last_verdict"),
        "last_error": health_payload.get("last_error"),
        "last_http_status": health_payload.get("last_http_status"),
        "last_attempts": health_payload.get("last_attempts"),
        "last_checked_at": health_payload.get("last_checked_at"),
    }


__all__ = [
    "CUSTOMER_RECORD_CONNECTOR_TYPE",
    "EnvelopeFormatError",
    "InvalidSystemOfRecordConnectorError",
    "LEDGER_REFUND_CONNECTOR_TYPE",
    "VaultCipherUnavailable",
    "build_customer_record_connector",
    "build_ledger_refund_connector",
    "decrypt_connector_bearer_token",
    "get_connector_config",
    "get_connector_health_snapshot",
    "mark_connector_tested",
    "serialize_connector_config",
    "upsert_customer_record_connector_config",
    "upsert_ledger_refund_connector_config",
]
