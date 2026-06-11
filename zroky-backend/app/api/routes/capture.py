import json
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.db.models import Call, GatewayCaptureHealth, OutcomeEvent, ProjectAlert, TraceRun, TraceSpan
from app.db.session import get_db_session

router = APIRouter(prefix="/v1/capture")

CaptureStatus = Literal["connected", "stale", "no_data"]


class CaptureValidationWarning(BaseModel):
    code: Literal[
        "tool_spans_missing",
        "outcome_missing",
        "prompt_version_missing",
        "input_missing",
        "version_metadata_missing",
        "policy_decisions_missing",
        "trace_graph_projection_missing",
        "trace_graph_projection_failed",
        "gateway_spool_backlog",
        "gateway_capture_loss",
        "gateway_backpressure",
    ]
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
    trace_runs_24h: int = 0
    trace_spans_24h: int = 0
    policy_spans_24h: int = 0
    handoff_spans_24h: int = 0
    incomplete_trace_runs_24h: int = 0
    projection_failures_24h: int = 0
    gateway_count: int = 0
    gateway_unhealthy_count: int = 0
    gateway_worst_status: str = "unknown"
    gateway_spool_backlog: int = 0
    gateway_spool_bytes: int = 0
    gateway_spool_oldest_age_seconds: float = 0
    gateway_loss_count: int = 0
    gateway_backpressure_rejections: int = 0
    gateway_last_heartbeat_at: str | None = None
    error_events_24h: int
    outcome_events_24h: int
    sampled_recent_calls: int
    validation_warnings: list[CaptureValidationWarning]


class GatewaySpoolHeartbeat(BaseModel):
    enabled: bool = True
    backlog: int = Field(default=0, ge=0)
    bytes: int = Field(default=0, ge=0)
    max_bytes: int = Field(default=0, ge=0)
    reserved_bytes: int = Field(default=0, ge=0)
    oldest_age_seconds: float = Field(default=0, ge=0)
    high_watermark: bool = False


class GatewayCaptureHeartbeatRequest(BaseModel):
    project_id: str | None = None
    gateway_id: str
    emit_mode: str | None = None
    durability_mode: str | None = None
    capture_status: str = "unknown"
    spool: GatewaySpoolHeartbeat = Field(default_factory=GatewaySpoolHeartbeat)
    emit_failures: int = Field(default=0, ge=0)
    enqueue_failures: int = Field(default=0, ge=0)
    flush_failures: int = Field(default=0, ge=0)
    flushed: int = Field(default=0, ge=0)
    loss_count: int = Field(default=0, ge=0)
    backpressure_rejections: int = Field(default=0, ge=0)
    last_error: str | None = None
    version: str | None = None
    checked_at: datetime | None = None


class GatewayCaptureHeartbeatResponse(BaseModel):
    project_id: str
    gateway_id: str
    capture_status: str
    alert_categories: list[str]


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


def _safe_json_any(raw: str | None) -> Any | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _has_version_metadata(span: TraceSpan) -> bool:
    parsed = _safe_json_any(span.versions_json)
    if not isinstance(parsed, dict):
        return False
    return any(
        parsed.get(key) not in (None, "", [], {})
        for key in ("code_sha", "deployment_id", "model_version", "tool_schema_version", "rag_version")
    )


def _gateway_status_rank(status_value: str | None) -> int:
    normalized = (status_value or "unknown").strip().lower()
    return {
        "ok": 0,
        "unknown": 1,
        "degraded": 2,
        "backpressure": 3,
        "loss_detected": 4,
    }.get(normalized, 1)


def _worst_gateway_status(rows: list[GatewayCaptureHealth], now: datetime) -> str:
    if not rows:
        return "unknown"
    worst = "ok"
    for row in rows:
        status_value = row.capture_status or "unknown"
        heartbeat_at = _as_utc(row.heartbeat_at)
        if heartbeat_at is None or (now - heartbeat_at).total_seconds() > 120:
            status_value = "degraded"
        if _gateway_status_rank(status_value) > _gateway_status_rank(worst):
            worst = status_value
    return worst


def _gateway_alert_id(prefix: str, gateway_id: str) -> str:
    digest = hashlib.sha1(gateway_id.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"[:64]


def _upsert_gateway_capture_alert(
    *,
    db: Session,
    tenant_id: str,
    gateway_id: str,
    category: str,
    severity: str,
    title: str,
    evidence: dict[str, Any],
) -> None:
    diagnosis_prefix = "gateway-loss" if category == "CAPTURE_LOSS" else "gateway-backpressure"
    diagnosis_id = _gateway_alert_id(diagnosis_prefix, gateway_id)
    alert = db.execute(
        select(ProjectAlert).where(
            ProjectAlert.tenant_id == tenant_id,
            ProjectAlert.diagnosis_id == diagnosis_id,
            ProjectAlert.category == category,
        )
    ).scalar_one_or_none()
    evidence_json = json.dumps(evidence, separators=(",", ":"))
    now = datetime.now(timezone.utc)
    if alert is None:
        db.add(
            ProjectAlert(
                tenant_id=tenant_id,
                diagnosis_id=diagnosis_id,
                category=category,
                severity=severity,
                status="OPEN",
                source="gateway_capture",
                title=title,
                evidence_json=evidence_json,
            )
        )
        return
    alert.status = "OPEN"
    alert.resolved_at = None
    alert.updated_at = now
    alert.title = title
    alert.evidence_json = evidence_json
    db.add(alert)


@router.post("/gateway-heartbeat", response_model=GatewayCaptureHeartbeatResponse)
def gateway_capture_heartbeat(
    body: GatewayCaptureHeartbeatRequest,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> GatewayCaptureHeartbeatResponse:
    if body.project_id is not None and body.project_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gateway heartbeat project does not match authenticated project.",
        )

    now = datetime.now(timezone.utc)
    heartbeat_at = _as_utc(body.checked_at) or now
    existing = db.execute(
        select(GatewayCaptureHealth).where(
            GatewayCaptureHealth.project_id == tenant_id,
            GatewayCaptureHealth.gateway_id == body.gateway_id,
        )
    ).scalar_one_or_none()

    previous_loss = existing.loss_count if existing is not None else 0
    previous_backpressure = existing.backpressure_rejections if existing is not None else 0
    row = existing or GatewayCaptureHealth(project_id=tenant_id, gateway_id=body.gateway_id, heartbeat_at=heartbeat_at)
    row.emit_mode = body.emit_mode
    row.durability_mode = body.durability_mode
    row.capture_status = body.capture_status
    row.spool_enabled = body.spool.enabled
    row.spool_backlog = body.spool.backlog
    row.spool_bytes = body.spool.bytes
    row.spool_max_bytes = body.spool.max_bytes
    row.spool_reserved_bytes = body.spool.reserved_bytes
    row.spool_oldest_age_seconds = body.spool.oldest_age_seconds
    row.spool_high_watermark = body.spool.high_watermark
    row.emit_failures = body.emit_failures
    row.enqueue_failures = body.enqueue_failures
    row.flush_failures = body.flush_failures
    row.flushed = body.flushed
    row.loss_count = body.loss_count
    row.backpressure_rejections = body.backpressure_rejections
    row.last_error = body.last_error
    row.version = body.version
    row.heartbeat_at = heartbeat_at
    row.payload_json = body.model_dump_json()
    db.add(row)

    alert_categories: list[str] = []
    if body.loss_count > previous_loss or body.capture_status == "loss_detected":
        _upsert_gateway_capture_alert(
            db=db,
            tenant_id=tenant_id,
            gateway_id=body.gateway_id,
            category="CAPTURE_LOSS",
            severity="critical",
            title="Gateway capture loss detected.",
            evidence={
                "gateway_id": body.gateway_id,
                "loss_count": body.loss_count,
                "previous_loss_count": previous_loss,
                "capture_status": body.capture_status,
                "spool_backlog": body.spool.backlog,
                "last_error": body.last_error,
            },
        )
        alert_categories.append("CAPTURE_LOSS")
    if (
        body.backpressure_rejections > previous_backpressure
        or body.capture_status == "backpressure"
        or body.spool.high_watermark
    ):
        _upsert_gateway_capture_alert(
            db=db,
            tenant_id=tenant_id,
            gateway_id=body.gateway_id,
            category="CAPTURE_BACKPRESSURE",
            severity="high",
            title="Gateway capture backpressure is blocking or risking provider calls.",
            evidence={
                "gateway_id": body.gateway_id,
                "backpressure_rejections": body.backpressure_rejections,
                "previous_backpressure_rejections": previous_backpressure,
                "capture_status": body.capture_status,
                "spool_backlog": body.spool.backlog,
                "spool_bytes": body.spool.bytes,
                "spool_max_bytes": body.spool.max_bytes,
                "last_error": body.last_error,
            },
        )
        alert_categories.append("CAPTURE_BACKPRESSURE")

    db.commit()
    return GatewayCaptureHeartbeatResponse(
        project_id=tenant_id,
        gateway_id=body.gateway_id,
        capture_status=body.capture_status,
        alert_categories=alert_categories,
    )


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
    has_input_signal = False
    has_version_metadata = False
    has_policy_signal = False

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

    recent_spans = list(
        db.execute(
            select(TraceSpan)
            .where(TraceSpan.project_id == tenant_id, TraceSpan.started_at >= since_24h)
            .limit(2000)
        ).scalars()
    )
    trace_spans_24h = len(recent_spans)
    graph_retrieval_spans = 0
    graph_memory_spans = 0
    trace_runs_24h = int(
        db.execute(
            select(func.count())
            .select_from(TraceRun)
            .where(TraceRun.project_id == tenant_id, TraceRun.started_at >= since_24h)
        ).scalar_one()
        or 0
    )
    policy_spans_24h = 0
    handoff_spans_24h = 0
    for span in recent_spans:
        span_type = (span.span_type or "").strip().lower()
        has_tool_signal = has_tool_signal or bool(span.tool_json) or span_type in {"tool_call", "tool_result"}
        has_input_signal = has_input_signal or bool(span.input_json)
        has_version_metadata = has_version_metadata or _has_version_metadata(span)
        has_policy_signal = has_policy_signal or bool(span.policy_json) or span_type == "policy"
        if span_type == "retrieval" or span.retrieval_json:
            graph_retrieval_spans += 1
        if span_type == "memory" or span.memory_json:
            graph_memory_spans += 1
        if span_type == "policy" or span.policy_json:
            policy_spans_24h += 1
        if span_type == "handoff" or span.handoff_json:
            handoff_spans_24h += 1

    retrieval_spans = max(retrieval_spans, graph_retrieval_spans)
    memory_spans = max(memory_spans, graph_memory_spans)

    incomplete_trace_runs_24h = int(
        db.execute(
            select(func.count())
            .select_from(TraceRun)
            .where(
                TraceRun.project_id == tenant_id,
                TraceRun.started_at >= since_24h,
                TraceRun.capture_completeness_score < 1,
            )
        ).scalar_one()
        or 0
    )
    projection_failures_24h = int(
        db.execute(
            select(func.count())
            .select_from(TraceRun)
            .where(
                TraceRun.project_id == tenant_id,
                TraceRun.started_at >= since_24h,
                TraceRun.projection_error.is_not(None),
            )
        ).scalar_one()
        or 0
    )

    gateway_rows = list(
        db.execute(
            select(GatewayCaptureHealth).where(GatewayCaptureHealth.project_id == tenant_id)
        ).scalars()
    )
    gateway_count = len(gateway_rows)
    gateway_worst_status = _worst_gateway_status(gateway_rows, now)
    gateway_unhealthy_count = 0
    gateway_spool_backlog = 0
    gateway_spool_bytes = 0
    gateway_spool_oldest_age_seconds = 0.0
    gateway_loss_count = 0
    gateway_backpressure_rejections = 0
    gateway_last_heartbeat: datetime | None = None
    for gateway in gateway_rows:
        heartbeat_at = _as_utc(gateway.heartbeat_at)
        status_value = gateway.capture_status or "unknown"
        if heartbeat_at is None or (now - heartbeat_at).total_seconds() > 120:
            status_value = "degraded"
        if status_value != "ok":
            gateway_unhealthy_count += 1
        gateway_spool_backlog += int(gateway.spool_backlog or 0)
        gateway_spool_bytes += int(gateway.spool_bytes or 0)
        gateway_spool_oldest_age_seconds = max(
            gateway_spool_oldest_age_seconds,
            float(gateway.spool_oldest_age_seconds or 0),
        )
        gateway_loss_count += int(gateway.loss_count or 0)
        gateway_backpressure_rejections += int(gateway.backpressure_rejections or 0)
        if heartbeat_at is not None and (gateway_last_heartbeat is None or heartbeat_at > gateway_last_heartbeat):
            gateway_last_heartbeat = heartbeat_at

    validation_warnings: list[CaptureValidationWarning] = []
    if recent_calls:
        if trace_spans_24h == 0:
            validation_warnings.append(
                CaptureValidationWarning(
                    code="trace_graph_projection_missing",
                    label="Trace graph missing",
                    detail="Recent calls arrived, but no normalized trace graph spans were projected.",
                )
            )
        if projection_failures_24h > 0:
            validation_warnings.append(
                CaptureValidationWarning(
                    code="trace_graph_projection_failed",
                    label="Trace graph projection failed",
                    detail=f"{projection_failures_24h} trace graph projections reported errors in the last 24h.",
                )
            )
        if not has_input_signal:
            validation_warnings.append(
                CaptureValidationWarning(
                    code="input_missing",
                    label="Input missing",
                    detail="Recent trace spans did not include masked user/system input evidence.",
                )
            )
        if not has_version_metadata:
            validation_warnings.append(
                CaptureValidationWarning(
                    code="version_metadata_missing",
                    label="Version metadata missing",
                    detail="Recent trace spans did not include code/model/tool/RAG version metadata.",
                )
            )
        if not has_policy_signal:
            validation_warnings.append(
                CaptureValidationWarning(
                    code="policy_decisions_missing",
                    label="Policy decisions missing",
                    detail="No captured policy decision spans were seen in the last 24h.",
                )
            )
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
    if gateway_loss_count > 0 or gateway_worst_status == "loss_detected":
        validation_warnings.append(
            CaptureValidationWarning(
                code="gateway_capture_loss",
                label="Gateway capture loss detected",
                detail="A gateway reported dropped or unreadable capture records. Treat replay evidence as incomplete until resolved.",
            )
        )
    if gateway_backpressure_rejections > 0 or gateway_worst_status == "backpressure":
        validation_warnings.append(
            CaptureValidationWarning(
                code="gateway_backpressure",
                label="Gateway capture backpressure",
                detail="A gateway is rejecting provider calls or near spool capacity to preserve capture guarantees.",
            )
        )
    if gateway_spool_backlog > 0:
        validation_warnings.append(
            CaptureValidationWarning(
                code="gateway_spool_backlog",
                label="Gateway spool backlog",
                detail=f"{gateway_spool_backlog} capture event(s) are queued locally and waiting for delivery.",
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
        trace_runs_24h=trace_runs_24h,
        trace_spans_24h=trace_spans_24h,
        policy_spans_24h=policy_spans_24h,
        handoff_spans_24h=handoff_spans_24h,
        incomplete_trace_runs_24h=incomplete_trace_runs_24h,
        projection_failures_24h=projection_failures_24h,
        gateway_count=gateway_count,
        gateway_unhealthy_count=gateway_unhealthy_count,
        gateway_worst_status=gateway_worst_status,
        gateway_spool_backlog=gateway_spool_backlog,
        gateway_spool_bytes=gateway_spool_bytes,
        gateway_spool_oldest_age_seconds=gateway_spool_oldest_age_seconds,
        gateway_loss_count=gateway_loss_count,
        gateway_backpressure_rejections=gateway_backpressure_rejections,
        gateway_last_heartbeat_at=gateway_last_heartbeat.isoformat() if gateway_last_heartbeat else None,
        error_events_24h=error_events,
        outcome_events_24h=outcome_events_24h,
        sampled_recent_calls=len(recent_calls),
        validation_warnings=validation_warnings,
    )
