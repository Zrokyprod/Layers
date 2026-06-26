"""Tenant-scoped system-of-record connector configuration."""

from __future__ import annotations

import json
import hashlib
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
from app.services.protected_action_billing import enforce_system_of_record_connector_limit
from app.services.system_of_record_connectors import (
    ConnectorConfigError,
    CustomerRecordApiConnector,
    GenericRestApiConnector,
    LedgerRefundApiConnector,
    PostgresReadOnlyConnector,
    validate_customer_record_api_config,
    validate_generic_rest_api_config,
    validate_ledger_refund_api_config,
    validate_postgres_read_config,
)

CUSTOMER_RECORD_CONNECTOR_TYPE = "customer_record_api"
GENERIC_REST_CONNECTOR_TYPE = "generic_rest_api"
LEDGER_REFUND_CONNECTOR_TYPE = "ledger_refund_api"
POSTGRES_READ_CONNECTOR_TYPE = "postgres_read"
VALID_CONNECTOR_TYPES = frozenset(
    {
        CUSTOMER_RECORD_CONNECTOR_TYPE,
        GENERIC_REST_CONNECTOR_TYPE,
        LEDGER_REFUND_CONNECTOR_TYPE,
        POSTGRES_READ_CONNECTOR_TYPE,
    }
)

_CONNECTOR_CONTRACTS: dict[str, dict[str, Any]] = {
    LEDGER_REFUND_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": LEDGER_REFUND_CONNECTOR_TYPE,
        "adapter": "https_json_record",
        "system_of_record": "ledger_refund",
        "config_endpoint": "/v1/integrations/system-of-record/ledger-refund/config",
        "status_endpoint": "/v1/integrations/system-of-record/ledger-refund/status",
        "test_endpoint": "/v1/integrations/system-of-record/ledger-refund/test",
        "required_inputs": [
            "https_base_url",
            "path_template_with_refund_id",
            "read_scoped_bearer_token",
            "safe_existing_refund_id",
        ],
        "required_record_fields": ["refund_id", "status"],
        "recommended_record_fields": ["amount_usd", "currency"],
        "pass_rule": (
            "A saved connector test must fetch one refund record from the "
            "system of record and reconcile it as matched."
        ),
    },
    CUSTOMER_RECORD_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": CUSTOMER_RECORD_CONNECTOR_TYPE,
        "adapter": "https_json_record",
        "system_of_record": "customer_record",
        "config_endpoint": "/v1/integrations/system-of-record/customer-record/config",
        "status_endpoint": "/v1/integrations/system-of-record/customer-record/status",
        "test_endpoint": "/v1/integrations/system-of-record/customer-record/test",
        "required_inputs": [
            "https_base_url",
            "path_template_with_customer_id",
            "read_scoped_bearer_token",
            "safe_existing_customer_id",
        ],
        "required_record_fields": ["customer_id", "status"],
        "recommended_record_fields": ["email", "account_id"],
        "pass_rule": (
            "A saved connector test must fetch one customer record from the "
            "system of record and reconcile it as matched."
        ),
    },
    GENERIC_REST_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": GENERIC_REST_CONNECTOR_TYPE,
        "adapter": "https_json_record",
        "system_of_record": "generic_rest",
        "config_endpoint": "/v1/integrations/system-of-record/generic-rest/config",
        "status_endpoint": "/v1/integrations/system-of-record/generic-rest/status",
        "test_endpoint": "/v1/integrations/system-of-record/generic-rest/test",
        "required_inputs": [
            "https_base_url",
            "path_template_with_record_ref",
            "read_scoped_bearer_token",
            "safe_existing_record_ref",
        ],
        "required_record_fields": ["record_ref"],
        "recommended_record_fields": ["status", "updated_at"],
        "pass_rule": (
            "A saved connector test must fetch one JSON record from the "
            "customer system and reconcile the configured match fields as matched."
        ),
    },
    POSTGRES_READ_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": POSTGRES_READ_CONNECTOR_TYPE,
        "adapter": "postgresql_readonly",
        "system_of_record": "postgres_read",
        "config_endpoint": "/v1/integrations/system-of-record/postgres-read/config",
        "status_endpoint": "/v1/integrations/system-of-record/postgres-read/status",
        "test_endpoint": "/v1/integrations/system-of-record/postgres-read/test",
        "required_inputs": [
            "postgres_database_url",
            "single_read_only_select_query",
            "safe_existing_query_params",
        ],
        "required_record_fields": [],
        "recommended_record_fields": ["id", "status", "updated_at"],
        "pass_rule": (
            "A saved connector test must execute one read-only query against "
            "PostgreSQL and reconcile the configured match fields as matched."
        ),
    },
}


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


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _connector_contract(connector_type: str) -> dict[str, Any]:
    connector_type = _normalize_connector_type(connector_type)
    return json.loads(json.dumps(_CONNECTOR_CONTRACTS[connector_type]))


def _connector_readiness(
    row: SystemOfRecordConnectorConfig | None,
    *,
    connector_type: str,
    health: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    connector_type = _normalize_connector_type(connector_type)
    health_payload = dict(health or {})
    last_http_status = _as_int(health_payload.get("last_http_status"))
    last_attempts = _as_int(health_payload.get("last_attempts"))
    last_error_code = health_payload.get("last_error_code")
    last_retryable = _as_bool(health_payload.get("last_retryable"))
    if connector_type == POSTGRES_READ_CONNECTOR_TYPE:
        checks = {
            "config_saved": row is not None and bool(row.is_active),
            "database_url_present": row is not None
            and bool(row.database_url_ciphertext),
            "read_query_present": row is not None and bool(row.read_query),
            "saved_test_matched": health_payload.get("last_verdict") == "matched",
            "connector_attempted": last_attempts is not None and last_attempts >= 1,
            "no_connector_error_code": last_error_code in (None, ""),
            "not_retryable_failure": last_retryable in (None, False),
        }
        blocker_messages = {
            "config_saved": "connector config has not been saved",
            "database_url_present": "encrypted PostgreSQL database URL is missing",
            "read_query_present": "read-only verification query is missing",
            "saved_test_matched": "latest connector test did not reconcile as matched",
            "connector_attempted": "connector has not attempted a system-of-record read",
            "no_connector_error_code": "latest connector test has an error code",
            "not_retryable_failure": "latest connector test ended in a retryable failure",
        }
    else:
        checks = {
            "config_saved": row is not None and bool(row.is_active),
            "bearer_token_present": row is not None
            and bool(row.bearer_token_ciphertext),
            "saved_test_matched": health_payload.get("last_verdict") == "matched",
            "connector_attempted": last_attempts is not None and last_attempts >= 1,
            "http_2xx": last_http_status is not None
            and 200 <= last_http_status <= 299,
            "no_connector_error_code": last_error_code in (None, ""),
            "not_retryable_failure": last_retryable in (None, False),
        }
        blocker_messages = {
            "config_saved": "connector config has not been saved",
            "bearer_token_present": "read-scoped bearer token is missing",
            "saved_test_matched": "latest connector test did not reconcile as matched",
            "connector_attempted": "connector has not attempted a system-of-record read",
            "http_2xx": "latest connector test did not return a 2xx HTTP response",
            "no_connector_error_code": "latest connector test has an error code",
            "not_retryable_failure": "latest connector test ended in a retryable failure",
        }
    blockers = [
        blocker_messages[key]
        for key, passed in checks.items()
        if not passed
    ]
    return {
        "status": "ready" if not blockers else "not_ready",
        "contract": _connector_contract(connector_type),
        "checks": checks,
        "blockers": blockers,
        "last_checked_at": health_payload.get("last_checked_at"),
    }


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
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=LEDGER_REFUND_CONNECTOR_TYPE,
    )
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
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=CUSTOMER_RECORD_CONNECTOR_TYPE,
    )
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


def upsert_generic_rest_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str,
    path_template: str = "/records/{record_ref}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
    allow_private_hosts: bool = False,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_generic_rest_api_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
            allow_private_hosts=allow_private_hosts,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = _normalize_query(query)
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=GENERIC_REST_CONNECTOR_TYPE,
    )
    row = get_connector_config(
        db, project_id=project_id, connector_type=GENERIC_REST_CONNECTOR_TYPE
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=GENERIC_REST_CONNECTOR_TYPE,
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


def upsert_postgres_read_connector_config(
    db: Session,
    *,
    project_id: str,
    database_url: str | None = None,
    read_query: str,
    clear_database_url: bool = False,
    updated_by_subject: str | None = None,
    allow_private_hosts: bool = False,
) -> SystemOfRecordConnectorConfig:
    row = get_connector_config(
        db, project_id=project_id, connector_type=POSTGRES_READ_CONNECTOR_TYPE
    )
    if row is None and not database_url:
        raise InvalidSystemOfRecordConnectorError("database_url is required")
    if clear_database_url:
        raise InvalidSystemOfRecordConnectorError(
            "database_url cannot be cleared for an active PostgreSQL connector"
        )

    normalized_query: str
    public_database_url = row.base_url if row is not None else None
    normalized_database_url: str | None = None
    if database_url is not None:
        try:
            normalized = validate_postgres_read_config(
                database_url=database_url,
                read_query=read_query,
                allow_private_hosts=allow_private_hosts,
            )
        except ConnectorConfigError as exc:
            raise InvalidSystemOfRecordConnectorError(str(exc)) from exc
        normalized_database_url = normalized["database_url"]
        public_database_url = normalized["public_database_url"]
        normalized_query = normalized["read_query"]
    else:
        try:
            normalized = validate_postgres_read_config(
                database_url="postgresql://placeholder.example.com/placeholder",
                read_query=read_query,
                allow_private_hosts=True,
            )
        except ConnectorConfigError as exc:
            raise InvalidSystemOfRecordConnectorError(str(exc)) from exc
        normalized_query = normalized["read_query"]

    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=POSTGRES_READ_CONNECTOR_TYPE,
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=POSTGRES_READ_CONNECTOR_TYPE,
            created_by_subject=updated_by_subject,
            created_at=now,
        )

    row.base_url = public_database_url or "postgresql://source-record"
    row.path_template = "/"
    row.record_path = None
    row.query_json = None
    row.read_query = normalized_query
    row.updated_by_subject = updated_by_subject
    row.updated_at = now
    row.is_active = True

    if normalized_database_url is not None:
        bundle = encrypt_provider_key(
            plaintext=normalized_database_url,
            project_id=project_id,
        )
        row.database_url_ciphertext = bundle.ciphertext
        row.database_url_fingerprint = bundle.key_fingerprint
        row.database_url_last4 = bundle.key_last4
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


def decrypt_connector_database_url(
    row: SystemOfRecordConnectorConfig,
    *,
    project_id: str,
) -> str | None:
    if not row.database_url_ciphertext:
        return None
    return decrypt_provider_key(
        ciphertext=row.database_url_ciphertext,
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
        fail_closed_config_errors=True,
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
        fail_closed_config_errors=True,
    )


def build_generic_rest_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    record_ref: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
    allow_private_hosts: bool,
) -> GenericRestApiConnector:
    return GenericRestApiConnector(
        base_url=row.base_url,
        record_ref=record_ref,
        bearer_token=bearer_token,
        path_template=row.path_template or "/records/{record_ref}",
        query=_json_loads(row.query_json),
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        allow_private_hosts=allow_private_hosts,
        fail_closed_config_errors=True,
    )


def build_postgres_read_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    database_url: str,
    params: Mapping[str, Any] | None,
    timeout_seconds: float,
    allow_private_hosts: bool,
) -> PostgresReadOnlyConnector:
    return PostgresReadOnlyConnector(
        database_url=database_url,
        query=row.read_query or "",
        params=params,
        timeout_seconds=timeout_seconds,
        allow_private_hosts=allow_private_hosts,
        fail_closed_config_errors=True,
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
    error_code = (
        str(connector_metadata.get("error_code")).strip()
        if connector_metadata.get("error_code") is not None
        else None
    )
    retryable = _as_bool(connector_metadata.get("retryable"))

    if row.verdict == "matched":
        health_status = "healthy"
    elif row.verdict == "mismatched":
        health_status = "failing"
    elif error_code == "auth_failed":
        health_status = "auth_failed"
    elif retryable:
        health_status = "degraded"
    else:
        health_status = "not_verified"

    return {
        "health_status": health_status,
        "last_verdict": row.verdict,
        "last_error": connector_metadata.get("error"),
        "last_error_code": error_code,
        "last_http_status": _as_int(connector_metadata.get("http_status")),
        "last_attempts": _as_int(connector_metadata.get("attempts")),
        "last_retryable": retryable,
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
    readiness = _connector_readiness(
        row,
        connector_type=connector_type,
        health=health_payload,
    )
    if row is None:
        return {
            "connected": False,
            "connector_type": connector_type,
            "base_url": None,
            "path_template": None,
            "record_path": None,
            "query": None,
            "has_database_url": False,
            "database_url_last4": None,
            "has_read_query": False,
            "read_query_digest": None,
            "has_bearer_token": False,
            "bearer_token_last4": None,
            "last_tested_at": None,
            "created_at": None,
            "updated_at": None,
            "health_status": "not_configured",
            "last_verdict": None,
            "last_error": None,
            "last_error_code": None,
            "last_http_status": None,
            "last_attempts": None,
            "last_retryable": None,
            "last_checked_at": None,
            "readiness": readiness,
        }
    read_query = row.read_query or None
    return {
        "connected": bool(row.is_active),
        "connector_type": row.connector_type,
        "base_url": row.base_url,
        "path_template": row.path_template,
        "record_path": row.record_path,
        "query": _json_loads(row.query_json),
        "has_database_url": bool(row.database_url_ciphertext),
        "database_url_last4": row.database_url_last4,
        "has_read_query": bool(read_query),
        "read_query_digest": hashlib.sha256(read_query.encode("utf-8")).hexdigest()
        if read_query
        else None,
        "has_bearer_token": bool(row.bearer_token_ciphertext),
        "bearer_token_last4": row.bearer_token_last4,
        "last_tested_at": row.last_tested_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "health_status": health_payload.get("health_status") or "not_verified",
        "last_verdict": health_payload.get("last_verdict"),
        "last_error": health_payload.get("last_error"),
        "last_error_code": health_payload.get("last_error_code"),
        "last_http_status": health_payload.get("last_http_status"),
        "last_attempts": health_payload.get("last_attempts"),
        "last_retryable": health_payload.get("last_retryable"),
        "last_checked_at": health_payload.get("last_checked_at"),
        "readiness": readiness,
    }


__all__ = [
    "CUSTOMER_RECORD_CONNECTOR_TYPE",
    "EnvelopeFormatError",
    "GENERIC_REST_CONNECTOR_TYPE",
    "InvalidSystemOfRecordConnectorError",
    "LEDGER_REFUND_CONNECTOR_TYPE",
    "POSTGRES_READ_CONNECTOR_TYPE",
    "VaultCipherUnavailable",
    "build_customer_record_connector",
    "build_generic_rest_connector",
    "build_ledger_refund_connector",
    "build_postgres_read_connector",
    "decrypt_connector_bearer_token",
    "decrypt_connector_database_url",
    "get_connector_config",
    "get_connector_health_snapshot",
    "mark_connector_tested",
    "serialize_connector_config",
    "upsert_customer_record_connector_config",
    "upsert_generic_rest_connector_config",
    "upsert_ledger_refund_connector_config",
    "upsert_postgres_read_connector_config",
]
