"""Evidence-first response workflow for confirmed SOR mismatches.

This module intentionally never mutates a system of record. A mismatch can
suggest a compensating action, but that action must be created and approved on
the normal protected-action rail before it can execute.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ActionReceipt,
    OutcomeMismatchResponse,
    OutcomeReconciliationCheck,
    ProjectAlert,
)
from app.services.action_timeline import record_action_timeline_event
from app.services.alerts import auto_send_pending_alerts_to_slack


MISMATCH_ALERT_CATEGORY = "OUTCOME_MISMATCH"
MISMATCH_RESPONSE_OPEN = "OPEN"
MISMATCH_RESPONSE_ACKNOWLEDGED = "ACKNOWLEDGED"
MISMATCH_RESPONSE_RESOLVED = "RESOLVED"
VALID_RESOLUTION_CODES = frozenset(
    {"confirmed_mismatch", "expected_change", "false_positive", "unresolved"}
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _dumps(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), separators=(",", ":"), sort_keys=True, default=str)


def _comparison(check: OutcomeReconciliationCheck) -> dict[str, Any]:
    value = _loads(check.comparison_json, {})
    return value if isinstance(value, dict) else {}


def is_actionable_mismatch(check: OutcomeReconciliationCheck) -> bool:
    """Return true only for evidence that contradicts the claimed outcome.

    ``pending`` is eventual consistency and ``unverifiable`` is a coverage
    gap. Neither must be presented as agent wrongdoing.
    """

    if (check.verdict or "").lower() != "mismatched":
        return False
    proof_status = (check.proof_status or "").lower()
    return proof_status not in {"pending", "unverifiable", "cancelled"}


def _remediation_suggestion(check: OutcomeReconciliationCheck) -> dict[str, Any]:
    comparison = _comparison(check)
    return {
        "kind": "compensating_action_review",
        "status": "suggested",
        "execution_state": "not_started",
        "requires_owner_approval": True,
        "safety_boundary": "A rollback is a new protected action. Zroky will not execute it automatically.",
        "next_steps": [
            "Review the claimed and observed system-of-record values.",
            "Decide whether a compensating action is needed.",
            "Create that action through the protected-action rail for independent approval, proof, and receipt.",
        ],
        "mismatched_fields": [
            item.get("field")
            for item in comparison.get("mismatches", [])
            if isinstance(item, Mapping) and isinstance(item.get("field"), str)
        ],
    }


def _alert_evidence(response: OutcomeMismatchResponse, check: OutcomeReconciliationCheck) -> dict[str, Any]:
    comparison = _comparison(check)
    return {
        "mismatch_response_id": response.id,
        "reconciliation_check_id": check.id,
        "action_intent_id": response.action_intent_id,
        "action_type": check.action_type,
        "system_ref": check.system_ref,
        "proof_status": check.proof_status,
        "proof_reason_code": check.proof_reason_code,
        "reason": check.reason,
        "mismatched_fields": [
            item.get("field")
            for item in comparison.get("mismatches", [])
            if isinstance(item, Mapping) and isinstance(item.get("field"), str)
        ],
    }


def create_or_get_mismatch_response(
    db: Session,
    *,
    check: OutcomeReconciliationCheck,
    action_intent_id: str | None = None,
) -> OutcomeMismatchResponse | None:
    """Persist one case and one alert for a confirmed reconciliation mismatch."""

    if not is_actionable_mismatch(check):
        return None

    response = db.execute(
        select(OutcomeMismatchResponse).where(
            OutcomeMismatchResponse.project_id == check.project_id,
            OutcomeMismatchResponse.reconciliation_check_id == check.id,
        )
    ).scalar_one_or_none()
    changed = False
    timeline_needed = False
    if response is None:
        response = OutcomeMismatchResponse(
            id=str(uuid4()),
            project_id=check.project_id,
            reconciliation_check_id=check.id,
            action_intent_id=action_intent_id or check.action_intent_id,
            status=MISMATCH_RESPONSE_OPEN,
            remediation_json=_dumps(_remediation_suggestion(check)),
        )
        db.add(response)
        db.flush()
        changed = True
        timeline_needed = bool(response.action_intent_id)
    elif response.action_intent_id is None and (action_intent_id or check.action_intent_id):
        response.action_intent_id = action_intent_id or check.action_intent_id
        db.add(response)
        changed = True
        timeline_needed = True

    if response.alert_id is None:
        alert = ProjectAlert(
            id=str(uuid4()),
            tenant_id=check.project_id,
            diagnosis_id=response.id,
            category=MISMATCH_ALERT_CATEGORY,
            severity="critical",
            status=MISMATCH_RESPONSE_OPEN,
            source="outcome_reconciliation",
            title=f"System-of-record mismatch for {check.action_type or 'protected action'}",
            evidence_json=_dumps(_alert_evidence(response, check)),
        )
        db.add(alert)
        db.flush()
        response.alert_id = alert.id
        db.add(response)
        changed = True

    if timeline_needed:
        _record_timeline(
            db,
            response=response,
            event_type="outcome_mismatch_detected",
            actor=None,
            extra={
                "proof_status": check.proof_status,
                "proof_reason_code": check.proof_reason_code,
            },
        )

    if changed:
        db.commit()
        db.refresh(response)
        try:
            auto_send_pending_alerts_to_slack(
                db,
                tenant_id=check.project_id,
                diagnosis_id=response.id,
                categories=[MISMATCH_ALERT_CATEGORY],
                agent_name="outcome_reconciliation",
            )
        except Exception:
            # The case and audit alert are durable even if Slack is unavailable.
            pass
    return response


def list_mismatch_responses(
    db: Session,
    *,
    project_id: str,
    status: str | None = None,
    since: datetime | None = None,
    limit: int = 50,
) -> list[OutcomeMismatchResponse]:
    query = select(OutcomeMismatchResponse).where(OutcomeMismatchResponse.project_id == project_id)
    if status:
        normalized = status.upper()
        if normalized not in {MISMATCH_RESPONSE_OPEN, MISMATCH_RESPONSE_ACKNOWLEDGED, MISMATCH_RESPONSE_RESOLVED}:
            raise ValueError("status must be one of: OPEN, ACKNOWLEDGED, RESOLVED")
        query = query.where(OutcomeMismatchResponse.status == normalized)
    if since is not None:
        query = query.where(OutcomeMismatchResponse.created_at >= since)
    return list(
        db.execute(
            query.order_by(OutcomeMismatchResponse.created_at.desc(), OutcomeMismatchResponse.id.desc()).limit(limit)
        ).scalars()
    )


def get_mismatch_response(
    db: Session,
    *,
    project_id: str,
    response_id: str,
) -> OutcomeMismatchResponse | None:
    return db.execute(
        select(OutcomeMismatchResponse).where(
            OutcomeMismatchResponse.project_id == project_id,
            OutcomeMismatchResponse.id == response_id,
        )
    ).scalar_one_or_none()


def acknowledge_mismatch_response(
    db: Session,
    *,
    response: OutcomeMismatchResponse,
    actor: str | None,
) -> OutcomeMismatchResponse:
    if response.status == MISMATCH_RESPONSE_RESOLVED:
        return response
    if response.status == MISMATCH_RESPONSE_OPEN:
        response.status = MISMATCH_RESPONSE_ACKNOWLEDGED
        response.acknowledged_at = _now()
        response.acknowledged_by_subject = actor
        _update_alert_status(db, response=response, status=MISMATCH_RESPONSE_ACKNOWLEDGED)
        _record_timeline(db, response=response, event_type="outcome_mismatch_acknowledged", actor=actor)
        db.add(response)
        db.commit()
        db.refresh(response)
    return response


def resolve_mismatch_response(
    db: Session,
    *,
    response: OutcomeMismatchResponse,
    resolution_code: str,
    resolution_note: str | None,
    actor: str | None,
) -> OutcomeMismatchResponse:
    normalized_code = resolution_code.strip().lower()
    if normalized_code not in VALID_RESOLUTION_CODES:
        raise ValueError("resolution_code must be one of: " + ", ".join(sorted(VALID_RESOLUTION_CODES)))
    if response.status == MISMATCH_RESPONSE_RESOLVED:
        if response.resolution_code != normalized_code:
            raise ValueError("Mismatch response case is already resolved with a different resolution_code.")
        return response
    response.status = MISMATCH_RESPONSE_RESOLVED
    response.resolution_code = normalized_code
    response.resolution_note = resolution_note.strip()[:1000] if resolution_note and resolution_note.strip() else None
    response.resolved_at = _now()
    response.resolved_by_subject = actor
    if response.acknowledged_at is None:
        response.acknowledged_at = response.resolved_at
        response.acknowledged_by_subject = actor
    _update_alert_status(db, response=response, status=MISMATCH_RESPONSE_RESOLVED)
    _record_timeline(
        db,
        response=response,
        event_type="outcome_mismatch_resolved",
        actor=actor,
        extra={"resolution_code": normalized_code},
    )
    db.add(response)
    db.commit()
    db.refresh(response)
    return response


def link_corrective_action(
    db: Session,
    *,
    response: OutcomeMismatchResponse,
    corrective_action_intent_id: str,
    decision_status: str,
    actor: str | None,
) -> OutcomeMismatchResponse:
    remediation = _loads(response.remediation_json, {})
    existing_action_id = remediation.get("corrective_action_intent_id")
    if existing_action_id and existing_action_id != corrective_action_intent_id:
        raise ValueError("Mismatch response already has a different corrective action.")
    changed = (
        existing_action_id != corrective_action_intent_id
        or remediation.get("status") != "proposed"
        or remediation.get("decision_status") != decision_status
    )
    remediation.update(
        {
            "status": "proposed",
            "execution_state": "not_started",
            "corrective_action_intent_id": corrective_action_intent_id,
            "decision_status": decision_status,
            "proposed_by": actor,
            "proposed_at": _now().isoformat(),
        }
    )
    response.remediation_json = _dumps(remediation)
    db.add(response)
    if changed:
        _record_timeline(
            db,
            response=response,
            event_type="outcome_correction_proposed",
            actor=actor,
            extra={
                "corrective_action_intent_id": corrective_action_intent_id,
                "decision_status": decision_status,
            },
        )
    return response


def _update_alert_status(db: Session, *, response: OutcomeMismatchResponse, status: str) -> None:
    if not response.alert_id:
        return
    alert = db.execute(
        select(ProjectAlert).where(
            ProjectAlert.id == response.alert_id,
            ProjectAlert.tenant_id == response.project_id,
        )
    ).scalar_one_or_none()
    if alert is None:
        return
    now = _now()
    alert.status = status
    if status in {MISMATCH_RESPONSE_ACKNOWLEDGED, MISMATCH_RESPONSE_RESOLVED} and alert.acknowledged_at is None:
        alert.acknowledged_at = now
    if status == MISMATCH_RESPONSE_RESOLVED:
        alert.resolved_at = now
    db.add(alert)


def _record_timeline(
    db: Session,
    *,
    response: OutcomeMismatchResponse,
    event_type: str,
    actor: str | None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    if not response.action_intent_id:
        return
    payload = {
        "mismatch_response_id": response.id,
        "reconciliation_check_id": response.reconciliation_check_id,
        **dict(extra or {}),
    }
    record_action_timeline_event(
        db,
        project_id=response.project_id,
        action_id=response.action_intent_id,
        event_type=event_type,
        payload=payload,
        actor=actor,
    )


def mismatch_response_to_dict(db: Session, response: OutcomeMismatchResponse) -> dict[str, Any]:
    check = db.execute(
        select(OutcomeReconciliationCheck).where(
            OutcomeReconciliationCheck.project_id == response.project_id,
            OutcomeReconciliationCheck.id == response.reconciliation_check_id,
        )
    ).scalar_one_or_none()
    receipt = None
    if response.action_intent_id:
        receipt = db.execute(
            select(ActionReceipt).where(
                ActionReceipt.project_id == response.project_id,
                ActionReceipt.action_intent_id == response.action_intent_id,
            )
        ).scalar_one_or_none()
    comparison = _comparison(check) if check is not None else {}
    return {
        "id": response.id,
        "project_id": response.project_id,
        "reconciliation_check_id": response.reconciliation_check_id,
        "action_intent_id": response.action_intent_id,
        "action_receipt_id": receipt.id if receipt is not None else None,
        "receipt_digest": receipt.receipt_digest if receipt is not None else None,
        "alert_id": response.alert_id,
        "status": response.status,
        "resolution_code": response.resolution_code,
        "resolution_note": response.resolution_note,
        "remediation": _loads(response.remediation_json, {}),
        "evidence": {
            "verdict": check.verdict if check is not None else None,
            "proof_status": check.proof_status if check is not None else None,
            "proof_reason_code": check.proof_reason_code if check is not None else None,
            "reason": check.reason if check is not None else None,
            "action_type": check.action_type if check is not None else None,
            "system_ref": check.system_ref if check is not None else None,
            "claimed": _loads(check.claimed_json, {}) if check is not None else {},
            "actual": _loads(check.actual_json, None) if check is not None else None,
            "comparison": comparison,
            "observed_at": check.proof_observed_at if check is not None else None,
            "checked_at": check.checked_at if check is not None else None,
        },
        "acknowledged_by_subject": response.acknowledged_by_subject,
        "acknowledged_at": response.acknowledged_at,
        "resolved_by_subject": response.resolved_by_subject,
        "resolved_at": response.resolved_at,
        "created_at": response.created_at,
        "updated_at": response.updated_at,
    }
