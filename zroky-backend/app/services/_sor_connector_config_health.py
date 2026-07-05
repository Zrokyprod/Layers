from __future__ import annotations

from app.services._sor_connector_config_core import *  # noqa: F403


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
            "has_oauth_refresh_token": False,
            "oauth_refresh_token_last4": None,
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
        "has_oauth_refresh_token": bool(row.oauth_refresh_token_ciphertext),
        "oauth_refresh_token_last4": row.oauth_refresh_token_last4,
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
