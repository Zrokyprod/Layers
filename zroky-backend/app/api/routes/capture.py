import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.db.models import Call, OutcomeEvent
from app.db.session import get_db_session

router = APIRouter(prefix="/v1/capture")

CaptureStatus = Literal["connected", "stale", "no_data"]


class CaptureValidationWarning(BaseModel):
    code: Literal["tool_spans_missing", "outcome_missing", "prompt_version_missing"]
    label: str
    detail: str


class CaptureHealthResponse(BaseModel):
    project_id: str
    status: CaptureStatus
    stale_after_minutes: int
    last_call_id: str | None
    last_seen_at: str | None
    seconds_since_last_call: int | None
    last_provider: str | None
    last_model: str | None
    last_call_type: str | None
    last_source: str | None
    calls_24h: int
    sdk_events_24h: int
    gateway_events_24h: int
    retrieval_spans_24h: int
    memory_spans_24h: int
    error_events_24h: int
    outcome_events_24h: int
    sampled_recent_calls: int
    validation_warnings: list[CaptureValidationWarning]


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _source_for_call(call: Call) -> str:
    payload = _safe_json(call.payload_json)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata_source = str(metadata.get("source") or "").strip()
    if metadata_source:
        return metadata_source
    payload_source = str(payload.get("source") or "").strip()
    if payload_source:
        return payload_source
    if call.provider in {"retrieval", "memory"}:
        return call.provider
    return "unknown"


def _is_gateway_source(source: str) -> bool:
    return source == "gateway_redis_stream" or source.startswith("gateway")


def _is_sdk_source(source: str) -> bool:
    return source == "sdk_ingest"


def _has_tool_signal(call: Call) -> bool:
    call_type = (call.call_type or "").strip().lower()
    provider = (call.provider or "").strip().lower()
    if call_type in {"tool", "tool_call", "retrieval", "memory"} or provider in {"retrieval", "memory"}:
        return True

    payload = _safe_json(call.payload_json)
    if payload.get("tool_calls") or payload.get("tool_calls_made") or payload.get("tool_lifecycle_summary"):
        return True
    metadata = _safe_json(call.metadata_json)
    span_type = str(metadata.get("span_type") or "").strip().lower()
    return span_type in {"tool", "retrieval", "memory"}


def _has_prompt_version(call: Call) -> bool:
    payload = _safe_json(call.payload_json)
    if str(payload.get("prompt_version") or "").strip():
        return True
    metadata = _safe_json(call.metadata_json)
    return bool(str(metadata.get("prompt_version") or "").strip())


@router.get("/health", response_model=CaptureHealthResponse)
def capture_health(
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> CaptureHealthResponse:
    now = datetime.now(timezone.utc)
    stale_after_minutes = 15
    since_24h = now - timedelta(hours=24)

    last_call = db.execute(
        select(Call)
        .where(Call.project_id == tenant_id)
        .order_by(desc(Call.created_at))
        .limit(1)
    ).scalar_one_or_none()

    calls_24h = int(
        db.execute(
            select(func.count())
            .select_from(Call)
            .where(Call.project_id == tenant_id, Call.created_at >= since_24h)
        ).scalar_one()
        or 0
    )

    recent_calls = list(
        db.execute(
            select(Call)
            .where(Call.project_id == tenant_id, Call.created_at >= since_24h)
            .order_by(desc(Call.created_at))
            .limit(1000)
        ).scalars()
    )

    sdk_events = 0
    gateway_events = 0
    retrieval_spans = 0
    memory_spans = 0
    error_events = 0
    has_tool_signal = False
    has_prompt_version = False

    for call in recent_calls:
        source = _source_for_call(call)
        call_type = (call.call_type or "").strip().lower()
        provider = (call.provider or "").strip().lower()
        has_tool_signal = has_tool_signal or _has_tool_signal(call)
        has_prompt_version = has_prompt_version or _has_prompt_version(call)
        if _is_gateway_source(source):
            gateway_events += 1
        elif _is_sdk_source(source):
            sdk_events += 1
        if call_type == "retrieval" or provider == "retrieval":
            retrieval_spans += 1
        if call_type == "memory" or provider == "memory":
            memory_spans += 1
        if (call.status or "").strip().lower() in {"error", "failed", "timeout"}:
            error_events += 1

    outcome_events_24h = int(
        db.execute(
            select(func.count())
            .select_from(OutcomeEvent)
            .where(OutcomeEvent.project_id == tenant_id, OutcomeEvent.created_at >= since_24h)
        ).scalar_one()
        or 0
    )

    validation_warnings: list[CaptureValidationWarning] = []
    if recent_calls:
        if not has_tool_signal:
            validation_warnings.append(
                CaptureValidationWarning(
                    code="tool_spans_missing",
                    label="Tool spans missing",
                    detail="No tool, retrieval, memory, or model tool-call spans were seen in the last 24h.",
                )
            )
        if outcome_events_24h == 0:
            validation_warnings.append(
                CaptureValidationWarning(
                    code="outcome_missing",
                    label="Outcome missing",
                    detail="No business outcome events were linked in the last 24h.",
                )
            )
        if not has_prompt_version:
            validation_warnings.append(
                CaptureValidationWarning(
                    code="prompt_version_missing",
                    label="Prompt version missing",
                    detail="Recent calls did not include prompt_version, so deploy-to-failure diagnosis is weaker.",
                )
            )

    last_seen = _as_utc(last_call.created_at if last_call else None)
    seconds_since_last = int((now - last_seen).total_seconds()) if last_seen else None
    if last_seen is None:
        status: CaptureStatus = "no_data"
    elif seconds_since_last is not None and seconds_since_last > stale_after_minutes * 60:
        status = "stale"
    else:
        status = "connected"

    return CaptureHealthResponse(
        project_id=tenant_id,
        status=status,
        stale_after_minutes=stale_after_minutes,
        last_call_id=last_call.id if last_call else None,
        last_seen_at=last_seen.isoformat() if last_seen else None,
        seconds_since_last_call=seconds_since_last,
        last_provider=last_call.provider if last_call else None,
        last_model=last_call.model if last_call else None,
        last_call_type=last_call.call_type if last_call else None,
        last_source=_source_for_call(last_call) if last_call else None,
        calls_24h=calls_24h,
        sdk_events_24h=sdk_events,
        gateway_events_24h=gateway_events,
        retrieval_spans_24h=retrieval_spans,
        memory_spans_24h=memory_spans,
        error_events_24h=error_events,
        outcome_events_24h=outcome_events_24h,
        sampled_recent_calls=len(recent_calls),
        validation_warnings=validation_warnings,
    )
