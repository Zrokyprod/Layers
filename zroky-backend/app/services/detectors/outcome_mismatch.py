from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.detectors._payload import _as_str


_OUTCOME_MISMATCH_CONFIDENCE = 0.96


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for key in ("outcome_reconciliation", "reconciliation"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            records.append(value)
    for key in ("outcome_reconciliations", "reconciliation_checks"):
        for value in _as_list(payload.get(key)):
            if isinstance(value, Mapping):
                records.append(value)
    trace = _as_mapping(payload.get("trace_graph"))
    for span in _as_list(trace.get("spans")):
        if not isinstance(span, Mapping):
            continue
        reconciliation = _as_mapping(span.get("outcome_reconciliation"))
        if reconciliation:
            records.append(reconciliation)
    return records


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return detect_outcome_mismatch(payload)


def detect_outcome_mismatch(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    for record in _records(payload):
        verdict = _as_str(record.get("verdict")).lower()
        if verdict != "mismatched":
            continue
        action = _as_str(record.get("action_type"), fallback="agent action")
        system_ref = _as_str(record.get("system_ref") or record.get("external_ref"))
        reason = _as_str(record.get("reason"), fallback="claimed outcome did not match the system of record")
        signature = f"outcome_mismatch:{action}:{system_ref or reason[:80]}"
        return {
            "category": "OUTCOME_MISMATCH",
            "speed_class": "fast",
            "confidence": _OUTCOME_MISMATCH_CONFIDENCE,
            "what_happened": f"{action} reported success but the source-of-record outcome mismatched.",
            "why_it_matters": "Silent-success failures corrupt the system of record while output checks still look green.",
            "root_cause": reason,
            "recommended_next_action": "Block repeat execution, inspect the reconciliation evidence, and add a Golden that asserts the real outcome.",
            "grouping_signature": signature,
            "severity_hint": "critical",
            "evidence": {
                "verdict": verdict,
                "action_type": action,
                "system_ref": system_ref or None,
                "reason": reason,
                "comparison": record.get("comparison"),
            },
        }
    return None
