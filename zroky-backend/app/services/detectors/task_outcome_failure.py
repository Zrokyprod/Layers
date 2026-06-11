from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.detectors._payload import _as_bool, _as_str, _pick


_TASK_OUTCOME_FAILURE_CONFIDENCE = 0.91


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _outcome_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for key in ("business_outcome", "outcome", "task_outcome"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            records.append(value)
    trace = _as_mapping(payload.get("trace_graph"))
    for span in _as_list(trace.get("spans")):
        if not isinstance(span, Mapping):
            continue
        outcome = _as_mapping(span.get("outcome"))
        if outcome or _as_str(span.get("span_type")).lower() == "outcome":
            records.append(outcome or span)
    return records


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return detect_task_outcome_failure(payload)


def detect_task_outcome_failure(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    for outcome in _outcome_records(payload):
        status = _as_str(outcome.get("status") or outcome.get("result") or outcome.get("outcome")).lower()
        success_value = outcome.get("success")
        failed = (
            status in {"failed", "failure", "unsuccessful", "escalated", "abandoned", "rejected"}
            or _as_bool(success_value, fallback=True) is False
        )
        if not failed:
            continue
        reason = _as_str(
            outcome.get("reason")
            or outcome.get("failure_reason")
            or outcome.get("message")
            or _pick(payload, ("business_outcome_reason",))
        )
        workflow = _as_str(_pick(payload, ("workflow_name",), ("workflow",)), fallback="agent task")
        signature = f"task_outcome_failure:{workflow}:{status or reason[:80] or 'failed'}"
        return {
            "category": "TASK_OUTCOME_FAILURE",
            "speed_class": "fast",
            "confidence": _TASK_OUTCOME_FAILURE_CONFIDENCE,
            "what_happened": f"{workflow} produced a failed business outcome.",
            "why_it_matters": "The model call can be technically successful while the customer-facing task still failed.",
            "root_cause": reason or f"Business outcome status was {status or 'failed'}.",
            "recommended_next_action": "Replay the full task trace and add a Golden that asserts the business outcome, not only final text.",
            "grouping_signature": signature,
            "severity_hint": "high",
            "evidence": {
                "workflow_name": workflow,
                "outcome_status": status or None,
                "reason": reason or None,
                "trigger_rule": "business_outcome_failed",
            },
        }
    return None
