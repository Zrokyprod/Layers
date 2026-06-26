from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import Call, RuntimePolicyAuditEvent, RuntimePolicyDecision, TraceSpan
from app.services.pilot import get_or_create_policy, parse_policy_json
from app.services.privacy import mask_payload, mask_text, mask_value


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
_AUDIT_EVENT_ORDER = {
    "allowed": 0,
    "blocked": 0,
    "approval_requested": 0,
    "approval_recorded": 1,
    "approved": 2,
    "rejected": 2,
    "expired": 2,
    "approval_consumed": 3,
}


@dataclass(frozen=True)
class RuntimePolicyResult:
    decision: RuntimePolicyDecision
    allowed: bool
    requires_approval: bool
    reasons: list[str]


class RuntimePolicyApprovalConflict(ValueError):
    """Raised when a pending approval cannot accept the supplied approver."""


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


def _masked_any(value: Any) -> Any:
    return mask_value(value)


def _business_impact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    explicit = payload.get("business_impact")
    if isinstance(explicit, dict):
        impact = mask_payload(explicit)
    elif explicit is not None:
        impact = {"summary": mask_text(str(explicit))}
    else:
        impact = {}

    for source_key, target_key in (
        ("business_impact_summary", "summary"),
        ("impact_summary", "summary"),
        ("impact_usd", "estimated_value_usd"),
        ("estimated_cost_usd", "estimated_cost_usd"),
        ("customer_id", "customer_id"),
        ("account_id", "account_id"),
        ("order_id", "order_id"),
        ("resource_id", "resource_id"),
    ):
        if source_key in payload and target_key not in impact:
            impact[target_key] = _masked_any(payload.get(source_key))

    tool_args = payload.get("tool_args")
    if isinstance(tool_args, dict):
        for key in ("customer_id", "account_id", "order_id", "invoice_id", "ticket_id", "resource_id", "amount", "currency"):
            if key in tool_args and key not in impact:
                impact[key] = _masked_any(tool_args.get(key))

    action = _normalize_tool(_bounded(payload.get("action_type"), max_length=64))
    tool = _normalize_tool(_bounded(payload.get("tool_name"), max_length=255))
    if any(marker in action or marker in tool for marker in ("delete", "refund", "payment", "transfer", "payout")):
        impact.setdefault("risk_category", "destructive_or_financial")
    elif any(marker in action or marker in tool for marker in ("email", "send_email", "webhook", "http")):
        impact.setdefault("risk_category", "external_communication")

    return impact


def _tool_args(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("tool_args")
    return value if isinstance(value, dict) else {}


def _amount_usd(payload: dict[str, Any]) -> float | None:
    candidates: list[Any] = [
        payload.get("amount_usd"),
        payload.get("impact_usd"),
    ]
    business_impact = payload.get("business_impact")
    if isinstance(business_impact, dict):
        candidates.extend(
            [
                business_impact.get("amount_usd"),
                business_impact.get("estimated_value_usd"),
                business_impact.get("impact_usd"),
            ]
        )
    tool_args = _tool_args(payload)
    candidates.extend([tool_args.get("amount_usd"), tool_args.get("amount")])
    nested_parameters = tool_args.get("parameters")
    if isinstance(nested_parameters, dict):
        candidates.extend([nested_parameters.get("amount_usd"), nested_parameters.get("amount")])
    for candidate in candidates:
        amount = _as_float(candidate)
        if amount is not None:
            return amount

    amount_minor = _as_float(tool_args.get("amount_minor"))
    currency = str(tool_args.get("currency") or payload.get("currency") or "").strip().upper()
    if amount_minor is not None and currency in {"USD", ""}:
        return amount_minor / 100.0
    if isinstance(nested_parameters, dict):
        nested_amount_minor = _as_float(nested_parameters.get("amount_minor"))
        nested_currency = str(nested_parameters.get("currency") or payload.get("currency") or "").strip().upper()
        if nested_amount_minor is not None and nested_currency in {"USD", ""}:
            return nested_amount_minor / 100.0
    return None


def _is_refund_or_transfer(payload: dict[str, Any]) -> bool:
    action = _normalize_tool(_bounded(payload.get("action_type"), max_length=64))
    tool = _normalize_tool(_bounded(payload.get("tool_name"), max_length=255))
    operation = _normalize_tool(_bounded(payload.get("operation_kind"), max_length=32))
    return any(marker in action or marker in tool or marker in operation for marker in ("refund", "transfer", "payment"))


def _is_production_deploy(payload: dict[str, Any]) -> bool:
    environment = str(payload.get("environment") or "").strip().lower()
    if environment not in {"prod", "production"}:
        return False
    action = _normalize_tool(_bounded(payload.get("action_type"), max_length=64))
    tool = _normalize_tool(_bounded(payload.get("tool_name"), max_length=255))
    operation = _normalize_tool(_bounded(payload.get("operation_kind"), max_length=32))
    return "deploy" in action or "deploy" in tool or operation == "deploy"


def _changed_recipient(payload: dict[str, Any]) -> bool:
    if payload.get("recipient_changed") is True or payload.get("changed_recipient") is True:
        return True
    tool_args = _tool_args(payload)
    if tool_args.get("recipient_changed") is True or tool_args.get("changed_recipient") is True:
        return True
    before = tool_args.get("previous_recipient") or tool_args.get("old_recipient") or payload.get("previous_recipient")
    after = tool_args.get("new_recipient") or tool_args.get("recipient") or payload.get("new_recipient")
    return before is not None and after is not None and str(before).strip().lower() != str(after).strip().lower()


def _first_launch_block_reasons(payload: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if policy.get("runtime_changed_recipient_deny") is True and _changed_recipient(payload):
        reasons.append("customer-visible recipient changed; deny until a new action intent is created")
    return reasons


def _first_launch_approval_reasons(payload: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    amount = _amount_usd(payload)
    approval_threshold = _as_float(policy.get("runtime_amount_approval_threshold_usd"))
    deny_threshold = _as_float(policy.get("runtime_amount_deny_threshold_usd"))
    if (
        amount is not None
        and approval_threshold is not None
        and _is_refund_or_transfer(payload)
        and amount > approval_threshold
        and (deny_threshold is None or amount <= deny_threshold)
    ):
        reasons.append(f"refund or transfer amount ${amount:.2f} exceeds approval threshold ${approval_threshold:.2f}")
    if (
        amount is not None
        and deny_threshold is not None
        and _is_refund_or_transfer(payload)
        and amount > deny_threshold
    ):
        reasons.append(
            f"refund or transfer amount ${amount:.2f} exceeds dual-approval threshold ${deny_threshold:.2f}; two distinct approvals required"
        )

    if policy.get("runtime_production_deploys_require_approval") is True and _is_production_deploy(payload):
        reasons.append("production deploy requires human approval before execution")
    return reasons


def _required_approval_count(payload: dict[str, Any], policy: dict[str, Any], approval_reasons: list[str]) -> int:
    if not approval_reasons:
        return 0
    amount = _amount_usd(payload)
    deny_threshold = _as_float(policy.get("runtime_amount_deny_threshold_usd"))
    if (
        amount is not None
        and deny_threshold is not None
        and _is_refund_or_transfer(payload)
        and amount > deny_threshold
    ):
        return 2
    return 1


def _intended_action_payload(payload: dict[str, Any]) -> dict[str, Any]:
    action_type = _bounded(payload.get("action_type"), max_length=64)
    tool_name = _bounded(payload.get("tool_name"), max_length=255)
    agent = _bounded(payload.get("agent_name"), max_length=255)
    summary_parts = []
    if agent:
        summary_parts.append(f"{agent} intends")
    else:
        summary_parts.append("agent intends")
    summary_parts.append(f"to run {tool_name or action_type or 'action'}")
    if action_type and tool_name and action_type != tool_name:
        summary_parts.append(f"for {action_type}")
    return {
        "summary": " ".join(summary_parts),
        "action_type": action_type,
        "tool_name": tool_name,
        "tool_args": _masked_any(payload.get("tool_args")),
        "external_action": bool(payload.get("external_action")),
        "approval_id": _bounded(payload.get("approval_id"), max_length=36),
    }


def _trace_context_payload(db: Session, *, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    trace_id = _bounded(payload.get("trace_id"), max_length=128)
    call_id = _bounded(payload.get("call_id"), max_length=64)
    context = {
        "trace_id": trace_id,
        "span_id": _bounded(payload.get("span_id"), max_length=128),
        "call_id": call_id,
        "agent_name": _bounded(payload.get("agent_name"), max_length=255),
        "role": _bounded(payload.get("role"), max_length=64),
        "workflow_name": _bounded(payload.get("workflow_name") or payload.get("workflow"), max_length=255),
        "user_id": _masked_any(payload.get("user_id")),
        "environment": _bounded(payload.get("environment"), max_length=64),
    }
    if call_id:
        call = db.execute(
            select(Call).where(
                Call.project_id == project_id,
                Call.id == call_id,
            )
        ).scalar_one_or_none()
        if call is not None:
            context.update(
                {
                    "call_status": call.status,
                    "call_type": call.call_type,
                    "provider": call.provider,
                    "model": call.model,
                    "call_created_at": call.created_at.isoformat() if call.created_at else None,
                    "call_user_id": _masked_any(call.user_id),
                }
            )
            if not context.get("agent_name"):
                context["agent_name"] = call.agent_name
    return {key: value for key, value in context.items() if value not in (None, "", {})}


def _policy_hit_payload(
    payload: dict[str, Any],
    policy: dict[str, Any],
    *,
    decision: str,
    status: str,
    reasons: list[str],
    required_approval_count: int = 0,
) -> dict[str, Any]:
    return {
        "policy": "runtime_policy_gate",
        "decision": decision,
        "status": status,
        "risk_reasons": [_reason(item) for item in reasons],
        "sensitive_action": _is_sensitive_action(payload, policy),
        "external_action": _is_external_action(payload),
        "limits": {
            "max_tool_calls": policy.get("runtime_max_tool_calls"),
            "max_retries": policy.get("runtime_max_retries"),
            "max_cost_usd": policy.get("runtime_max_cost_usd"),
        },
        "requires_human_approval": status == "pending_approval",
        "first_launch_rules": {
            "amount_usd": _amount_usd(payload),
            "amount_approval_threshold_usd": policy.get("runtime_amount_approval_threshold_usd"),
            "amount_deny_threshold_usd": policy.get("runtime_amount_deny_threshold_usd"),
            "production_deploys_require_approval": policy.get("runtime_production_deploys_require_approval"),
            "changed_recipient_deny": policy.get("runtime_changed_recipient_deny"),
        },
        "approval_requirements": {
            "required_approval_count": required_approval_count,
            "dual_approval_required": required_approval_count >= 2,
        },
    }


def _approval_scope_payload(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "trace_id": _bounded(payload.get("trace_id"), max_length=128),
        "agent_name": _bounded(payload.get("agent_name"), max_length=255),
        "role": _bounded(payload.get("role"), max_length=64),
        "action_type": _bounded(payload.get("action_type"), max_length=64),
        "tool_name": _bounded(payload.get("tool_name"), max_length=255),
        "tool_args": _masked_any(payload.get("tool_args")),
        "external_action": bool(payload.get("external_action")),
        "business_impact": _business_impact_payload(payload),
    }


def _approval_scope_hash(project_id: str, payload: dict[str, Any]) -> str:
    rendered = _json_dumps(_approval_scope_payload(project_id, payload))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _decision_snapshot(row: RuntimePolicyDecision) -> dict[str, Any]:
    return {
        "id": row.id,
        "decision": row.decision,
        "status": row.status,
        "trace_id": row.trace_id,
        "agent_name": row.agent_name,
        "action_type": row.action_type,
        "tool_name": row.tool_name,
        "reasons": _json_loads(row.reasons_json, []),
        "approval_scope_hash": row.approval_scope_hash,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "resolved_by": row.resolved_by,
        "consumed_at": row.consumed_at.isoformat() if row.consumed_at else None,
        "consumed_by_decision_id": row.consumed_by_decision_id,
        "required_approval_count": row.required_approval_count,
        "approval_count": row.approval_count,
        "approver_subjects": _json_loads(row.approver_subjects_json, []),
    }


def _audit_event_type(*, decision: str, status: str) -> str:
    if status == "pending_approval":
        return "approval_requested"
    if status == "blocked":
        return "blocked"
    if status == "allowed":
        return "allowed"
    if status in {"approved", "rejected", "expired"}:
        return status
    return decision


def _log_audit_event(
    db: Session,
    *,
    decision: RuntimePolicyDecision,
    event_type: str,
    actor: str | None = None,
    reason: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> RuntimePolicyAuditEvent:
    event = RuntimePolicyAuditEvent(
        id=str(uuid4()),
        project_id=decision.project_id,
        decision_id=decision.id,
        event_type=event_type,
        actor=_bounded(actor, max_length=128),
        reason=mask_text(reason)[:1000] if reason else None,
        before_json=_json_dumps(before) if before is not None else None,
        after_json=_json_dumps(after if after is not None else _decision_snapshot(decision)),
    )
    db.add(event)
    db.flush()
    return event


def _find_reusable_pending_approval(
    db: Session,
    *,
    project_id: str,
    payload: dict[str, Any],
) -> RuntimePolicyDecision | None:
    scope_hash = _approval_scope_hash(project_id, payload)
    now = _now()
    return db.execute(
        select(RuntimePolicyDecision)
        .where(
            RuntimePolicyDecision.project_id == project_id,
            RuntimePolicyDecision.status == "pending_approval",
            RuntimePolicyDecision.approval_scope_hash == scope_hash,
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
    if approval.consumed_at is not None:
        return None
    if (approval.required_approval_count or 0) > 0 and approval.approval_count < approval.required_approval_count:
        return None
    if approval.expires_at is not None:
        expires_at = approval.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= _now():
            before = _decision_snapshot(approval)
            approval.status = "expired"
            db.add(approval)
            db.flush()
            _log_audit_event(
                db,
                decision=approval,
                event_type="expired",
                reason="approval expired before use",
                before=before,
                after=_decision_snapshot(approval),
            )
            _update_trace_policy_span(db, project_id=project_id, decision=approval)
            return None
    expected_scope_hash = _approval_scope_hash(project_id, payload)
    if approval.approval_scope_hash != expected_scope_hash:
        return None
    return approval


def _approver_subjects(row: RuntimePolicyDecision) -> list[str]:
    loaded = _json_loads(row.approver_subjects_json, [])
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded if str(item).strip()]


def _set_approver_subjects(row: RuntimePolicyDecision, subjects: list[str]) -> None:
    row.approver_subjects_json = _json_dumps(subjects)


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
        "intended_action": _json_loads(decision.intended_action_json, {}),
        "trace_context": _json_loads(decision.trace_context_json, {}),
        "policy_hit": _json_loads(decision.policy_hit_json, {}),
        "business_impact": _json_loads(decision.business_impact_json, {}),
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
        "consumed_at": decision.consumed_at.isoformat() if decision.consumed_at else None,
        "consumed_by_decision_id": decision.consumed_by_decision_id,
        "intended_action": _json_loads(decision.intended_action_json, {}),
        "trace_context": _json_loads(decision.trace_context_json, {}),
        "policy_hit": _json_loads(decision.policy_hit_json, {}),
        "business_impact": _json_loads(decision.business_impact_json, {}),
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
    required_approval_count: int = 0,
) -> RuntimePolicyDecision:
    masked_request = mask_payload(payload)
    intended_action = _intended_action_payload(payload)
    trace_context = _trace_context_payload(db, project_id=project_id, payload=payload)
    business_impact = _business_impact_payload(payload)
    policy_hit = _policy_hit_payload(
        payload,
        policy,
        decision=decision,
        status=status,
        reasons=reasons,
        required_approval_count=required_approval_count,
    )
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
        intended_action_json=_json_dumps(intended_action),
        trace_context_json=_json_dumps(trace_context),
        policy_hit_json=_json_dumps(policy_hit),
        business_impact_json=_json_dumps(business_impact),
        approval_scope_hash=_approval_scope_hash(project_id, payload),
        required_approval_count=required_approval_count,
        approval_count=0,
        approver_subjects_json=_json_dumps([]),
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    _persist_trace_policy_span(db, project_id=project_id, decision=row, request_payload=payload)
    _log_audit_event(
        db,
        decision=row,
        event_type=_audit_event_type(decision=decision, status=status),
        actor=_bounded(payload.get("actor") or payload.get("agent_name"), max_length=128),
        reason="; ".join([_reason(item) for item in reasons]),
    )
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

    reasons.extend(_first_launch_block_reasons(payload, policy))

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

    approval_reasons = _first_launch_approval_reasons(payload, policy)
    if _is_sensitive_action(payload, policy) and policy.get("runtime_sensitive_actions_require_approval") is True:
        approval_reasons.insert(0, "sensitive action requires human approval before execution")
    required_approval_count = _required_approval_count(payload, policy, approval_reasons)

    if approval_reasons:
        approval = _valid_approval(
            db,
            project_id=project_id,
            approval_id=_bounded(payload.get("approval_id"), max_length=36),
            payload=payload,
        )
        if approval is not None:
            before_approval = _decision_snapshot(approval)
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
            approval.consumed_at = _now()
            approval.consumed_by_decision_id = row.id
            db.add(approval)
            db.flush()
            _log_audit_event(
                db,
                decision=approval,
                event_type="approval_consumed",
                actor=_bounded(payload.get("actor") or payload.get("agent_name"), max_length=128),
                reason=approved_reason,
                before=before_approval,
                after=_decision_snapshot(approval),
            )
            _update_trace_policy_span(db, project_id=project_id, decision=approval)
            db.commit()
            db.refresh(row)
            return RuntimePolicyResult(row, allowed=True, requires_approval=False, reasons=[approved_reason])

        pending = _find_reusable_pending_approval(db, project_id=project_id, payload=payload)
        if pending is not None:
            reasons = _json_loads(pending.reasons_json, approval_reasons)
            return RuntimePolicyResult(pending, allowed=False, requires_approval=True, reasons=reasons)

        row = _create_decision(
            db,
            project_id=project_id,
            payload=payload,
            policy=policy,
            decision="requires_approval",
            status="pending_approval",
            reasons=approval_reasons,
            expires_at=_approval_expiry(policy),
            required_approval_count=required_approval_count,
        )
        db.commit()
        db.refresh(row)
        return RuntimePolicyResult(row, allowed=False, requires_approval=True, reasons=approval_reasons)

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


def list_runtime_policy_audit_events(
    db: Session,
    *,
    project_id: str,
    decision_ids: list[str],
) -> dict[str, list[RuntimePolicyAuditEvent]]:
    if not decision_ids:
        return {}
    rows = list(
        db.execute(
            select(RuntimePolicyAuditEvent)
            .where(
                RuntimePolicyAuditEvent.project_id == project_id,
                RuntimePolicyAuditEvent.decision_id.in_(decision_ids),
            )
            .order_by(RuntimePolicyAuditEvent.created_at.asc(), RuntimePolicyAuditEvent.id.asc())
        ).scalars()
    )
    grouped: dict[str, list[RuntimePolicyAuditEvent]] = {}
    for row in rows:
        grouped.setdefault(row.decision_id, []).append(row)
    for events in grouped.values():
        events.sort(
            key=lambda event: (
                event.created_at,
                _AUDIT_EVENT_ORDER.get(event.event_type, 99),
                event.id,
            )
        )
    return grouped


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
    before = _decision_snapshot(row)
    actor_key = _bounded(actor, max_length=128) or "anonymous-approver"
    cleaned_reason = mask_text(reason.strip())[:1000]
    if not approved:
        row.status = "rejected"
        row.decision = "block"
        row.resolved_at = _now()
        row.resolved_by = actor_key
        row.resolution_reason = cleaned_reason
        db.add(row)
        db.flush()
        _log_audit_event(
            db,
            decision=row,
            event_type="rejected",
            actor=actor_key,
            reason=reason,
            before=before,
            after=_decision_snapshot(row),
        )
        _update_trace_policy_span(db, project_id=project_id, decision=row)
        db.commit()
        db.refresh(row)
        return row

    approvers = _approver_subjects(row)
    if actor_key in approvers:
        raise RuntimePolicyApprovalConflict("A second approval must come from a distinct approver.")

    approvers.append(actor_key)
    required_count = max(1, row.required_approval_count or 1)
    row.required_approval_count = required_count
    row.approval_count = len(approvers)
    _set_approver_subjects(row, approvers)
    if row.approval_count >= required_count:
        row.status = "approved"
        row.decision = "allow"
        row.resolved_at = _now()
        row.resolved_by = actor_key
        row.resolution_reason = cleaned_reason
        event_type = "approved"
    else:
        row.status = "pending_approval"
        row.decision = "requires_approval"
        row.resolved_at = None
        row.resolved_by = None
        row.resolution_reason = None
        event_type = "approval_recorded"
    db.add(row)
    db.flush()
    _log_audit_event(
        db,
        decision=row,
        event_type=event_type,
        actor=actor_key,
        reason=reason,
        before=before,
        after=_decision_snapshot(row),
    )
    _update_trace_policy_span(db, project_id=project_id, decision=row)
    db.commit()
    db.refresh(row)
    return row


def expire_runtime_policy_decision(
    db: Session,
    *,
    project_id: str,
    decision_id: str,
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
    before = _decision_snapshot(row)
    actor_key = _bounded(actor, max_length=128) or "system"
    row.status = "expired"
    row.decision = "block"
    row.resolved_at = _now()
    row.resolved_by = actor_key
    row.resolution_reason = mask_text(reason.strip())[:1000]
    db.add(row)
    db.flush()
    _log_audit_event(
        db,
        decision=row,
        event_type="expired",
        actor=actor_key,
        reason=reason,
        before=before,
        after=_decision_snapshot(row),
    )
    _update_trace_policy_span(db, project_id=project_id, decision=row)
    db.commit()
    db.refresh(row)
    return row
