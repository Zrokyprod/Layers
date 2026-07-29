"""Evidence-backed, owner-approved relief from repetitive approvals.

Rules are intentionally narrow. They match one persisted action-intent shape,
only for UPDATE operations, and are created only after repeated human-approved
actions have matched their system-of-record proof and generated a receipt.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ActionIntent, ApprovalAdaptationRule, RuntimePolicyDecision


SAFE_OPERATION_KINDS = frozenset({"UPDATE"})
ACTIVE = "active"
REVOKED = "revoked"


class ApprovalAdaptationNotFound(ValueError):
    """Raised when a project-scoped adaptation rule does not exist."""


class ApprovalAdaptationNotEligible(ValueError):
    """Raised when the current evidence cannot support an adaptation rule."""


@dataclass(frozen=True)
class ApprovalAdaptationCandidate:
    scope_hash: str
    agent_id: str | None
    action_type: str
    operation_kind: str
    contract_key: str
    environment: str
    approved_count: int
    matched_count: int
    mismatched_count: int
    unresolved_count: int

    @property
    def eligible(self) -> bool:
        return (
            self.operation_kind in SAFE_OPERATION_KINDS
            and self.approved_count > 0
            and self.approved_count == self.matched_count
            and self.mismatched_count == 0
            and self.unresolved_count == 0
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _canonical_digest(value: Any) -> str:
    rendered = json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def scope_hash_for_action_intent(intent: ActionIntent) -> str:
    """Hash an exact intent shape without storing resource or parameter values."""
    scope = {
        "project_id": intent.project_id,
        "agent_id": intent.agent_id,
        "contract_key": intent.contract_key,
        "contract_version": intent.contract_version,
        "action_type": intent.action_type,
        "operation_kind": intent.operation_kind,
        "environment": intent.environment,
        "principal_digest": _canonical_digest(_json_loads(intent.principal_json, {})),
        "resource_digest": _canonical_digest(_json_loads(intent.resource_json, {})),
        "parameters_digest": _canonical_digest(_json_loads(intent.parameters_json, {})),
    }
    return _canonical_digest(scope)


def _approval_id_from_decision(decision: RuntimePolicyDecision) -> str | None:
    request = _json_loads(decision.request_json, {})
    approval_id = request.get("approval_id") if isinstance(request, dict) else None
    return approval_id.strip() if isinstance(approval_id, str) and approval_id.strip() else None


def _matched(action: ActionIntent) -> bool:
    return action.proof_status == "matched" and action.receipt_status == "generated"


def _candidate_rows(db: Session, *, project_id: str) -> list[ApprovalAdaptationCandidate]:
    """Build candidates from completed, human-approved action outcomes.

    The linked policy decision is the post-approval allow decision. Its
    request records the exact pending approval that was consumed, which lets
    this query exclude historical auto-allowed actions from the evidence set.
    """
    rows = list(
        db.execute(
            select(ActionIntent, RuntimePolicyDecision)
            .join(
                RuntimePolicyDecision,
                RuntimePolicyDecision.id == ActionIntent.runtime_policy_decision_id,
            )
            .where(
                ActionIntent.project_id == project_id,
                ActionIntent.status == "authorized",
                RuntimePolicyDecision.project_id == project_id,
                RuntimePolicyDecision.status == "allowed",
            )
        ).all()
    )
    approval_ids = {
        approval_id
        for _, decision in rows
        if (approval_id := _approval_id_from_decision(decision)) is not None
    }
    if not approval_ids:
        return []
    approvals = {
        row.id: row
        for row in db.execute(
            select(RuntimePolicyDecision).where(
                RuntimePolicyDecision.project_id == project_id,
                RuntimePolicyDecision.id.in_(approval_ids),
                RuntimePolicyDecision.status == "approved",
                RuntimePolicyDecision.required_approval_count == 1,
            )
        ).scalars()
    }
    grouped: dict[str, dict[str, Any]] = {}
    for action, decision in rows:
        approval_id = _approval_id_from_decision(decision)
        if approval_id not in approvals or action.operation_kind not in SAFE_OPERATION_KINDS:
            continue
        scope_hash = scope_hash_for_action_intent(action)
        bucket = grouped.setdefault(
            scope_hash,
            {
                "action": action,
                "approved_count": 0,
                "matched_count": 0,
                "mismatched_count": 0,
                "unresolved_count": 0,
            },
        )
        bucket["approved_count"] += 1
        if _matched(action):
            bucket["matched_count"] += 1
        elif action.proof_status == "mismatched":
            bucket["mismatched_count"] += 1
        else:
            bucket["unresolved_count"] += 1
    candidates = []
    for scope_hash, bucket in grouped.items():
        action = bucket["action"]
        candidates.append(
            ApprovalAdaptationCandidate(
                scope_hash=scope_hash,
                agent_id=action.agent_id,
                action_type=action.action_type,
                operation_kind=action.operation_kind,
                contract_key=action.contract_key,
                environment=action.environment,
                approved_count=bucket["approved_count"],
                matched_count=bucket["matched_count"],
                mismatched_count=bucket["mismatched_count"],
                unresolved_count=bucket["unresolved_count"],
            )
        )
    return candidates


def list_recommendations(
    db: Session,
    *,
    project_id: str,
    minimum_matched_approvals: int,
) -> list[ApprovalAdaptationCandidate]:
    """Return eligible patterns that do not already have an active rule."""
    active_scopes = set(
        db.execute(
            select(ApprovalAdaptationRule.scope_hash).where(
                ApprovalAdaptationRule.project_id == project_id,
                ApprovalAdaptationRule.status == ACTIVE,
                ApprovalAdaptationRule.expires_at > _now(),
            )
        ).scalars()
    )
    return [
        candidate
        for candidate in _candidate_rows(db, project_id=project_id)
        if candidate.eligible
        and candidate.matched_count >= minimum_matched_approvals
        and candidate.scope_hash not in active_scopes
    ]


def activate_recommendation(
    db: Session,
    *,
    project_id: str,
    scope_hash: str,
    minimum_matched_approvals: int,
    duration_days: int,
    actor: str | None,
) -> ApprovalAdaptationRule:
    existing = db.execute(
        select(ApprovalAdaptationRule)
        .where(
            ApprovalAdaptationRule.project_id == project_id,
            ApprovalAdaptationRule.scope_hash == scope_hash,
            ApprovalAdaptationRule.status == ACTIVE,
            ApprovalAdaptationRule.expires_at > _now(),
        )
        .order_by(ApprovalAdaptationRule.created_at.desc(), ApprovalAdaptationRule.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    candidates = {
        candidate.scope_hash: candidate
        for candidate in list_recommendations(
            db,
            project_id=project_id,
            minimum_matched_approvals=minimum_matched_approvals,
        )
    }
    candidate = candidates.get(scope_hash)
    if candidate is None:
        raise ApprovalAdaptationNotEligible("No eligible verified approval pattern exists for this scope.")
    row = ApprovalAdaptationRule(
        id=str(uuid4()),
        project_id=project_id,
        scope_hash=candidate.scope_hash,
        agent_id=candidate.agent_id,
        action_type=candidate.action_type,
        operation_kind=candidate.operation_kind,
        contract_key=candidate.contract_key,
        environment=candidate.environment,
        evidence_approved_count=candidate.approved_count,
        evidence_matched_count=candidate.matched_count,
        status=ACTIVE,
        activated_by_subject=actor,
        expires_at=_now() + timedelta(days=duration_days),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_rules(db: Session, *, project_id: str) -> list[ApprovalAdaptationRule]:
    return list(
        db.execute(
            select(ApprovalAdaptationRule)
            .where(ApprovalAdaptationRule.project_id == project_id)
            .order_by(ApprovalAdaptationRule.created_at.desc(), ApprovalAdaptationRule.id.desc())
        ).scalars()
    )


def revoke_rule(
    db: Session,
    *,
    project_id: str,
    rule_id: str,
    actor: str | None,
    reason: str,
) -> ApprovalAdaptationRule:
    row = db.execute(
        select(ApprovalAdaptationRule).where(
            ApprovalAdaptationRule.project_id == project_id,
            ApprovalAdaptationRule.id == rule_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApprovalAdaptationNotFound("Approval adaptation rule not found.")
    if row.status == ACTIVE:
        row.status = REVOKED
        row.revoked_at = _now()
        row.revoked_by_subject = actor
        row.revocation_reason = reason
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def revoke_active_rules_for_proof_failure(
    db: Session,
    *,
    intent: ActionIntent,
    proof_status: str,
) -> list[ApprovalAdaptationRule]:
    """Trip the adaptation circuit breaker on a final proof failure.

    This deliberately does not commit. Verification owns the surrounding
    transaction, so the mismatch and revocation become durable together.
    """
    if intent.operation_kind not in SAFE_OPERATION_KINDS:
        return []
    rows = list(
        db.execute(
            select(ApprovalAdaptationRule).where(
                ApprovalAdaptationRule.project_id == intent.project_id,
                ApprovalAdaptationRule.scope_hash == scope_hash_for_action_intent(intent),
                ApprovalAdaptationRule.status == ACTIVE,
                ApprovalAdaptationRule.expires_at > _now(),
            )
        ).scalars()
    )
    for row in rows:
        row.status = REVOKED
        row.revoked_at = _now()
        row.revoked_by_subject = f"system:proof-{proof_status}"
        row.revocation_reason = f"automatic: verification ended {proof_status}"
        db.add(row)
    if rows:
        db.flush()
    return rows


def find_active_rule_for_action(
    db: Session,
    *,
    project_id: str,
    action_id: str | None,
) -> ApprovalAdaptationRule | None:
    """Resolve a rule only for a persisted safe action intent.

    Direct runtime-policy callers never qualify. This keeps the exemption on
    Zroky's verified-action rail, where the exact contract and later receipt
    are both present.
    """
    if not action_id:
        return None
    action = db.execute(
        select(ActionIntent).where(
            ActionIntent.project_id == project_id,
            ActionIntent.id == action_id,
        )
    ).scalar_one_or_none()
    if action is None or action.operation_kind not in SAFE_OPERATION_KINDS:
        return None
    return db.execute(
        select(ApprovalAdaptationRule)
        .where(
            ApprovalAdaptationRule.project_id == project_id,
            ApprovalAdaptationRule.scope_hash == scope_hash_for_action_intent(action),
            ApprovalAdaptationRule.status == ACTIVE,
            ApprovalAdaptationRule.expires_at > _now(),
        )
        .order_by(ApprovalAdaptationRule.created_at.desc(), ApprovalAdaptationRule.id.desc())
        .limit(1)
    ).scalar_one_or_none()
