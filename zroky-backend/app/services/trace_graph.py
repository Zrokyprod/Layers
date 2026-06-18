from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Call, TraceRun, TraceSpan


FAILED_STATUSES = {"failed", "failure", "error", "timeout", "cancelled", "canceled", "aborted"}


def _parse_created_at(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return datetime.fromtimestamp(float(candidate), tz=timezone.utc)
        except ValueError:
            pass
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _safe_json_load(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if value == {} or value == [] or value == "":
        return None
    return _json_dumps(value)


def _bounded_text(value: object, *, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length]


def _as_float(value: object) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return parsed if parsed >= 0 else 0.0


def _derive_span_type(call: Call, payload: dict[str, Any]) -> str:
    explicit = _bounded_text(payload.get("span_type"), max_length=64)
    if explicit:
        return explicit
    call_type = str(payload.get("call_type") or call.call_type or "").strip().lower()
    provider = str(payload.get("provider") or call.provider or "").strip().lower()
    if call_type in {"agent_run", "trace"}:
        return "agent_run"
    if call_type in {"tool_call", "tool_result", "function"}:
        return call_type
    if call_type == "retrieval" or provider == "retrieval":
        return "retrieval"
    if call_type == "memory" or provider == "memory":
        return "memory"
    if call_type in {"policy", "policy_decision"}:
        return "policy"
    if call_type == "handoff":
        return "handoff"
    if payload.get("outcome"):
        return "outcome"
    return "llm_call"


def _versions_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    versions = dict(payload.get("versions") or {}) if isinstance(payload.get("versions"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    for key in ("code_sha", "deployment_id", "model_version", "tool_schema_version", "rag_version"):
        value = payload.get(key) or metadata.get(key)
        if value and key not in versions:
            versions[key] = value
    prompt_version = payload.get("prompt_version") or metadata.get("prompt_version")
    if prompt_version and "prompt_version" not in versions:
        versions["prompt_version"] = prompt_version
    return versions or None


def _input_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    result = dict(payload.get("input") or {}) if isinstance(payload.get("input"), dict) else {}
    if payload.get("system_prompt") and "system_prompt" not in result:
        result["system_prompt"] = payload["system_prompt"]
    if payload.get("user_input") and "user_input" not in result:
        result["user_input"] = payload["user_input"]
    return result or None


def _output_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    final_answer = payload.get("final_answer") or payload.get("output_content") or payload.get("normalized_output")
    result: dict[str, Any] = {}
    if final_answer is not None:
        result["final_answer"] = final_answer
    if payload.get("finish_reason") is not None:
        result["finish_reason"] = payload.get("finish_reason")
    if payload.get("stop_reason") is not None:
        result["stop_reason"] = payload.get("stop_reason")
    if payload.get("output_fingerprint") is not None:
        result["output_fingerprint"] = payload.get("output_fingerprint")
    return result or None


def _tool_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(payload.get("tool"), dict):
        return payload["tool"]
    calls = payload.get("tool_calls") or payload.get("tool_calls_made")
    if calls:
        return {"calls": calls}
    return None


def _json_has_key(raw: str | None, keys: set[str]) -> bool:
    parsed = _safe_json_load(raw)
    if not parsed:
        return False
    return any(key in parsed and parsed.get(key) not in (None, "", [], {}) for key in keys)


def _tool_has_result(raw: str | None) -> bool:
    parsed = _safe_json_load(raw)
    if not parsed:
        return False
    if any(parsed.get(key) not in (None, "", [], {}) for key in ("result", "output", "response", "tool_output")):
        return True
    calls = parsed.get("calls")
    if isinstance(calls, list):
        return any(
            isinstance(item, dict)
            and any(item.get(key) not in (None, "", [], {}) for key in ("result", "output", "response", "tool_output"))
            for item in calls
        )
    return False


def _span_sort_key(span: TraceSpan) -> tuple[int, int, datetime, str]:
    started = span.started_at or span.created_at or datetime.min.replace(tzinfo=timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (0 if span.span_index is not None else 1, span.span_index or 0, started, span.span_id)


def _completion_warnings(spans: list[TraceSpan]) -> list[str]:
    warnings: list[str] = []
    if not spans:
        return ["trace_graph_projection_missing"]

    has_input = any(span.input_json for span in spans)
    has_prompt_version = any(_json_has_key(span.versions_json, {"prompt_version"}) for span in spans)
    has_version_metadata = any(
        _json_has_key(span.versions_json, {"code_sha", "deployment_id", "model_version", "tool_schema_version", "rag_version"})
        for span in spans
    )
    tool_spans = [span for span in spans if span.span_type in {"tool_call", "tool_result"} or span.tool_json]
    has_tool_output_gap = any(not _tool_has_result(span.tool_json) for span in tool_spans)
    has_retrieval_or_memory = any(span.span_type in {"retrieval", "memory"} or span.retrieval_json or span.memory_json for span in spans)
    has_policy = any(span.span_type == "policy" or span.policy_json for span in spans)
    has_outcome = any(span.span_type == "outcome" or span.outcome_json for span in spans)

    if not has_input:
        warnings.append("input_missing")
    if not has_prompt_version:
        warnings.append("prompt_version_missing")
    if not has_version_metadata:
        warnings.append("version_metadata_missing")
    if has_tool_output_gap:
        warnings.append("tool_output_missing")
    if not has_retrieval_or_memory:
        warnings.append("rag_memory_spans_missing")
    if not has_policy:
        warnings.append("policy_decisions_missing")
    if not has_outcome:
        warnings.append("business_outcome_missing")
    return warnings


def _root_span(spans: list[TraceSpan]) -> TraceSpan:
    span_ids = {span.span_id for span in spans}
    for span in sorted(spans, key=_span_sort_key):
        if not span.parent_span_id or span.parent_span_id not in span_ids:
            return span
    return sorted(spans, key=_span_sort_key)[0]


def upsert_trace_graph_for_call(
    *,
    db: Session,
    tenant_id: str,
    call: Call,
    payload: dict[str, Any] | None = None,
) -> TraceRun:
    """Project a persisted Call into the normalized trace graph.

    The call ledger remains authoritative. This function creates or updates the
    graph span for that call, then recomputes the trace_run summary from all
    spans in the same tenant and trace. Duplicate ingest events therefore update
    the same span/run instead of double-counting cost or evidence.
    """
    payload = payload or _safe_json_load(call.payload_json)
    trace_id = _bounded_text(payload.get("trace_id"), max_length=128) or call.id
    span_id = _bounded_text(payload.get("span_id"), max_length=128) or call.id
    parent_span_id = _bounded_text(payload.get("parent_span_id") or payload.get("parent_call_id"), max_length=128)
    started_at = _parse_created_at(payload.get("created_at")) or call.created_at or datetime.now(timezone.utc)
    latency_ms = _as_float(payload.get("latency_ms")) if payload.get("latency_ms") is not None else call.latency_ms
    ended_at = None
    if latency_ms is not None:
        try:
            ended_at = datetime.fromtimestamp(started_at.timestamp() + (float(latency_ms) / 1000), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            ended_at = None

    span = db.execute(
        select(TraceSpan).where(
            TraceSpan.project_id == tenant_id,
            TraceSpan.span_id == span_id,
        )
    ).scalar_one_or_none()
    if span is None:
        span = TraceSpan(project_id=tenant_id, trace_id=trace_id, span_id=span_id)

    versions = _versions_payload(payload)
    span.trace_id = trace_id
    span.parent_span_id = parent_span_id
    span.call_id = call.id
    span.event_id = call.event_id
    span.environment_id = call.environment_id
    span.agent_id = call.agent_id
    span.agent_release_id = call.agent_release_id
    span.span_type = _derive_span_type(call, payload)
    span.span_name = _bounded_text(payload.get("span_name"), max_length=255)
    span.span_index = payload.get("span_index") if isinstance(payload.get("span_index"), int) else payload.get("step_index")
    span.agent_name = _bounded_text(payload.get("agent_name") or call.agent_name, max_length=255)
    span.provider = _bounded_text(payload.get("provider") or call.provider, max_length=120)
    span.model = _bounded_text(payload.get("model") or call.model, max_length=120)
    span.status = call.status or _bounded_text(payload.get("status"), max_length=32) or "unknown"
    span.error_code = _bounded_text(payload.get("error_code") or call.error_code, max_length=120)
    span.started_at = started_at
    span.ended_at = ended_at
    span.latency_ms = latency_ms
    span.cost_total = _as_float(payload.get("total_cost_usd") or payload.get("actual_cost_usd") or payload.get("cost_usd") or call.cost_total)
    span.input_json = _json_or_none(_input_payload(payload))
    span.output_json = _json_or_none(_output_payload(payload))
    span.tool_json = _json_or_none(_tool_payload(payload))
    span.retrieval_json = _json_or_none(payload.get("retrieval"))
    span.memory_json = _json_or_none(payload.get("memory"))
    span.handoff_json = _json_or_none(payload.get("handoff"))
    span.policy_json = _json_or_none(payload.get("policy"))
    span.outcome_json = _json_or_none(payload.get("outcome"))
    span.versions_json = _json_or_none(versions)
    span.payload_json = _json_dumps(payload)
    span.capture_source = _bounded_text(payload.get("capture_source") or payload.get("source"), max_length=64)
    span.masking_version = _bounded_text(payload.get("masking_version"), max_length=64)
    span.pii_masked = bool(payload.get("pii_masked")) or span.masking_version is not None
    db.add(span)
    db.flush()

    spans = list(
        db.execute(
            select(TraceSpan).where(
                TraceSpan.project_id == tenant_id,
                TraceSpan.trace_id == trace_id,
            )
        ).scalars()
    )
    spans.sort(key=_span_sort_key)
    root = _root_span(spans)
    agents: list[str] = []
    providers: list[str] = []
    for item in spans:
        if item.agent_name and item.agent_name not in agents:
            agents.append(item.agent_name)
        if item.provider and item.provider not in {"unknown", ""} and item.provider not in providers:
            providers.append(item.provider)

    warnings = _completion_warnings(spans)
    failed = [item for item in spans if (item.status or "").strip().lower() in FAILED_STATUSES]
    has_outcome = any(item.outcome_json for item in spans)
    score = max(0.0, round(1.0 - (len(warnings) / 7.0), 3))

    run = db.execute(
        select(TraceRun).where(
            TraceRun.project_id == tenant_id,
            TraceRun.trace_id == trace_id,
        )
    ).scalar_one_or_none()
    if run is None:
        run = TraceRun(project_id=tenant_id, trace_id=trace_id)

    run.root_span_id = root.span_id
    run.root_call_id = root.call_id
    run.status = "error" if failed else "completed"
    run.span_count = len(spans)
    run.agent_count = len(agents)
    run.agents_json = _json_dumps(agents)
    run.providers_json = _json_dumps(providers)
    run.started_at = spans[0].started_at if spans else None
    run.ended_at = max((item.ended_at or item.started_at for item in spans), default=None)
    run.total_latency_ms = sum(float(item.latency_ms or 0) for item in spans) if spans else 0.0
    run.total_cost_usd = sum(_as_float(item.cost_total) for item in spans)
    run.error_count = len(failed)
    run.has_failure = bool(failed)
    run.has_outcome = has_outcome
    run.completeness_warnings_json = _json_dumps(warnings)
    run.capture_completeness_score = score
    run.projection_error = None
    run.payload_json = _json_dumps(
        {
            "trace_id": trace_id,
            "root_span_id": run.root_span_id,
            "root_call_id": run.root_call_id,
            "warnings": warnings,
            "span_count": len(spans),
        }
    )
    db.add(run)
    return run
