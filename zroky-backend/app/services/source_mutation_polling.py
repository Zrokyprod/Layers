from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SourceMutationPollState, SystemOfRecordConnectorConfig
from app.services.provider_key_cipher import VaultCipherUnavailable
from app.services.source_mutations import ingest_source_mutation
from app.services.system_of_record_connector_config import (
    GENERIC_REST_CONNECTOR_TYPE,
    POSTGRES_READ_CONNECTOR_TYPE,
    RAZORPAY_REFUND_CONNECTOR_TYPE,
    STRIPE_PAYMENT_CONNECTOR_TYPE,
    STRIPE_REFUND_CONNECTOR_TYPE,
    decrypt_connector_bearer_token,
    decrypt_connector_database_url,
)

logger = logging.getLogger(__name__)

POLLABLE_CONNECTOR_TYPES = {
    GENERIC_REST_CONNECTOR_TYPE,
    POSTGRES_READ_CONNECTOR_TYPE,
    RAZORPAY_REFUND_CONNECTOR_TYPE,
    STRIPE_PAYMENT_CONNECTOR_TYPE,
    STRIPE_REFUND_CONNECTOR_TYPE,
}


@dataclass(frozen=True)
class SourceMutationPollResult:
    scanned: int = 0
    succeeded: int = 0
    failed: int = 0
    ingested: int = 0
    skipped: int = 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except Exception:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _json_dumps(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True, default=str)


def _deep_get(value: Any, path: str | None) -> Any:
    if not path:
        return value
    current = value
    for part in path.split("."):
        if isinstance(current, Mapping):
            current = current.get(part)
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
            continue
        return None
    return current


def _as_list(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        return [value]
    return []


def _clean_text(value: Any, fallback: str | None = None) -> str | None:
    if value is None:
        return fallback
    rendered = str(value).strip()
    return rendered or fallback


def _event_timestamp(value: Mapping[str, Any]) -> datetime | None:
    for key in ("created", "created_at", "updated", "updated_at", "occurred_at", "event_time"):
        raw = value.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            try:
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            except Exception:
                continue
        if isinstance(raw, str):
            cleaned = raw.strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(cleaned)
            except ValueError:
                continue
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _event_object(event: Mapping[str, Any]) -> Mapping[str, Any]:
    data = event.get("data")
    if isinstance(data, Mapping):
        obj = data.get("object")
        if isinstance(obj, Mapping):
            return obj
    obj = event.get("object")
    return obj if isinstance(obj, Mapping) else event


def _source_for_connector(connector_type: str) -> str:
    if connector_type in {STRIPE_REFUND_CONNECTOR_TYPE, STRIPE_PAYMENT_CONNECTOR_TYPE}:
        return "stripe"
    if connector_type == RAZORPAY_REFUND_CONNECTOR_TYPE:
        return "razorpay"
    if connector_type == POSTGRES_READ_CONNECTOR_TYPE:
        return "postgres"
    return "generic_rest"


def _action_type_for_event(connector_type: str, event: Mapping[str, Any], obj: Mapping[str, Any]) -> str:
    event_type = _clean_text(event.get("type"), "") or ""
    if connector_type == STRIPE_REFUND_CONNECTOR_TYPE or "refund" in event_type:
        return "refund"
    if connector_type == STRIPE_PAYMENT_CONNECTOR_TYPE or "payment_intent" in event_type or "payment" in event_type:
        return "payment_adjustment"
    if connector_type == RAZORPAY_REFUND_CONNECTOR_TYPE:
        return "refund"
    if connector_type == POSTGRES_READ_CONNECTOR_TYPE:
        return _clean_text(obj.get("action_type") or obj.get("mutation_type"), "database_record_update") or "database_record_update"
    return _clean_text(obj.get("action_type") or event.get("action_type"), "internal_api_mutation") or "internal_api_mutation"


def _mutation_payload(connector_type: str, event: Mapping[str, Any]) -> dict[str, Any]:
    obj = _event_object(event)
    mutation_id = _clean_text(event.get("id") or obj.get("id") or obj.get("mutation_id"), str(uuid4())) or str(uuid4())
    action_type = _action_type_for_event(connector_type, event, obj)
    resource_type = _clean_text(obj.get("object") or obj.get("resource_type") or event.get("resource_type"), action_type)
    resource_id = _clean_text(obj.get("id") or obj.get("resource_id") or event.get("resource_id"), mutation_id)
    actor = obj.get("actor") if isinstance(obj.get("actor"), Mapping) else {}
    metadata = {
        "feed": "source_mutation_poller",
        "connector_type": connector_type,
        "event_type": event.get("type"),
        "status": obj.get("status"),
    }
    for key in ("zroky_action_id", "action_receipt_id", "idempotency_key"):
        if obj.get(key) is not None:
            metadata[key] = obj.get(key)

    return {
        "source_system": _source_for_connector(connector_type),
        "mutation_id": mutation_id,
        "action_type": action_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "system_ref": _clean_text(event.get("system_ref") or f"{_source_for_connector(connector_type)}:{resource_id}"),
        "actor_type": _clean_text(obj.get("actor_type") or actor.get("type") or event.get("actor_type"), "unknown"),
        "actor_id": _clean_text(obj.get("actor_id") or actor.get("id") or event.get("actor_id")),
        "zroky_action_id": _clean_text(obj.get("zroky_action_id") or event.get("zroky_action_id")),
        "action_receipt_id": _clean_text(obj.get("action_receipt_id") or event.get("action_receipt_id")),
        "idempotency_key": _clean_text(obj.get("idempotency_key") or event.get("idempotency_key")),
        "metadata": metadata,
        "occurred_at": _event_timestamp(event) or _event_timestamp(obj),
    }


def _state_for_connector(db: Session, row: SystemOfRecordConnectorConfig) -> SourceMutationPollState:
    state = db.execute(
        select(SourceMutationPollState).where(
            SourceMutationPollState.project_id == row.project_id,
            SourceMutationPollState.connector_type == row.connector_type,
        )
    ).scalar_one_or_none()
    if state is not None:
        return state
    state = SourceMutationPollState(
        id=str(uuid4()),
        project_id=row.project_id,
        connector_type=row.connector_type,
        source_system=_source_for_connector(row.connector_type),
        cursor_json=_json_dumps({}),
    )
    db.add(state)
    db.flush()
    return state


def _query_mapping(row: SystemOfRecordConnectorConfig) -> dict[str, Any]:
    return _json_loads(row.query_json)


def _poll_http_events(
    row: SystemOfRecordConnectorConfig,
    *,
    db: Session,
    state: SourceMutationPollState,
    limit: int,
    timeout_seconds: float,
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    query = _query_mapping(row)
    cursor = _json_loads(state.cursor_json)
    event_path = _clean_text(query.get("event_path"), "data") or "data"
    path = _clean_text(query.get("mutation_feed_path") or query.get("event_feed_path"))
    if not path:
        if row.connector_type in {STRIPE_REFUND_CONNECTOR_TYPE, STRIPE_PAYMENT_CONNECTOR_TYPE}:
            path = "/v1/events"
            query.setdefault("type", "refund.updated" if row.connector_type == STRIPE_REFUND_CONNECTOR_TYPE else "payment_intent.succeeded")
        elif row.connector_type == RAZORPAY_REFUND_CONNECTOR_TYPE:
            path = "/v1/refunds"
            event_path = "items"
        else:
            path = row.path_template

    params = {str(k): v for k, v in query.items() if k not in {"event_path", "mutation_feed_path", "event_feed_path"}}
    params.setdefault("limit", min(max(limit, 1), 100))
    if cursor.get("last_seen_epoch") and row.connector_type in {STRIPE_REFUND_CONNECTOR_TYPE, STRIPE_PAYMENT_CONNECTOR_TYPE}:
        params.setdefault("created[gt]", int(cursor["last_seen_epoch"]))

    token = decrypt_connector_bearer_token(row, project_id=row.project_id, db=db)
    headers = {"Accept": "application/json"}
    auth: tuple[str, str] | None = None
    if row.connector_type == RAZORPAY_REFUND_CONNECTOR_TYPE:
        key_id = _clean_text(params.pop("key_id", None))
        if key_id and token:
            auth = (key_id, token)
    elif token:
        headers["Authorization"] = f"Bearer {token}"

    url = row.base_url.rstrip("/") + "/" + path.lstrip("/")
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.get(url, headers=headers, params=params, auth=auth)
        response.raise_for_status()
        payload = response.json()

    events = _as_list(_deep_get(payload, event_path))
    new_cursor = dict(cursor)
    if events:
        new_cursor["last_event_id"] = _clean_text(events[0].get("id"), new_cursor.get("last_event_id"))
        newest_seen = max(
            (
                timestamp.timestamp()
                for event in events
                if (timestamp := _event_timestamp(event)) is not None
            ),
            default=None,
        )
        if newest_seen is not None:
            new_cursor["last_seen_epoch"] = int(newest_seen)
    if isinstance(payload, Mapping) and payload.get("has_more") is False:
        new_cursor["exhausted_at"] = _now().isoformat()
    return events, new_cursor


def _poll_postgres_events(
    row: SystemOfRecordConnectorConfig,
    *,
    db: Session,
    state: SourceMutationPollState,
    limit: int,
    timeout_seconds: float,
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - optional dependency guard
        raise RuntimeError("psycopg is required for postgres source mutation polling") from exc

    database_url = decrypt_connector_database_url(row, project_id=row.project_id, db=db)
    if not database_url:
        raise RuntimeError("postgres connector database_url is not configured")
    query = row.read_query
    if not query:
        raise RuntimeError("postgres connector read_query is not configured")
    cursor = _json_loads(state.cursor_json)
    params = {
        **_query_mapping(row),
        "limit": min(max(limit, 1), 500),
        "last_seen_id": cursor.get("last_seen_id"),
        "last_seen_at": cursor.get("last_seen_at"),
    }
    with psycopg.connect(database_url, connect_timeout=max(1, int(timeout_seconds))) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            columns = [desc[0] for desc in cur.description or []]
            rows = [dict(zip(columns, item)) for item in cur.fetchall()]
    events = _as_list(rows)
    new_cursor = dict(cursor)
    if events:
        last = events[-1]
        new_cursor["last_seen_id"] = _clean_text(last.get("id") or last.get("mutation_id"), new_cursor.get("last_seen_id"))
        seen_at = _event_timestamp(last)
        if seen_at is not None:
            new_cursor["last_seen_at"] = seen_at.isoformat()
    return events, new_cursor


def _poll_connector(
    db: Session,
    row: SystemOfRecordConnectorConfig,
    *,
    limit: int,
    timeout_seconds: float,
) -> int:
    state = _state_for_connector(db, row)
    state.last_polled_at = _now()
    try:
        if row.connector_type == POSTGRES_READ_CONNECTOR_TYPE:
            events, cursor = _poll_postgres_events(
                row, db=db, state=state, limit=limit, timeout_seconds=timeout_seconds
            )
        else:
            events, cursor = _poll_http_events(
                row, db=db, state=state, limit=limit, timeout_seconds=timeout_seconds
            )
        ingested = 0
        for event in events:
            payload = _mutation_payload(row.connector_type, event)
            ingest_source_mutation(db, project_id=row.project_id, **payload)
            ingested += 1
        state.cursor_json = _json_dumps(cursor)
        state.last_success_at = _now()
        state.last_error = None
        state.consecutive_failures = 0
        state.updated_at = _now()
        db.add(state)
        db.commit()
        return ingested
    except Exception as exc:
        db.rollback()
        state = _state_for_connector(db, row)
        state.last_polled_at = _now()
        state.last_error = str(exc)[:512]
        state.consecutive_failures = int(state.consecutive_failures or 0) + 1
        state.updated_at = _now()
        db.add(state)
        db.commit()
        raise


def poll_source_mutations_once(
    db: Session,
    *,
    project_limit: int = 100,
    per_connector_limit: int = 50,
    timeout_seconds: float = 5.0,
) -> SourceMutationPollResult:
    rows = list(
        db.execute(
            select(SystemOfRecordConnectorConfig)
            .where(
                SystemOfRecordConnectorConfig.is_active.is_(True),
                SystemOfRecordConnectorConfig.connector_type.in_(POLLABLE_CONNECTOR_TYPES),
            )
            .order_by(SystemOfRecordConnectorConfig.updated_at.desc())
            .limit(max(1, project_limit))
        ).scalars()
    )
    result = SourceMutationPollResult(scanned=len(rows))
    succeeded = failed = ingested = skipped = 0
    for row in rows:
        if not row.bearer_token_ciphertext and row.connector_type != POSTGRES_READ_CONNECTOR_TYPE:
            skipped += 1
            continue
        if row.connector_type == POSTGRES_READ_CONNECTOR_TYPE and not row.database_url_ciphertext:
            skipped += 1
            continue
        try:
            ingested += _poll_connector(
                db,
                row,
                limit=per_connector_limit,
                timeout_seconds=timeout_seconds,
            )
            succeeded += 1
        except (httpx.HTTPError, RuntimeError, VaultCipherUnavailable, ValueError) as exc:
            failed += 1
            logger.warning(
                "source_mutation_poll_failed project=%s connector=%s error=%s",
                row.project_id,
                row.connector_type,
                exc,
            )
    return SourceMutationPollResult(
        scanned=result.scanned,
        succeeded=succeeded,
        failed=failed,
        ingested=ingested,
        skipped=skipped,
    )
