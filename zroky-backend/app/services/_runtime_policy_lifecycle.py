from __future__ import annotations

from app.services._runtime_policy_core import *  # noqa: F403


def _sequence_risk_enabled_from_policy(policy_snapshot: Any) -> bool:
    return isinstance(policy_snapshot, dict) and policy_snapshot.get("runtime_sequence_risk_enabled") is True


def runtime_sequence_risk_enabled(result: RuntimePolicyResult) -> bool:
    """Return whether sequence-risk detection is enabled for this policy result."""

    policy_snapshot = _json_loads(result.decision.policy_snapshot_json, {})
    return _sequence_risk_enabled_from_policy(policy_snapshot)


def escalate_runtime_policy_result_for_sequence_risk(
    db: Session,
    *,
    project_id: str,
    result: RuntimePolicyResult,
    signal: SequenceRiskSignal | None,
    actor: str | None = None,
) -> RuntimePolicyResult:
    """Escalate a persisted runtime-policy decision when cross-action risk is
    detected. ``evaluate_runtime_policy`` has already committed ``result``, so
    this updates the *persisted* row (decision, status, reasons, policy_hit) and
    emits the matching audit event + trace span. It never *downgrades* - if the
    single-action decision is already at least as restrictive as the sequence
    recommendation, the result is returned untouched.
    """

    if signal is None:
        return result

    # Opt-in only: a project must enable sequence-risk escalation. The resolved
    # policy is already captured on the persisted decision, so read it there.
    policy_snapshot = _json_loads(result.decision.policy_snapshot_json, {})
    if not _sequence_risk_enabled_from_policy(policy_snapshot):
        return result

    if signal.recommended == SEQUENCE_BLOCK:
        target_rank, decision, status = 2, "block", "blocked"
        allowed, requires_approval = False, False
    else:  # hold_for_approval
        target_rank, decision, status = 1, "requires_approval", "pending_approval"
        allowed, requires_approval = False, True

    current_rank = _DECISION_RANK.get(result.decision.decision, 0)
    if current_rank >= target_rank:
        return result

    row = result.decision
    before = _decision_snapshot(row)

    existing_reasons = _json_loads(row.reasons_json, [])
    if not isinstance(existing_reasons, list):
        existing_reasons = []
    seq_reason = _reason(f"sequence risk: {signal.reason}")
    merged_reasons = [*[str(item) for item in existing_reasons], seq_reason]

    policy_hit = _json_loads(row.policy_hit_json, {})
    if not isinstance(policy_hit, dict):
        policy_hit = {}
    policy_hit["sequence_risk"] = {
        "pattern": signal.pattern,
        "recommended": signal.recommended,
        "confidence": signal.confidence,
        "reason": signal.reason,
        "trace_id": signal.trace_id,
        "contributing_action_ids": signal.contributing_action_ids,
    }

    row.decision = decision
    row.status = status
    row.reasons_json = _json_dumps([_reason(item) for item in merged_reasons])
    row.policy_hit_json = _json_dumps(policy_hit)
    if status == "pending_approval":
        if row.expires_at is None:
            row.expires_at = _approval_expiry(policy_snapshot)
        if (row.required_approval_count or 0) <= 0:
            row.required_approval_count = 1
    db.add(row)
    db.flush()

    _log_audit_event(
        db,
        decision=row,
        event_type=_audit_event_type(decision=decision, status=status),
        actor=actor,
        reason=seq_reason,
        before=before,
        after=_decision_snapshot(row),
    )
    _update_trace_policy_span(db, project_id=project_id, decision=row)
    db.commit()
    db.refresh(row)

    return RuntimePolicyResult(
        row,
        allowed=allowed,
        requires_approval=requires_approval,
        reasons=merged_reasons,
    )


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


def _auto_advance_linked_action_intent(
    db: Session,
    *,
    project_id: str,
    decision_id: str,
    actor: str | None,
) -> None:
    from app.services.action_kernel import auto_advance_action_intent_for_runtime_policy_resolution

    advanced = auto_advance_action_intent_for_runtime_policy_resolution(
        db,
        project_id=project_id,
        decision_id=decision_id,
        actor=actor,
    )
    if advanced is not None:
        db.commit()


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
        _auto_advance_linked_action_intent(
            db,
            project_id=project_id,
            decision_id=row.id,
            actor=actor_key,
        )
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
    if row.status == "approved":
        _auto_advance_linked_action_intent(
            db,
            project_id=project_id,
            decision_id=row.id,
            actor=actor_key,
        )
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
