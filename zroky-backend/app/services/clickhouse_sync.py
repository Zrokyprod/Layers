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

from sqlalchemy import select, text
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
    import json
    payload: dict = {}
    if call.payload_json:
        try:
            payload = json.loads(call.payload_json)
        except Exception:
            pass

    usage = payload.get("usage") or {}
    return {
        "event_id": str(call.id),
        "project_id": str(call.project_id or ""),
        "provider": str(call.provider or "unknown"),
        "model": str(call.model or "unknown"),
        "call_type": str(call.call_type or "chat"),
        "timestamp_utc": call.created_at or datetime.now(UTC),
        "latency_ms": float(call.latency_ms or 0),
        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
        "output_tokens": int(usage.get("completion_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
        "cost_usd": float(call.cost_usd or 0),
        "status": str(call.status or "success"),
        "status_code": int(call.status_code or 200),
        "failure_code": str(call.failure_code or ""),
        "agent_name": str(call.agent_name or ""),
    }


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
