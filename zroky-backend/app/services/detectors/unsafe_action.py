from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.detectors._payload import _as_bool, _as_str, _pick


_UNSAFE_ACTION_CONFIDENCE = 0.94
_SENSITIVE_ACTION_TERMS = (
    "refund",
    "delete",
    "remove",
    "transfer",
    "payment",
    "charge",
    "payout",
    "email",
    "send",
    "password",
    "permission",
    "role",
)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _policy_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    direct = payload.get("policy")
    if isinstance(direct, Mapping):
        records.append(direct)
    for item in _as_list(payload.get("policy_decisions")):
        if isinstance(item, Mapping):
            records.append(item)
    trace = _as_mapping(payload.get("trace_graph"))
    for span in _as_list(trace.get("spans")):
        if not isinstance(span, Mapping):
            continue
        policy = _as_mapping(span.get("policy"))
        if policy or _as_str(span.get("span_type")).lower() == "policy":
            records.append(policy or span)
    return records


def _tool_names(payload: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("tool_calls", "tool_calls_made", "tools", "tool_lifecycle_summary"):
        for item in _as_list(payload.get(key)):
            if isinstance(item, Mapping):
                name = _as_str(item.get("tool_name") or item.get("name") or item.get("tool"))
                if name:
                    names.append(name)
    trace = _as_mapping(payload.get("trace_graph"))
    for span in _as_list(trace.get("spans")):
        if not isinstance(span, Mapping):
            continue
        span_type = _as_str(span.get("span_type")).lower()
        tool = _as_mapping(span.get("tool"))
        if span_type == "tool" or tool:
            name = _as_str(tool.get("name") or tool.get("tool_name") or span.get("span_name"))
            if name:
                names.append(name)
    single = _as_str(_pick(payload, ("tool_name",), ("tool", "name")))
    if single:
        names.append(single)
    return names


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return detect_unsafe_action(payload)


def detect_unsafe_action(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    policies = _policy_records(payload)
    denied = next(
        (
            policy
            for policy in policies
            if _as_str(policy.get("decision") or policy.get("status")).lower()
            in {"deny", "denied", "blocked", "reject", "rejected"}
        ),
        None,
    )
    if denied is not None:
        action = _as_str(denied.get("action") or denied.get("policy_name"), fallback="policy-guarded action")
        return _result(
            action=action,
            reason="a policy decision denied the action",
            trigger_rule="policy_decision_denied",
            policy=denied,
        )

    approved = any(
        _as_str(policy.get("decision") or policy.get("status")).lower()
        in {"allow", "allowed", "approved", "pass", "passed"}
        or _as_bool(policy.get("approved"), fallback=False)
        for policy in policies
    )
    for name in _tool_names(payload):
        normalized = name.lower()
        if not any(term in normalized for term in _SENSITIVE_ACTION_TERMS):
            continue
        if approved:
            return None
        return _result(
            action=name,
            reason="no approving policy decision was captured before a sensitive tool action",
            trigger_rule="sensitive_tool_without_policy_approval",
            policy=None,
        )
    return None


def _result(
    *,
    action: str,
    reason: str,
    trigger_rule: str,
    policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    signature = f"unsafe_action:{action}:{trigger_rule}"
    return {
        "category": "UNSAFE_ACTION",
        "speed_class": "fast",
        "confidence": _UNSAFE_ACTION_CONFIDENCE,
        "what_happened": f"Unsafe or sensitive action path detected for {action}.",
        "why_it_matters": "Autonomous agents must not perform sensitive actions without policy proof or human-approved guardrails.",
        "root_cause": f"{action} is unsafe because {reason}.",
        "recommended_next_action": "Add a policy approval span before the action and replay this trace with the policy assertion.",
        "grouping_signature": signature,
        "severity_hint": "critical",
        "evidence": {
            "action": action,
            "policy_decision": dict(policy) if policy is not None else None,
            "trigger_rule": trigger_rule,
        },
    }
