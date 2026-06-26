from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Call,
    OutcomeReconciliationCheck,
    RuntimePolicyAuditEvent,
    RuntimePolicyDecision,
    TraceSpan,
)


SCHEMA_VERSION = "runtime_policy_evidence.v1"
HASH_ALGORITHM = "sha256"


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _decision_to_evidence(row: RuntimePolicyDecision) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "trace_id": row.trace_id,
        "call_id": row.call_id,
        "agent_name": row.agent_name,
        "role": row.role,
        "action_type": row.action_type,
        "tool_name": row.tool_name,
        "decision": row.decision,
        "status": row.status,
        "allowed": row.status in {"allowed", "approved"},
        "requires_approval": row.status == "pending_approval",
        "reasons": _json_loads(row.reasons_json, []),
        "request": _json_loads(row.request_json, {}),
        "policy_snapshot": _json_loads(row.policy_snapshot_json, {}),
        "intended_action": _json_loads(row.intended_action_json, {}),
        "trace_context": _json_loads(row.trace_context_json, {}),
        "policy_hit": _json_loads(row.policy_hit_json, {}),
        "business_impact": _json_loads(row.business_impact_json, {}),
        "approval_scope_hash": row.approval_scope_hash,
        "created_at": _iso(row.created_at),
        "expires_at": _iso(row.expires_at),
        "resolved_at": _iso(row.resolved_at),
        "resolved_by": row.resolved_by,
        "resolution_reason": row.resolution_reason,
        "consumed_at": _iso(row.consumed_at),
        "consumed_by_decision_id": row.consumed_by_decision_id,
        "required_approval_count": row.required_approval_count,
        "approval_count": row.approval_count,
        "approver_subjects": _json_loads(row.approver_subjects_json, []),
    }


def _audit_to_evidence(row: RuntimePolicyAuditEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "decision_id": row.decision_id,
        "event_type": row.event_type,
        "actor": row.actor,
        "reason": row.reason,
        "before": _json_loads(row.before_json, None),
        "after": _json_loads(row.after_json, None),
        "created_at": _iso(row.created_at),
    }


def _outcome_to_evidence(row: OutcomeReconciliationCheck) -> dict[str, Any]:
    return {
        "id": row.id,
        "call_id": row.call_id,
        "trace_id": row.trace_id,
        "runtime_policy_decision_id": row.runtime_policy_decision_id,
        "action_type": row.action_type,
        "connector_type": row.connector_type,
        "system_ref": row.system_ref,
        "verdict": row.verdict,
        "reason": row.reason,
        "amount_usd": float(row.amount_usd) if row.amount_usd is not None else None,
        "currency": row.currency,
        "claimed": _json_loads(row.claimed_json, {}),
        "actual": _json_loads(row.actual_json, None),
        "comparison": _json_loads(row.comparison_json, {}),
        "idempotency_key": row.idempotency_key,
        "metadata": _json_loads(row.metadata_json, None),
        "checked_at": _iso(row.checked_at),
        "created_at": _iso(row.created_at),
    }


def _trace_span_to_evidence(row: TraceSpan) -> dict[str, Any]:
    return {
        "id": row.id,
        "trace_id": row.trace_id,
        "span_id": row.span_id,
        "parent_span_id": row.parent_span_id,
        "call_id": row.call_id,
        "span_type": row.span_type,
        "span_name": row.span_name,
        "agent_name": row.agent_name,
        "status": row.status,
        "started_at": _iso(row.started_at),
        "ended_at": _iso(row.ended_at),
        "policy": _json_loads(row.policy_json, {}),
        "payload": _json_loads(row.payload_json, {}),
    }


def _call_to_evidence(row: Call | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "event_id": row.event_id,
        "trace_id": _json_loads(row.payload_json, {}).get("trace_id"),
        "agent_name": row.agent_name,
        "user_id": row.user_id,
        "call_type": row.call_type,
        "provider": row.provider,
        "model": row.model,
        "status": row.status,
        "error_code": row.error_code,
        "latency_ms": row.latency_ms,
        "total_tokens": row.total_tokens,
        "cost_total": float(row.cost_total),
        "cost_currency": row.cost_currency,
        "created_at": _iso(row.created_at),
    }


def _related_decisions(
    db: Session,
    *,
    project_id: str,
    decision: RuntimePolicyDecision,
) -> list[RuntimePolicyDecision]:
    ids = {decision.id}
    if decision.consumed_by_decision_id:
        ids.add(decision.consumed_by_decision_id)
    request = _json_loads(decision.request_json, {})
    approval_id = request.get("approval_id")
    if isinstance(approval_id, str) and approval_id.strip():
        ids.add(approval_id.strip())

    rows = (
        db.execute(
            select(RuntimePolicyDecision)
            .where(
                RuntimePolicyDecision.project_id == project_id,
                RuntimePolicyDecision.id.in_(ids),
            )
            .order_by(RuntimePolicyDecision.created_at.asc())
        )
        .scalars()
        .all()
    )
    return rows


def _verification_status(outcomes: list[OutcomeReconciliationCheck]) -> str:
    if any(row.verdict == "mismatched" for row in outcomes):
        return "fail"
    if any(row.verdict == "matched" for row in outcomes):
        return "pass"
    if outcomes:
        return "not_verified"
    return "not_verified"


def _outcome_filters(
    *,
    project_id: str,
    decision: RuntimePolicyDecision,
    related_decision_ids: set[str],
) -> list[Any]:
    filters: list[Any] = []
    if related_decision_ids:
        filters.append(OutcomeReconciliationCheck.runtime_policy_decision_id.in_(related_decision_ids))
    if decision.call_id:
        filters.append(OutcomeReconciliationCheck.call_id == decision.call_id)
    if decision.trace_id:
        filters.append(OutcomeReconciliationCheck.trace_id == decision.trace_id)
    return [
        OutcomeReconciliationCheck.project_id == project_id,
        or_(*filters),
    ] if filters else [OutcomeReconciliationCheck.project_id == project_id]


def build_runtime_policy_evidence_pack(
    db: Session,
    *,
    project_id: str,
    decision_id: str,
) -> dict[str, Any] | None:
    decision = db.execute(
        select(RuntimePolicyDecision).where(
            RuntimePolicyDecision.project_id == project_id,
            RuntimePolicyDecision.id == decision_id,
        )
    ).scalar_one_or_none()
    if decision is None:
        return None

    related = _related_decisions(db, project_id=project_id, decision=decision)
    related_ids = {row.id for row in related}
    audits = (
        db.execute(
            select(RuntimePolicyAuditEvent)
            .where(
                RuntimePolicyAuditEvent.project_id == project_id,
                RuntimePolicyAuditEvent.decision_id.in_(related_ids),
            )
            .order_by(RuntimePolicyAuditEvent.created_at.asc(), RuntimePolicyAuditEvent.id.asc())
        )
        .scalars()
        .all()
    )
    outcomes = (
        db.execute(
            select(OutcomeReconciliationCheck)
            .where(*_outcome_filters(project_id=project_id, decision=decision, related_decision_ids=related_ids))
            .order_by(OutcomeReconciliationCheck.checked_at.asc(), OutcomeReconciliationCheck.id.asc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    policy_span_ids = [f"policy:{decision_id}" for decision_id in related_ids]
    spans = (
        db.execute(
            select(TraceSpan)
            .where(
                TraceSpan.project_id == project_id,
                TraceSpan.span_id.in_(policy_span_ids),
            )
            .order_by(TraceSpan.started_at.asc(), TraceSpan.id.asc())
        )
        .scalars()
        .all()
    )
    call = None
    if decision.call_id:
        call = db.execute(
            select(Call).where(Call.project_id == project_id, Call.id == decision.call_id)
        ).scalar_one_or_none()

    core = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "decision_id": decision.id,
        "verification_status": _verification_status(outcomes),
        "decision": _decision_to_evidence(decision),
        "related_decisions": [
            _decision_to_evidence(row) for row in related if row.id != decision.id
        ],
        "audit_log": [_audit_to_evidence(row) for row in audits],
        "trace_policy_spans": [_trace_span_to_evidence(row) for row in spans],
        "outcome_reconciliation": [_outcome_to_evidence(row) for row in outcomes],
        "call": _call_to_evidence(call),
    }
    evidence_hash = hashlib.sha256(_json_dumps(core).encode("utf-8")).hexdigest()
    return {
        **core,
        "generated_at": _iso(datetime.now(timezone.utc)),
        "hash_algorithm": HASH_ALGORITHM,
        "evidence_hash": evidence_hash,
        "hash_payload_excludes": ["generated_at"],
    }
