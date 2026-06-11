from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import Call, RuntimePolicyDecision, TraceSpan
from app.services.pilot import get_or_create_policy, parse_policy_json
from app.services.privacy import mask_payload, mask_text


_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(?:the\s+)?(?:system|developer)\s+prompt", re.IGNORECASE),
    re.compile(r"send\s+(?:this|the)\s+(?:data|secret|token|key)\s+to\s+http", re.IGNORECASE),
    re.compile(r"exfiltrat", re.IGNORECASE),
)

_DEFAULT_SENSITIVE_KEYWORDS = (
    "payment",
    "charge",
    "refund",
    "delete",
    "email",
    "send_email",
    "transfer",
    "payout",
)

_MAX_REASON_LENGTH = 240


@dataclass(frozen=True)
class RuntimePolicyResult:
    decision: RuntimePolicyDecision
    allowed: bool
    requires_approval: bool
    reasons: list[str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _bounded(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    if not rendered:
        return None
    return rendered[:max_length]


def _normalize_tool(value: str | None) -> str:
    return (value or "").strip().lower().replace("-", "_")


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _reason(text: str) -> str:
    return " ".join(text.split())[:_MAX_REASON_LENGTH]


def _is_external_action(payload: dict[str, Any]) -> bool:
    if payload.get("external_action") is True:
        return True
    action = _normalize_tool(_bounded(payload.get("action_type"), max_length=64))
    tool = _normalize_tool(_bounded(payload.get("tool_name"), max_length=255))
    return any(
        marker in action or marker in tool
        for marker in ("email", "http", "webhook", "payment", "refund", "delete", "transfer", "payout")
    )


def _contains_prompt_injection(payload: dict[str, Any]) -> bool:
    if payload.get("prompt_injection_detected") is True:
        return True
    values = [
        payload.get("input_text"),
        payload.get("user_input"),
        payload.get("output_text"),
        payload.get("tool_args"),
        payload.get("metadata"),
    ]
    rendered = " ".join(
        json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value or "")
        for value in values
    )
    return any(pattern.search(rendered) for pattern in _PROMPT_INJECTION_PATTERNS)


def _payload_has_pii(payload: dict[str, Any]) -> bool:
    if payload.get("pii_detected") is True:
        return True
    candidates = {
        "input_text": payload.get("input_text"),
        "output_text": payload.get("output_text"),
        "tool_args": payload.get("tool_args"),
        "metadata": payload.get("metadata"),
    }
    masked = mask_payload(candidates)
    return masked != candidates


def _is_sensitive_action(payload: dict[str, Any], policy: dict[str, Any]) -> bool:
    action = _normalize_tool(_bounded(payload.get("action_type"), max_length=64))
    tool = _normalize_tool(_bounded(payload.get("tool_name"), max_length=255))
    configured = policy.get("runtime_sensitive_tools")
    keywords = configured if isinstance(configured, list) and configured else list(_DEFAULT_SENSITIVE_KEYWORDS)
    normalized_keywords = [_normalize_tool(str(item)) for item in keywords if str(item).strip()]
    return any(keyword and (keyword in action or keyword in tool) for keyword in normalized_keywords)


def _approval_expiry(policy: dict[str, Any]) -> datetime:
    ttl = _as_int(policy.get("runtime_approval_ttl_minutes")) or 60
    return _now() + timedelta(minutes=max(1, ttl))


def _find_reusable_pending_approval(
    db: Session,
    *,
    project_id: str,
    payload: dict[str, Any],
) -> RuntimePolicyDecision | None:
    trace_id = _bounded(payload.get("trace_id"), max_length=128)
    action_type = _bounded(payload.get("action_type"), max_length=64)
    tool_name = _bounded(payload.get("tool_name"), max_length=255)
    if not trace_id:
        return None
    now = _now()
    return db.execute(
        select(RuntimePolicyDecision)
        .where(
            RuntimePolicyDecision.project_id == project_id,
            RuntimePolicyDecision.trace_id == trace_id,
            RuntimePolicyDecision.status == "pending_approval",
            RuntimePolicyDecision.action_type == action_type,
            RuntimePolicyDecision.tool_name == tool_name,
            RuntimePolicyDecision.expires_at > now,
        )
        .order_by(desc(RuntimePolicyDecision.created_at))
        .limit(1)
    ).scalar_one_or_none()


def _valid_approval(
    db: Session,
    *,
    project_id: str,
    approval_id: str | None,
    payload: dict[str, Any],
) -> RuntimePolicyDecision | None:
    if not approval_id:
        return None
    approval = db.execute(
        select(RuntimePolicyDecision).where(
            RuntimePolicyDecision.project_id == project_id,
            RuntimePolicyDecision.id == approval_id,
            RuntimePolicyDecision.status == "approved",
        )
    ).scalar_one_or_none()
    if approval is None:
        return None
    if approval.expires_at is not None:
        expires_at = approval.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= _now():
            approval.status = "expired"
            db.add(approval)
            db.flush()
            return None
    action_type = _bounded(payload.get("action_type"), max_length=64)
    tool_name = _bounded(payload.get("tool_name"), max_length=255)
    if approval.action_type != action_type or approval.tool_name != tool_name:
        return None
    return approval


def _persist_trace_policy_span(
    db: Session,
    *,
    project_id: str,
    decision: RuntimePolicyDecision,
    request_payload: dict[str, Any],
) -> None:
    trace_id = decision.trace_id
    if not trace_id:
        return
    now = _now()
    policy_payload = {
        "decision_id": decision.id,
        "decision": decision.decision,
        "status": decision.status,
        "reasons": _json_loads(decision.reasons_json, []),
        "action_type": decision.action_type,
        "tool_name": decision.tool_name,
        "requires_approval": decision.status == "pending_approval",
        "approval_expires_at": decision.expires_at.isoformat() if decision.expires_at else None,
    }
    span = TraceSpan(
        id=str(uuid4()),
        project_id=project_id,
        trace_id=trace_id,
        span_id=f"policy:{decision.id}",
        parent_span_id=_bounded(request_payload.get("span_id"), max_length=128),
        call_id=decision.call_id,
        event_id=f"policy:{decision.id}",
        span_type="policy",
        span_name="runtime_policy_gate",
        agent_name=decision.agent_name,
        status="blocked" if decision.status in {"blocked", "pending_approval", "rejected"} else "completed",
        started_at=now,
        ended_at=now,
        latency_ms=0,
        cost_total=0,
        policy_json=_json_dumps(policy_payload),
        payload_json=_json_dumps(
            {
                "policy": policy_payload,
                "request": mask_payload(request_payload),
            }
        ),
        capture_source="runtime_policy_gate",
        masking_version="backend_privacy_v1",
        pii_masked=True,
    )
    db.add(span)
    db.flush()


def _update_trace_policy_span(
    db: Session,
    *,
    project_id: str,
    decision: RuntimePolicyDecision,
) -> None:
    if not decision.trace_id:
        return
    span = db.execute(
        select(TraceSpan).where(
            TraceSpan.project_id == project_id,
            TraceSpan.span_id == f"policy:{decision.id}",
        )
    ).scalar_one_or_none()
    if span is None:
        return
    policy_payload = {
        "decision_id": decision.id,
        "decision": decision.decision,
        "status": decision.status,
        "reasons": _json_loads(decision.reasons_json, []),
        "action_type": decision.action_type,
        "tool_name": decision.tool_name,
        "requires_approval": decision.status == "pending_approval",
        "approval_expires_at": decision.expires_at.isoformat() if decision.expires_at else None,
        "resolved_at": decision.resolved_at.isoformat() if decision.resolved_at else None,
        "resolved_by": decision.resolved_by,
        "resolution_reason": decision.resolution_reason,
    }
    span.status = "blocked" if decision.status in {"blocked", "pending_approval", "rejected"} else "completed"
    span.policy_json = _json_dumps(policy_payload)
    span.payload_json = _json_dumps(
        {
            "policy": policy_payload,
            "request": _json_loads(decision.request_json, {}),
        }
    )
    db.add(span)
    db.flush()


def _existing_call_id(db: Session, *, project_id: str, call_id: str | None) -> str | None:
    if not call_id:
        return None
    exists = db.execute(
        select(Call.id).where(
            Call.project_id == project_id,
            Call.id == call_id,
        )
    ).scalar_one_or_none()
    return exists


def _create_decision(
    db: Session,
    *,
    project_id: str,
    payload: dict[str, Any],
    policy: dict[str, Any],
    decision: str,
    status: str,
    reasons: list[str],
    expires_at: datetime | None = None,
) -> RuntimePolicyDecision:
    masked_request = mask_payload(payload)
    row = RuntimePolicyDecision(
        id=str(uuid4()),
        project_id=project_id,
        trace_id=_bounded(payload.get("trace_id"), max_length=128),
        call_id=_existing_call_id(
            db,
            project_id=project_id,
            call_id=_bounded(payload.get("call_id"), max_length=64),
        ),
        agent_name=_bounded(payload.get("agent_name"), max_length=255),
        role=_bounded(payload.get("role"), max_length=64),
        action_type=_bounded(payload.get("action_type"), max_length=64),
        tool_name=_bounded(payload.get("tool_name"), max_length=255),
        decision=decision,
        status=status,
        reasons_json=_json_dumps([_reason(item) for item in reasons]),
        request_json=_json_dumps(masked_request),
        policy_snapshot_json=_json_dumps(policy),
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    _persist_trace_policy_span(db, project_id=project_id, decision=row, request_payload=payload)
    return row


def evaluate_runtime_policy(
    db: Session,
    *,
    project_id: str,
    payload: dict[str, Any],
) -> RuntimePolicyResult:
    policy_row = get_or_create_policy(db, project_id=project_id)
    policy = parse_policy_json(policy_row.policy_json)

    reasons: list[str] = []
    if policy.get("runtime_enabled") is False:
        row = _create_decision(
            db,
            project_id=project_id,
            payload=payload,
            policy=policy,
            decision="allow",
            status="allowed",
            reasons=["runtime policy gate disabled for this project"],
        )
        db.commit()
        db.refresh(row)
        return RuntimePolicyResult(row, allowed=True, requires_approval=False, reasons=["runtime policy gate disabled for this project"])

    if policy.get("kill_switch") is True:
        reasons.append("project kill switch is enabled")

    tool_name = _bounded(payload.get("tool_name"), max_length=255)
    allowed_tools = policy.get("runtime_allowed_tools")
    if isinstance(allowed_tools, list) and allowed_tools and tool_name:
        normalized_allowed = {_normalize_tool(str(item)) for item in allowed_tools}
        if _normalize_tool(tool_name) not in normalized_allowed:
            reasons.append(f"tool {tool_name!r} is not allowlisted for this project")

    tool_call_count = _as_int(payload.get("tool_call_count"))
    max_tool_calls = _as_int(policy.get("runtime_max_tool_calls"))
    if tool_call_count is not None and max_tool_calls is not None and max_tool_calls >= 0 and tool_call_count > max_tool_calls:
        reasons.append(f"tool call count {tool_call_count} exceeds runtime limit {max_tool_calls}")

    retry_count = _as_int(payload.get("retry_count"))
    max_retries = _as_int(policy.get("runtime_max_retries"))
    if retry_count is not None and max_retries is not None and max_retries >= 0 and retry_count > max_retries:
        reasons.append(f"retry count {retry_count} exceeds runtime limit {max_retries}")

    estimated_cost = _as_float(payload.get("estimated_cost_usd"))
    max_cost = _as_float(policy.get("runtime_max_cost_usd"))
    if estimated_cost is not None and max_cost is not None and max_cost >= 0 and estimated_cost > max_cost:
        reasons.append(f"estimated action cost ${estimated_cost:.6f} exceeds runtime limit ${max_cost:.6f}")

    external_action = _is_external_action(payload)
    if policy.get("runtime_block_pii_leak") is True and external_action and _payload_has_pii(payload):
        reasons.append("external action payload contains PII or secret-shaped data")

    if (
        policy.get("runtime_block_prompt_injected_external_action") is True
        and external_action
        and _contains_prompt_injection(payload)
    ):
        reasons.append("prompt-injection-shaped instruction attempted an external action")

    if reasons:
        row = _create_decision(
            db,
            project_id=project_id,
            payload=payload,
            policy=policy,
            decision="block",
            status="blocked",
            reasons=reasons,
        )
        db.commit()
        db.refresh(row)
        return RuntimePolicyResult(row, allowed=False, requires_approval=False, reasons=reasons)

    if _is_sensitive_action(payload, policy) and policy.get("runtime_sensitive_actions_require_approval") is True:
        approval = _valid_approval(
            db,
            project_id=project_id,
            approval_id=_bounded(payload.get("approval_id"), max_length=36),
            payload=payload,
        )
        if approval is not None:
            approved_reason = f"human approval {approval.id} accepted"
            row = _create_decision(
                db,
                project_id=project_id,
                payload=payload,
                policy=policy,
                decision="allow",
                status="allowed",
                reasons=[approved_reason],
            )
            db.commit()
            db.refresh(row)
            return RuntimePolicyResult(row, allowed=True, requires_approval=False, reasons=[approved_reason])

        pending = _find_reusable_pending_approval(db, project_id=project_id, payload=payload)
        if pending is not None:
            reasons = _json_loads(pending.reasons_json, ["sensitive action requires human approval"])
            return RuntimePolicyResult(pending, allowed=False, requires_approval=True, reasons=reasons)

        reasons = ["sensitive action requires human approval before execution"]
        row = _create_decision(
            db,
            project_id=project_id,
            payload=payload,
            policy=policy,
            decision="requires_approval",
            status="pending_approval",
            reasons=reasons,
            expires_at=_approval_expiry(policy),
        )
        db.commit()
        db.refresh(row)
        return RuntimePolicyResult(row, allowed=False, requires_approval=True, reasons=reasons)

    row = _create_decision(
        db,
        project_id=project_id,
        payload=payload,
        policy=policy,
        decision="allow",
        status="allowed",
        reasons=["runtime policy checks passed"],
    )
    db.commit()
    db.refresh(row)
    return RuntimePolicyResult(row, allowed=True, requires_approval=False, reasons=["runtime policy checks passed"])


def list_runtime_policy_decisions(
    db: Session,
    *,
    project_id: str,
    status: str | None = None,
    limit: int = 50,
) -> list[RuntimePolicyDecision]:
    query = select(RuntimePolicyDecision).where(RuntimePolicyDecision.project_id == project_id)
    if status:
        query = query.where(RuntimePolicyDecision.status == status)
    return list(
        db.execute(
            query.order_by(desc(RuntimePolicyDecision.created_at), desc(RuntimePolicyDecision.id)).limit(limit)
        ).scalars()
    )


def resolve_runtime_policy_decision(
    db: Session,
    *,
    project_id: str,
    decision_id: str,
    approved: bool,
    actor: str | None,
    reason: str,
) -> RuntimePolicyDecision | None:
    row = db.execute(
        select(RuntimePolicyDecision).where(
            RuntimePolicyDecision.project_id == project_id,
            RuntimePolicyDecision.id == decision_id,
            RuntimePolicyDecision.status == "pending_approval",
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.status = "approved" if approved else "rejected"
    row.decision = "allow" if approved else "block"
    row.resolved_at = _now()
    row.resolved_by = actor
    row.resolution_reason = mask_text(reason.strip())[:1000]
    db.add(row)
    db.flush()
    _update_trace_policy_span(db, project_id=project_id, decision=row)
    db.commit()
    db.refresh(row)
    return row
