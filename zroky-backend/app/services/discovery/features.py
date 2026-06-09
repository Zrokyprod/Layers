"""Feature extraction for the Discovery engine.

Pure functions only: `Call`/payload → `BehavioralFeatures`. No DB, no I/O,
no side effects — so it is trivially unit-testable and shared identically by
the production pipeline and the offline harness.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BehavioralFeatures:
    """The per-trace behavioral signal vector extracted from one Call."""

    call_id: str
    project_id: str
    agent_name: str | None
    workflow_name: str | None
    status: str
    error_code: str | None
    latency_ms: float | None
    cost_usd: float
    output_len: int
    output_shape: str
    output_fingerprint: str | None
    finish_reason: str | None
    tool_names: tuple[str, ...]
    outcome_category: str | None


# ── helpers ──────────────────────────────────────────────────────────────────


def _safe_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _safe_mapping(value: Any) -> dict[str, Any]:
    parsed = _safe_json(value)
    return parsed if isinstance(parsed, dict) else {}


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed != parsed or parsed in (float("inf"), float("-inf")):  # NaN/inf
        return default
    return parsed


def _first(record: Mapping[str, Any], payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
    return None


def _tool_name_from_mapping(item: Mapping[str, Any]) -> str | None:
    for key in ("name", "tool_name", "tool", "function_name", "called_tool"):
        value = _as_text(item.get(key))
        if value:
            return value
    function_value = item.get("function")
    if isinstance(function_value, Mapping):
        value = _as_text(function_value.get("name"))
        if value:
            return value
    return None


def _extract_tool_names(raw_value: Any) -> tuple[str, ...]:
    parsed = _safe_json(raw_value)
    if not isinstance(parsed, list):
        return ()
    names: list[str] = []
    for item in parsed:
        if isinstance(item, str):
            name = _as_text(item)
        elif isinstance(item, Mapping):
            name = _tool_name_from_mapping(item)
        else:
            name = None
        if name:
            names.append(name)
    return tuple(names)


def output_shape_of(output: str, fingerprint: str | None) -> str:
    """Coarse structural classification of an output (no PII retained)."""
    text = (output or "").strip()
    if not text:
        return "fingerprint_only" if fingerprint else "empty"
    parsed = _safe_json(text)
    if isinstance(parsed, Mapping):
        keys = sorted(str(key) for key in parsed.keys())[:8]
        return "json:{" + ",".join(keys) + "}"
    if isinstance(parsed, list):
        return "json:list"
    if parsed is not None:
        return f"json:{type(parsed).__name__}"
    word_count = len(text.split())
    if word_count <= 8:
        return "text:short"
    if word_count <= 80:
        return "text:medium"
    return "text:long"


def _outcome_category(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "success" if value else "failure"
    if isinstance(value, Mapping):
        for key in ("category", "status", "verdict", "label", "outcome"):
            category = _outcome_category(value.get(key))
            if category:
                return category
        if "success" in value:
            return _outcome_category(value.get("success"))
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"ok", "pass", "passed", "success", "succeeded", "true", "good"}:
        return "success"
    if text in {"fail", "failed", "failure", "false", "bad", "incorrect", "thumbs_down"}:
        return "failure"
    return text[:40]


def sequence_key(tool_names: Sequence[str]) -> str:
    return " -> ".join(tool_names) if tool_names else "<none>"


def status_is_failure(status: str, error_code: str | None, outcome: str | None) -> bool:
    """Whether a trace represents a failed call (for baseline error-rate)."""
    if error_code:
        return True
    normalized = (status or "").strip().lower()
    if normalized in {"failed", "failure", "error", "errored", "timeout", "cancelled"}:
        return True
    return outcome == "failure"


# ── public ───────────────────────────────────────────────────────────────────


def extract_features(record: Mapping[str, Any]) -> BehavioralFeatures:
    """Build BehavioralFeatures from a Call row (mapping) or its dict form.

    Top-level persisted Call fields win; `payload_json` fills gaps. Robust to
    missing/malformed fields — never raises on a bad record.
    """
    payload = _safe_mapping(record.get("payload_json") or record.get("payload"))
    tool_summary = record.get("tool_lifecycle_summary_json")
    tool_source = tool_summary if tool_summary is not None else _first(
        record, payload, "tool_calls", "tool_calls_made", "tool_lifecycle_summary"
    )

    call_id = _as_text(_first(record, payload, "call_id", "id", "event_id")) or "unknown"
    project_id = _as_text(_first(record, payload, "project_id", "tenant_id")) or "unknown_project"
    output = _as_text(_first(record, payload, "output", "normalized_output", "output_content")) or ""
    fingerprint = _as_text(_first(record, payload, "output_fingerprint"))
    latency_raw = _first(record, payload, "latency_ms", "call_latency_ms")
    cost_raw = _first(
        record, payload, "cost_usd", "cost_total", "actual_cost_usd", "estimated_cost_usd"
    )

    return BehavioralFeatures(
        call_id=call_id,
        project_id=project_id,
        agent_name=_as_text(_first(record, payload, "agent_name")),
        workflow_name=_as_text(_first(record, payload, "workflow_name")),
        status=(_as_text(_first(record, payload, "status")) or "unknown").lower(),
        error_code=_as_text(_first(record, payload, "error_code")),
        latency_ms=_as_float(latency_raw, -1.0) if latency_raw is not None else None,
        cost_usd=_as_float(cost_raw, 0.0),
        output_len=len(output),
        output_shape=output_shape_of(output, fingerprint),
        output_fingerprint=fingerprint,
        finish_reason=_as_text(_first(record, payload, "finish_reason", "stop_reason")),
        tool_names=_extract_tool_names(tool_source),
        outcome_category=_outcome_category(_first(record, payload, "outcome")),
    )


def behavior_key(features: BehavioralFeatures) -> tuple[str, str]:
    """Return (key, specificity) with graceful fallback for missing fields."""
    if features.agent_name and features.workflow_name:
        return (
            f"project={features.project_id}|agent={features.agent_name}|workflow={features.workflow_name}",
            "exact",
        )
    if features.agent_name:
        return (
            f"project={features.project_id}|agent={features.agent_name}|workflow=*",
            "agent_only",
        )
    return (f"project={features.project_id}|agent=*|workflow=*", "project_only")
