from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Call, DiagnosisJob, TraceSpan
from app.services.anomalies import map_failure_code_to_detector
from app.services.privacy import mask_value


_COMPACT_EVIDENCE_KEYS = {
    "provider",
    "model",
    "tool_name",
    "actual_tools",
    "expected_tool",
    "required_tool",
    "allowed_tools",
    "status",
    "error",
    "error_code",
    "violation",
    "trigger_rule",
    "latency_ms",
    "threshold_ms",
    "current_15m_spend_usd",
    "baseline_15m_spend_usd",
    "required_document",
    "document_count",
    "groundedness_score",
    "outcome_status",
    "workflow_name",
    "policy_decision",
    "action",
}


def _safe_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_list_json(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple, set)):
        return None
    text = str(value).strip()
    return text or None


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = _as_text(value)
        if text:
            return text
    return None


def _nested_text(mapping: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        if key in mapping:
            text = _as_text(mapping.get(key))
            if text:
                return text
    for value in mapping.values():
        if isinstance(value, Mapping):
            text = _nested_text(value, *keys)
            if text:
                return text
    return None


def _compact(value: Any, *, limit: int = 1200) -> Any:
    masked = mask_value(value)
    text = json.dumps(masked, separators=(",", ":"), default=str)
    if len(text) <= limit:
        return masked
    return {"truncated": True, "preview": text[:limit]}


def _call_payload(call: Call | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if call is None:
        return {}, {}
    return _safe_json(call.payload_json), _safe_json(call.metadata_json)


def _trace_id_from(payload: Mapping[str, Any], call: Call | None) -> str | None:
    call_payload, metadata = _call_payload(call)
    return _first_text(
        _nested_text(payload, "trace_id"),
        _nested_text(call_payload, "trace_id"),
        _nested_text(metadata, "trace_id"),
        getattr(call, "id", None),
    )


def _version_evidence(payload: Mapping[str, Any], call: Call | None) -> dict[str, str]:
    call_payload, metadata = _call_payload(call)
    sources: tuple[Mapping[str, Any], ...] = (
        payload,
        payload.get("versions") if isinstance(payload.get("versions"), Mapping) else {},
        call_payload,
        call_payload.get("versions") if isinstance(call_payload.get("versions"), Mapping) else {},
        metadata,
        metadata.get("versions") if isinstance(metadata.get("versions"), Mapping) else {},
    )
    keys = (
        "deployment_id",
        "code_sha",
        "prompt_version",
        "model_version",
        "tool_schema_version",
        "rag_version",
        "pricing_version",
    )
    result: dict[str, str] = {}
    for key in keys:
        for source in sources:
            text = _nested_text(source, key)
            if text:
                result[key] = text
                break
    if call is not None and call.pricing_version and "pricing_version" not in result:
        result["pricing_version"] = str(call.pricing_version)
    return result


def suspected_introduced_version(payload: Mapping[str, Any], call: Call | None) -> str | None:
    versions = _version_evidence(payload, call)
    for key in ("deployment_id", "code_sha", "prompt_version", "model_version", "tool_schema_version", "rag_version"):
        value = versions.get(key)
        if value:
            return f"{key}:{value[:16]}"
    return None


def enrich_payload_with_trace_context(
    db: Session,
    *,
    tenant_id: str,
    call: Call | None,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    enriched = dict(payload)
    if call is not None:
        enriched.setdefault("agent_name", call.agent_name)
        enriched.setdefault("user_id", call.user_id)
        enriched.setdefault("provider", call.provider)
        enriched.setdefault("model", call.model)
        enriched.setdefault("status", call.status)
        enriched.setdefault("error_code", call.error_code)
        enriched.setdefault("latency_ms", float(call.latency_ms) if call.latency_ms is not None else None)
        enriched.setdefault("cost_usd", float(call.cost_total or 0))

    trace_id = _trace_id_from(enriched, call)
    if trace_id:
        enriched.setdefault("trace_id", trace_id)

    spans = []
    if call is not None or trace_id:
        conditions = [TraceSpan.project_id == tenant_id]
        span_filters = []
        if trace_id:
            span_filters.append(TraceSpan.trace_id == trace_id)
        if call is not None:
            span_filters.append(TraceSpan.call_id == call.id)
        if span_filters:
            rows = db.execute(
                select(TraceSpan)
                .where(*conditions, or_(*span_filters))
                .order_by(TraceSpan.span_index.asc().nullslast(), TraceSpan.started_at.asc(), TraceSpan.id.asc())
                .limit(200)
            ).scalars().all()
            spans = [_span_to_payload(row) for row in rows]

    if spans:
        enriched["trace_graph"] = {
            "trace_id": trace_id,
            "spans": spans,
        }
        if "tool_lifecycle_summary" not in enriched:
            tool_summary = [_tool_summary(span) for span in spans if span.get("span_type") == "tool" or span.get("tool")]
            if tool_summary:
                enriched["tool_lifecycle_summary"] = tool_summary

    versions = _version_evidence(enriched, call)
    if versions:
        existing = enriched.get("versions") if isinstance(enriched.get("versions"), Mapping) else {}
        merged_versions = dict(existing)
        merged_versions.update(versions)
        enriched["versions"] = merged_versions
    return enriched


def _span_to_payload(span: TraceSpan) -> dict[str, Any]:
    return {
        "span_id": span.span_id,
        "parent_span_id": span.parent_span_id,
        "trace_id": span.trace_id,
        "call_id": span.call_id,
        "event_id": span.event_id,
        "span_type": span.span_type,
        "span_name": span.span_name,
        "span_index": span.span_index,
        "agent_name": span.agent_name,
        "provider": span.provider,
        "model": span.model,
        "status": span.status,
        "error_code": span.error_code,
        "latency_ms": float(span.latency_ms) if span.latency_ms is not None else None,
        "cost_usd": float(span.cost_total or 0),
        "input": _safe_json(span.input_json),
        "output": _safe_json(span.output_json),
        "tool": _safe_json(span.tool_json),
        "retrieval": _safe_json(span.retrieval_json),
        "memory": _safe_json(span.memory_json),
        "handoff": _safe_json(span.handoff_json),
        "policy": _safe_json(span.policy_json),
        "outcome": _safe_json(span.outcome_json),
        "versions": _safe_json(span.versions_json),
    }


def _tool_summary(span: Mapping[str, Any]) -> dict[str, Any]:
    tool = span.get("tool") if isinstance(span.get("tool"), Mapping) else {}
    return {
        "tool_name": _first_text(tool.get("name"), tool.get("tool_name"), span.get("span_name")),
        "tool_success": str(span.get("status", "")).lower() not in {"failed", "error", "errored"},
        "tool_input_signature": _first_text(tool.get("input_signature"), tool.get("args_signature")),
        "tool_output_signature": _first_text(tool.get("output_signature")),
        "state_changed": tool.get("state_changed") if isinstance(tool, Mapping) else None,
    }


def issue_evidence_from_diagnosis(
    *,
    diagnosis_item: Mapping[str, Any],
    payload: Mapping[str, Any],
    call: Call | None,
    job: DiagnosisJob | None,
    diagnosis_id: str,
) -> dict[str, Any]:
    category = _first_text(diagnosis_item.get("category")) or "UNKNOWN"
    detector_evidence = (
        diagnosis_item.get("evidence") if isinstance(diagnosis_item.get("evidence"), Mapping) else {}
    )
    summary = _first_text(
        diagnosis_item.get("summary"),
        diagnosis_item.get("title"),
        diagnosis_item.get("what_happened"),
        diagnosis_item.get("root_cause"),
    )
    root_cause = _first_text(diagnosis_item.get("root_cause"), summary)
    fix = diagnosis_item.get("fix") if isinstance(diagnosis_item.get("fix"), Mapping) else {}
    recommended = _first_text(
        diagnosis_item.get("recommended_next_action"),
        fix.get("primary"),
        fix.get("alternative"),
    )
    why = _first_text(diagnosis_item.get("why_it_matters")) or _default_why_it_matters(category)
    what = _first_text(diagnosis_item.get("what_happened"), summary, root_cause) or _default_what_happened(category)
    versions = _version_evidence(payload, call)
    introduced = _first_text(
        diagnosis_item.get("suspected_introduced_version"),
        suspected_introduced_version(payload, call),
    )
    trace_id = _first_text(_nested_text(payload, "trace_id"), getattr(call, "id", None))
    user_id = _first_text(_nested_text(payload, "user_id"), getattr(call, "user_id", None))
    grouping = _first_text(diagnosis_item.get("grouping_signature")) or grouping_signature(
        category=category,
        diagnosis_item=diagnosis_item,
        payload=payload,
        version=introduced,
    )

    compact_detector_evidence = {
        key: value
        for key, value in dict(detector_evidence).items()
        if key in _COMPACT_EVIDENCE_KEYS
    }
    if not compact_detector_evidence and detector_evidence:
        compact_detector_evidence = dict(list(detector_evidence.items())[:8])

    evidence = {
        "confidence": diagnosis_item.get("confidence"),
        "summary": summary,
        "what_happened": what,
        "why_it_matters": why,
        "root_cause": root_cause,
        "recommended_next_action": recommended,
        "grouping_signature": grouping,
        "severity_hint": _first_text(diagnosis_item.get("severity_hint")) or _default_severity_hint(category),
        "blast_radius_hint": diagnosis_item.get("blast_radius_hint"),
        "suspected_introduced_version": introduced,
        "version_evidence": versions,
        "detector": map_failure_code_to_detector(category),
        "detector_evidence": _compact(compact_detector_evidence),
        "trace_id": trace_id,
        "user_id": user_id,
        "workflow_name": _nested_text(payload, "workflow_name", "workflow"),
        "prompt_version": _nested_text(payload, "prompt_version", "prompt_id"),
        "provider": _first_text(getattr(call, "provider", None), _nested_text(payload, "provider")),
        "model": _first_text(getattr(call, "model", None), _nested_text(payload, "model")),
        "diagnosis_id": diagnosis_id,
        "call_id": getattr(call, "id", None) or _nested_text(payload, "call_id"),
    }
    if job is not None and getattr(job, "created_at", None):
        evidence["diagnosed_at"] = job.created_at.isoformat()
    return mask_value(evidence)


def grouping_signature(
    *,
    category: str,
    diagnosis_item: Mapping[str, Any],
    payload: Mapping[str, Any],
    version: str | None,
) -> str:
    evidence = diagnosis_item.get("evidence") if isinstance(diagnosis_item.get("evidence"), Mapping) else {}
    parts = [
        category.upper(),
        _nested_text(payload, "workflow_name", "workflow") or "",
        _nested_text(evidence, "tool_name", "actual_tools", "expected_tool", "required_tool") or "",
        _nested_text(evidence, "violation", "trigger_rule", "required_document", "action", "outcome_status") or "",
        _first_text(diagnosis_item.get("root_cause"), diagnosis_item.get("summary")) or "",
        version or "",
    ]
    normalized = [" ".join(part.lower().split())[:120] for part in parts if part]
    return "|".join(normalized)[:255] or category.upper()


def _default_what_happened(category: str) -> str:
    code = category.upper()
    if "TOOL" in code:
        return "The agent failed around tool choice, execution, or arguments."
    if code == "UNSAFE_ACTION":
        return "The agent attempted a sensitive action without trustworthy policy evidence."
    if code == "TASK_OUTCOME_FAILURE":
        return "The business task failed even though the model call may have completed."
    if "RAG" in code or "RETRIEVAL" in code:
        return "The answer was not grounded in the required retrieval evidence."
    if code == "LOOP_DETECTED":
        return "The agent repeated work without making progress."
    return "A recurring production failure pattern was detected."


def _default_why_it_matters(category: str) -> str:
    code = category.upper()
    if code == "UNSAFE_ACTION":
        return "Sensitive autonomous actions need policy proof before they can be trusted in production."
    if code == "TASK_OUTCOME_FAILURE":
        return "Outcome failures are the user-visible truth even when infrastructure metrics look healthy."
    if "TOOL" in code:
        return "Tool failures break real-world task execution and are strong replay/Golden candidates."
    if "RAG" in code or "RETRIEVAL" in code:
        return "Weak grounding creates confident wrong answers and should be converted into source assertions."
    if code in {"COST_SPIKE", "LATENCY_ANOMALY", "LATENCY_DRIFT"}:
        return "Performance regressions become reliability and spend incidents when they recur."
    return "Repeated failures should become regression tests before the next deploy."


def _default_severity_hint(category: str) -> str:
    code = category.upper()
    if code == "UNSAFE_ACTION":
        return "critical"
    if code in {"TASK_OUTCOME_FAILURE", "TOOL_CALL_FAILURE", "TOOL_ARGUMENT_MISMATCH", "RAG_GROUNDING_FAILURE"}:
        return "high"
    if code in {"TOOL_SELECTION_FAILURE", "SCHEMA_VIOLATION", "LOOP_DETECTED"}:
        return "medium"
    return "low"
