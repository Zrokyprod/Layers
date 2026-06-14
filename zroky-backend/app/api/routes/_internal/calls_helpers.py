from datetime import datetime, timezone
from typing import Any, Mapping

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Call, DiagnosisJob
from app.schemas.dashboard import TraceRootFailureResponse, TraceTreeNodeResponse
from app.services.privacy import hash_identifier

FAILED_STATUSES = {"failed", "error", "errored", "timeout", "dead_lettered", "enqueue_failed"}
STATUS_FILTER_ALIASES = {
    "completed": {"completed", "done", "success"},
    "success": {"completed", "done", "success"},
    "failed": {"failed", "error", "errored", "timeout", "dead_lettered", "enqueue_failed"},
    "error": {"failed", "error", "errored", "dead_lettered", "enqueue_failed"},
}


class MarkCallGoldenRequest(BaseModel):
    golden_set_id: str = Field(min_length=1)
    weight: float = Field(default=1.0, gt=0)
    status: str | None = None
    expected_output_text: str | None = None
    criteria_json: str | None = None


class MarkCallGoldenResponse(BaseModel):
    id: str
    golden_set_id: str
    project_id: str
    call_id: str | None
    status: str
    expected_output_text: str | None
    source_output_text: str | None
    source_evidence_json: str | None
    expected_tokens: int | None
    expected_cost_usd: float | None
    expected_latency_ms: int | None
    criteria_json: str | None
    weight: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _matches_filter(value: str | None, expected: str | None) -> bool:
    if expected is None:
        return True
    if value is None:
        return False
    return value.strip().lower() == expected.strip().lower()


def _matches_user_filter(value: str | None, expected: str | None) -> bool:
    if _matches_filter(value, expected):
        return True
    if expected is None or value is None:
        return False

    hashed_expected = hash_identifier(expected)
    if hashed_expected is None:
        return False
    return value.strip().lower() == hashed_expected.strip().lower()


def _matches_status_filter(value: str | None, expected: str | None) -> bool:
    if expected is None:
        return True
    if value is None:
        return False

    expected_normalized = expected.strip().lower()
    value_normalized = value.strip().lower()
    aliases = STATUS_FILTER_ALIASES.get(expected_normalized)
    if aliases is not None:
        return value_normalized in aliases
    return value_normalized == expected_normalized


def _normalized_status_filter_values(expected: str | None) -> set[str]:
    if expected is None:
        return set()
    expected_normalized = expected.strip().lower()
    if not expected_normalized:
        return set()
    return STATUS_FILTER_ALIASES.get(expected_normalized, {expected_normalized})


def _normalized_user_filter_values(expected: str | None) -> set[str]:
    if expected is None:
        return set()
    expected_normalized = expected.strip().lower()
    if not expected_normalized:
        return set()
    values = {expected_normalized}
    hashed_expected = hash_identifier(expected)
    if hashed_expected:
        values.add(hashed_expected.strip().lower())
    return values


def _as_text(value: Any, *, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _as_float(value: Any, *, fallback: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback
        try:
            return float(text)
        except ValueError:
            return fallback
    return fallback


def _pick(payload: Mapping[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current: Any = payload
        for segment in path:
            if not isinstance(current, Mapping) or segment not in current:
                current = None
                break
            current = current[segment]
        if current is not None:
            return current
    return None


def _extract_trace_id(payload: Mapping[str, Any]) -> str | None:
    trace_id = _as_text(payload.get("trace_id"))
    return trace_id or None


def _extract_parent_call_id(payload: Mapping[str, Any]) -> str | None:
    parent = _as_text(payload.get("parent_call_id"))
    return parent or None


def _extract_agent_name(payload: Mapping[str, Any]) -> str | None:
    agent = _as_text(payload.get("agent_name"))
    return agent or None


def _extract_provider(payload: Mapping[str, Any]) -> str | None:
    provider = _as_text(_pick(payload, ("provider",), ("request", "provider")))
    return provider or None


def _extract_model(payload: Mapping[str, Any]) -> str | None:
    model = _as_text(_pick(payload, ("model",), ("request", "model")))
    return model or None


def _extract_cost_confidence(payload: Mapping[str, Any]) -> str | None:
    confidence = _as_text(
        _pick(payload, ("cost_confidence",), ("cost", "cost_confidence"), ("cost", "per_call_breakdown", "cost_confidence"))
    ).lower()
    if confidence in {"high", "stale", "degraded"}:
        return confidence
    return None


def _fetch_job_for_call(db: Session, *, tenant_id: str, call_id: str) -> DiagnosisJob | None:
    job = db.execute(
        select(DiagnosisJob).where(
            DiagnosisJob.tenant_id == tenant_id,
            DiagnosisJob.call_id == call_id,
        )
    ).scalar_one_or_none()
    if job is not None:
        return job

    return db.execute(
        select(DiagnosisJob).where(
            DiagnosisJob.tenant_id == tenant_id,
            DiagnosisJob.diagnosis_id == call_id,
        )
    ).scalar_one_or_none()


def _extract_root_failure(result_payload: Mapping[str, Any]) -> TraceRootFailureResponse | None:
    diagnoses = result_payload.get("diagnoses")
    if not isinstance(diagnoses, list) or not diagnoses:
        return None

    first = diagnoses[0]
    if not isinstance(first, Mapping):
        return None

    category = _as_text(first.get("category")) or None
    root_cause = _as_text(first.get("root_cause")) or None
    if category is None and root_cause is None:
        return None

    return TraceRootFailureResponse(category=category, root_cause=root_cause)


def _extract_wasted_cost_usd(
    *,
    payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
    status: str,
) -> float:
    blast = result_payload.get("blast_radius")
    if isinstance(blast, Mapping):
        value = _as_float(blast.get("wasted_cost_usd"))
        if value > 0:
            return round(value, 6)

    diagnoses = result_payload.get("diagnoses")
    if isinstance(diagnoses, list) and diagnoses:
        first = diagnoses[0]
        if isinstance(first, Mapping):
            value = _as_float(first.get("wasted_cost_usd"))
            if value <= 0:
                value = _as_float(first.get("cost_impact_usd"))
            if value > 0:
                return round(value, 6)

    if status.strip().lower() in FAILED_STATUSES:
        failed_cost = _as_float(
            _pick(
                payload,
                ("cost_usd",),
                ("total_cost_usd",),
                ("cost", "per_call_breakdown", "total_cost_usd"),
                ("cost", "event_cost_usd"),
            )
        )
        if failed_cost > 0:
            return round(failed_cost, 6)

    return 0.0


def _build_trace_tree_node(
    *,
    job: DiagnosisJob,
    payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> TraceTreeNodeResponse:
    return TraceTreeNodeResponse(
        call_id=job.diagnosis_id,
        parent_call_id=_extract_parent_call_id(payload),
        agent_name=_extract_agent_name(payload),
        provider=_extract_provider(payload),
        model=_extract_model(payload),
        cost_confidence=_extract_cost_confidence(payload),
        status=job.status,
        wasted_cost_usd=_extract_wasted_cost_usd(payload=payload, result_payload=result_payload, status=job.status),
        latency_ms=None,
        error_code=None,
        created_at=job.created_at,
        children=[],
    )


def _build_trace_tree_node_from_call(
    *,
    call: Call,
    job: DiagnosisJob | None,
    payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> TraceTreeNodeResponse:
    return TraceTreeNodeResponse(
        call_id=call.id,
        parent_call_id=_extract_parent_call_id(payload),
        agent_name=call.agent_name or _extract_agent_name(payload),
        provider=call.provider or _extract_provider(payload),
        model=call.model or _extract_model(payload),
        cost_confidence=call.cost_confidence or _extract_cost_confidence(payload),
        status=call.status,
        wasted_cost_usd=round(float(call.cost_total or 0.0), 6)
        if call.status.strip().lower() in FAILED_STATUSES
        else _extract_wasted_cost_usd(payload=payload, result_payload=result_payload, status=call.status),
        latency_ms=round(float(call.latency_ms), 1) if call.latency_ms is not None else None,
        error_code=call.error_code or None,
        created_at=call.created_at,
        children=[],
    )


