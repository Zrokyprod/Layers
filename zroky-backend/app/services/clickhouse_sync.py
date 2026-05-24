"""ClickHouse incremental sync worker.

Periodically pulls new Call rows from Postgres and bulk-inserts them into
the ClickHouse `ingest_events` staging table. The ClickHouse materialized
views then drive the `cost_hourly`, `cost_daily`, and `issues_topk` tables.

Design:
  - Uses a watermark stored in Redis (key: "ch_sync:watermark") so each
    run only pulls rows created after the last successful sync.
  - Best-effort: failures are logged but never propagate to the API.
  - Runs as a Celery beat task every CLICKHOUSE_SYNC_INTERVAL_SECONDS.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Call
from app.services.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)

_WATERMARK_KEY = "ch_sync:watermark"
_BATCH_SIZE = 500


def sync_calls_to_clickhouse(db: Session) -> dict[str, Any]:
    """Pull new calls from Postgres and insert into ClickHouse.

    Returns a summary dict for logging / Celery result.
    """
    settings = get_settings()
    ch = get_clickhouse_client()
    if ch is None:
        return {"status": "skipped", "reason": "clickhouse_unavailable"}

    watermark = _get_watermark()
    since = watermark or (datetime.now(UTC) - timedelta(hours=2))

    rows = db.execute(
        select(Call).where(Call.created_at > since).order_by(Call.created_at).limit(_BATCH_SIZE)
    ).scalars().all()

    if not rows:
        return {"status": "ok", "inserted": 0, "watermark": since.isoformat()}

    records = [_call_to_row(r) for r in rows]
    try:
        ch.execute(
            "INSERT INTO ingest_events VALUES",
            records,
            types_check=False,
        )
        new_watermark = rows[-1].created_at
        _set_watermark(new_watermark)
        logger.info("ch_sync: inserted %d rows up to %s", len(records), new_watermark)
        return {"status": "ok", "inserted": len(records), "watermark": new_watermark.isoformat()}
    except Exception as exc:
        logger.warning("ch_sync insert failed: %s", exc)
        return {"status": "error", "reason": str(exc)}


def is_clickhouse_available() -> bool:
    return get_clickhouse_client() is not None


# ── helpers ───────────────────────────────────────────────────────────────────

def _call_to_row(call: Call) -> dict[str, Any]:
    status = str(call.status or "success")
    return {
        "event_id": str(call.id),
        "project_id": str(call.project_id or ""),
        "provider": str(call.provider or "unknown"),
        "model": str(call.model or "unknown"),
        "call_type": str(call.call_type or "chat"),
        "timestamp_utc": call.created_at or datetime.now(UTC),
        "latency_ms": float(call.latency_ms or 0),
        "prompt_tokens": int(call.input_tokens or 0),
        "output_tokens": int(call.output_tokens or 0),
        "total_tokens": int(call.total_tokens or 0),
        "cost_usd": float(call.cost_total or 0),
        "status": status,
        "status_code": _status_code_for_call(call),
        "failure_code": str(call.error_code or ""),
        "agent_name": str(call.agent_name or ""),
    }


def _status_code_for_call(call: Call) -> int:
    metadata = _load_json_object(call.metadata_json)
    payload = _load_json_object(call.payload_json)
    payload_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

    for value in (
        metadata.get("status_code"),
        payload_metadata.get("status_code"),
        payload.get("status_code"),
    ):
        status_code = _positive_int(value)
        if status_code is not None:
            return status_code

    status = str(call.status or "").strip().lower()
    error_code = str(call.error_code or "").strip().lower()
    if status in {"completed", "success"}:
        return 200
    if status in {"timeout", "timed_out"} or "timeout" in error_code:
        return 408
    if status in {"rate_limited", "rate_limit"} or "rate" in error_code:
        return 429
    if status in {"cancelled", "canceled"}:
        return 499
    if status in {"error", "failed", "failure"} or error_code:
        return 500
    return 200


def _load_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _get_watermark() -> datetime | None:
    try:
        from app.services.redis_client import get_redis_client
        rdb = get_redis_client()
        val = rdb.get(_WATERMARK_KEY)
        if val:
            return datetime.fromisoformat(val.decode())
    except Exception:
        pass
    return None


def _set_watermark(ts: datetime) -> None:
    try:
        from app.services.redis_client import get_redis_client
        rdb = get_redis_client()
        rdb.set(_WATERMARK_KEY, ts.isoformat(), ex=86400 * 7)
    except Exception:
        pass
