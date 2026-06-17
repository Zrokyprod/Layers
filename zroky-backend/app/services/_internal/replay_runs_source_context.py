import json
from typing import Any
from uuid import uuid4

from app.db.models import Anomaly, Call
from app.services.issue_projection import issue_projection_from_anomaly, projection_evidence

def _safe_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
        return decoded if isinstance(decoded, dict) else {}
    except Exception:
        return {}


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _first_context_value(payloads: list[dict[str, Any]], *keys: str) -> str | None:
    for payload in payloads:
        for key in keys:
            value = _first_text(payload.get(key))
            if value:
                return value
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compact_source_context(context: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in context.items():
        if value is None or value == "":
            continue
        if isinstance(value, str):
            limit = 420 if key == "reason" else 180
            compact[key] = value[:limit]
        else:
            compact[key] = value
    return compact


def _source_context_from_call(call: Call) -> dict[str, Any]:
    payload = _safe_json_object(call.payload_json)
    metadata = _safe_json_object(call.metadata_json)
    evidence = [payload, metadata]
    reason = _first_context_value(
        evidence,
        "failure_reason",
        "error_message",
        "error",
        "reason",
        "summary",
    )
    return _compact_source_context(
        {
            "kind": "call",
            "id": call.id,
            "call_id": call.id,
            "title": f"{call.agent_name or 'Agent'} call {call.id[:12]}",
            "reason": reason or call.error_code or call.status,
            "failure_code": call.error_code,
            "affected_agent": call.agent_name,
            "affected_workflow": _first_context_value(evidence, "workflow_name", "workflow"),
            "last_seen_at": call.created_at.isoformat(),
            "origin": "call",
        }
    )


def _source_context_from_issue(anomaly: Anomaly) -> dict[str, Any]:
    issue = issue_projection_from_anomaly(anomaly)
    evidence = projection_evidence(anomaly)
    legacy = evidence.get("legacy_issue")
    if not isinstance(legacy, dict):
        legacy = {}
    payloads = [evidence, legacy]
    reason = _first_context_value(
        payloads,
        "root_cause",
        "failure_reason",
        "reason",
        "summary",
    )
    agent = _first_context_value(payloads, "agent_name", "affected_agent") or issue.agent_name
    workflow = _first_context_value(payloads, "workflow_name", "workflow", "affected_workflow")
    origin = "discovery" if evidence.get("source") == "discovery" or anomaly.detector == "BEHAVIORAL_DRIFT" else "issue"
    title = _first_context_value(payloads, "title")
    if not title:
        target = workflow or agent or "Affected flow"
        title = f"{target} - {issue.failure_code.replace('_', ' ').lower()}"
    return _compact_source_context(
        {
            "kind": "issue",
            "id": issue.id,
            "issue_id": issue.id,
            "call_id": issue.sample_call_id,
            "title": title,
            "reason": reason or f"{issue.failure_code.replace('_', ' ').lower()} is recurring.",
            "failure_code": issue.failure_code,
            "severity": issue.severity,
            "affected_agent": agent,
            "affected_workflow": workflow,
            "occurrence_count": int(issue.occurrence_count or 0),
            "last_seen_at": issue.last_seen_at.isoformat(),
            "origin": origin,
            "confidence": _float_or_none(evidence.get("confidence")),
            "discovery_signature": _first_text(evidence.get("discovery_signature")),
        }
    )


def _one_click_set_name(*, source_kind: str, source_id: str) -> str:
    return f"One-click replay: {source_kind} {source_id[:12]} {str(uuid4())[:8]}"


