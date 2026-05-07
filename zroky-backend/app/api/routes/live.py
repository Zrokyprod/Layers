from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.dependencies.tenant import require_tenant_role
from app.db.models import DiagnosisJob
from app.db.session import SessionLocal
from app.schemas.dashboard import CallListItem
from app.services.dashboard_data import build_call_item

router = APIRouter(prefix="/v1/live")


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def _encode_event(event: str, payload: dict[str, Any]) -> bytes:
    serialized = json.dumps(payload, separators=(",", ":"), default=_json_default)
    return f"event: {event}\ndata: {serialized}\n\n".encode("utf-8")


def _fetch_jobs(tenant_id: str, limit: int) -> list[dict[str, Any]]:
    """Run a short-lived synchronous DB query and return serialisable items."""
    db = SessionLocal()
    try:
        jobs = db.execute(
            select(DiagnosisJob)
            .where(DiagnosisJob.tenant_id == tenant_id)
            .order_by(DiagnosisJob.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return [
            CallListItem.model_validate(build_call_item(job)).model_dump(mode="json")
            for job in jobs
        ]
    finally:
        db.close()


@router.get("/calls")
async def stream_calls(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    poll_interval_ms: int = Query(default=1500, ge=500, le=10000),
    max_events: int | None = Query(default=None, ge=1, le=100),
    tenant_id: str = Depends(require_tenant_role("viewer")),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[bytes]:
        last_seen_call_id: str | None = None
        heartbeat_ticks = 0
        heartbeat_threshold = max(1, int(15000 / poll_interval_ms))
        emitted_events = 0

        def should_stop() -> bool:
            return max_events is not None and emitted_events >= max_events

        while True:
            if await request.is_disconnected():
                break

            items = await asyncio.to_thread(_fetch_jobs, tenant_id, limit)
            newest_call_id = items[0]["call_id"] if items else None

            if newest_call_id != last_seen_call_id:
                last_seen_call_id = newest_call_id
                heartbeat_ticks = 0
                yield _encode_event(
                    "snapshot",
                    {
                        "items": items,
                        "sent_at": datetime.now(UTC).isoformat(),
                    },
                )
                emitted_events += 1
                if should_stop():
                    break
            else:
                heartbeat_ticks += 1
                if heartbeat_ticks >= heartbeat_threshold:
                    heartbeat_ticks = 0
                    yield b": ping\n\n"
                    emitted_events += 1
                    if should_stop():
                        break

            await asyncio.sleep(poll_interval_ms / 1000)

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
