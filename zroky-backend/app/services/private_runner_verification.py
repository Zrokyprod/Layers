"""Read-only verification jobs for customer-hosted runners.

The control plane never sends a raw endpoint or a credential value. Each job is
assigned to a runner that has explicitly allowlisted the credential reference
and advertised the connector-specific verifier.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ActionExecutionAttempt,
    ActionIntent,
    ActionRunner,
    ConnectorCredential,
    PrivateRunnerVerificationJob,
)
from app.services._action_post_execution_core import (
    JOB_GENERATE_RECEIPT,
    RECEIPT_PENDING,
    enqueue_action_post_execution_job,
)
from app.services.action_timeline import record_action_timeline_event
from app.services.outcome_reconciliation import ApiRecordConnector, intent_proof_status_for_check, reconcile_outcome
from app.services.system_of_record_connector_config import STRIPE_REFUND_CONNECTOR_TYPE, get_connector_config


RUNNER_VERIFICATION_SCHEMA = "zroky.private-runner-verification/v1"
_ADAPTER = "stripe_refund"
_OPERATION = "refund.read"
_ALLOWED_EVIDENCE_FIELDS = ("refund_id", "status", "amount_minor", "currency", "created_at")


class PrivateRunnerVerificationError(ValueError):
    pass


class PrivateRunnerVerificationNotFound(PrivateRunnerVerificationError):
    pass


class PrivateRunnerVerificationStateError(PrivateRunnerVerificationError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(value: str | None) -> dict[str, Any]:
    try:
        result = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return dict(result) if isinstance(result, dict) else {}


def _json_list(value: str | None) -> list[str]:
    try:
        result = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return [str(item).strip() for item in result if str(item).strip()] if isinstance(result, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _scope_allows(scope: Mapping[str, Any], credential_ref: str) -> bool:
    prefixes = scope.get("allowed_prefixes")
    if not isinstance(prefixes, list | tuple):
        return False
    return any(credential_ref.startswith(str(prefix).strip()) for prefix in prefixes if str(prefix).strip())


def _runner_supports_verification(runner: ActionRunner, credential_ref: str) -> bool:
    if runner.status != "online" or runner.runner_type != "customer_hosted":
        return False
    if not _scope_allows(_json_loads(runner.credential_scope_json), credential_ref):
        return False
    heartbeat = _json_loads(runner.heartbeat_payload_json)
    adapters = heartbeat.get("verification_adapters")
    return isinstance(adapters, list | tuple) and _ADAPTER in {str(value).strip() for value in adapters}


def _select_runner(db: Session, *, project_id: str, credential_ref: str) -> ActionRunner | None:
    rows = db.execute(
        select(ActionRunner)
        .where(ActionRunner.project_id == project_id)
        .order_by(ActionRunner.last_heartbeat_at.desc(), ActionRunner.created_at.asc())
    ).scalars()
    return next((row for row in rows if _runner_supports_verification(row, credential_ref)), None)


def _stripe_refund_id(context: Mapping[str, Any]) -> str | None:
    verification = _as_dict(context.get("verification"))
    target = _as_dict(context.get("target"))
    claimed = _as_dict(context.get("claimed"))
    result = _as_dict(context.get("result"))
    return _text(
        verification.get("refund_id"),
        target.get("refund_id"),
        claimed.get("refund_id"),
        result.get("refund_id"),
        result.get("provider_ref"),
    )


def enqueue_private_runner_verification(
    db: Session,
    *,
    intent: ActionIntent,
    attempt: ActionExecutionAttempt,
    context: Mapping[str, Any],
    connector_type: str,
) -> PrivateRunnerVerificationJob | None:
    """Queue a supported remote-credential verification, or return ``None``.

    ``None`` deliberately leaves the normal fail-closed reconciliation path in
    control for unsupported connectors and missing/offline runners.
    """
    if connector_type != STRIPE_REFUND_CONNECTOR_TYPE:
        return None
    config = get_connector_config(db, project_id=intent.project_id, connector_type=connector_type)
    if config is None or not config.is_active or not config.bearer_credential_id:
        return None
    credential = db.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.id == config.bearer_credential_id,
            ConnectorCredential.project_id == intent.project_id,
        )
    ).scalar_one_or_none()
    if not (
        credential
        and credential.is_active
        and credential.custody_mode == "private_runner"
        and credential.secret_ref
        and connector_type in _json_list(credential.allowed_connector_types_json)
    ):
        return None
    refund_id = _stripe_refund_id(context)
    if refund_id is None:
        return None
    runner = _select_runner(db, project_id=intent.project_id, credential_ref=credential.secret_ref)
    if runner is None:
        return None
    existing = db.execute(
        select(PrivateRunnerVerificationJob).where(
            PrivateRunnerVerificationJob.project_id == intent.project_id,
            PrivateRunnerVerificationJob.execution_attempt_id == attempt.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    plan = {
        "schema_version": RUNNER_VERIFICATION_SCHEMA,
        "adapter": _ADAPTER,
        "operation": _OPERATION,
        "connector_type": connector_type,
        "credential_ref": credential.secret_ref,
        "target": {"refund_id": refund_id},
        "evidence_fields": list(_ALLOWED_EVIDENCE_FIELDS),
    }
    stored_context = {
        "claimed": _as_dict(context.get("claimed")),
        "trace": _as_dict(context.get("trace")),
        "proof_manifest": _as_dict(context.get("proof_manifest")),
        "match_fields": [str(value) for value in context.get("match_fields", []) if str(value).strip()]
        if isinstance(context.get("match_fields"), list | tuple)
        else [],
        "system_ref": _text(context.get("system_ref"), _as_dict(context.get("verification")).get("system_ref")),
    }
    row = PrivateRunnerVerificationJob(
        id=str(uuid4()),
        project_id=intent.project_id,
        action_intent_id=intent.id,
        execution_attempt_id=attempt.id,
        runner_id=runner.id,
        connector_type=connector_type,
        credential_ref=credential.secret_ref,
        status="queued",
        plan_json=_json_dumps(plan),
        context_json=_json_dumps(stored_context),
    )
    db.add(row)
    db.flush()
    record_action_timeline_event(
        db,
        project_id=intent.project_id,
        action_id=intent.id,
        event_type="private_runner_verification_queued",
        payload={"verification_job_id": row.id, "runner_id": runner.id, "connector_type": connector_type},
        actor="action-post-execution-worker",
    )
    return row


def claim_private_runner_verification(
    db: Session, *, project_id: str, runner_id: str
) -> PrivateRunnerVerificationJob:
    row = db.execute(
        select(PrivateRunnerVerificationJob)
        .where(
            PrivateRunnerVerificationJob.project_id == project_id,
            PrivateRunnerVerificationJob.runner_id == runner_id,
            PrivateRunnerVerificationJob.status == "queued",
        )
        .order_by(PrivateRunnerVerificationJob.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise PrivateRunnerVerificationNotFound("No claimable verification job found for this runner.")
    row.status = "claimed"
    row.claimed_at = _now()
    db.add(row)
    db.flush()
    return row


def _safe_record(record: Mapping[str, Any]) -> dict[str, Any]:
    values = _as_dict(record)
    forbidden = {"token", "secret", "authorization", "api_key", "password"}
    if any(any(marker in str(key).lower() for marker in forbidden) for key in values):
        raise PrivateRunnerVerificationError("verification evidence must not contain credentials")
    return {key: values[key] for key in _ALLOWED_EVIDENCE_FIELDS if key in values}


def finish_private_runner_verification(
    db: Session,
    *,
    project_id: str,
    runner_id: str,
    job_id: str,
    actual_record: Mapping[str, Any] | None,
    record_found: bool,
    error_message: str | None = None,
) -> PrivateRunnerVerificationJob:
    row = db.execute(
        select(PrivateRunnerVerificationJob).where(
            PrivateRunnerVerificationJob.id == job_id,
            PrivateRunnerVerificationJob.project_id == project_id,
            PrivateRunnerVerificationJob.runner_id == runner_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise PrivateRunnerVerificationNotFound("Verification job was not found for this runner.")
    if row.status != "claimed" and not (error_message and row.status == "queued"):
        raise PrivateRunnerVerificationStateError("Verification job must be claimed before it can finish.")
    intent = db.execute(
        select(ActionIntent).where(ActionIntent.id == row.action_intent_id, ActionIntent.project_id == project_id)
    ).scalar_one()
    context = _json_loads(row.context_json)
    evidence = {} if error_message else _safe_record(actual_record or {})
    outcome = reconcile_outcome(
        db,
        project_id=project_id,
        claimed=_as_dict(context.get("claimed")),
        connector=ApiRecordConnector(record=evidence or None, record_found=record_found, connector_type=row.connector_type),
        call_id=_text(_as_dict(context.get("trace")).get("call_id")),
        trace_id=_text(_as_dict(context.get("trace")).get("trace_id")),
        runtime_policy_decision_id=intent.runtime_policy_decision_id,
        action_intent_id=intent.id,
        action_type=intent.action_type,
        system_ref=_text(context.get("system_ref")) or f"{row.connector_type}:{intent.id}",
        match_fields=[str(value) for value in context.get("match_fields", [])],
        proof_manifest=_as_dict(context.get("proof_manifest")) or None,
        idempotency_key=f"private-runner-verification:{row.id}",
        metadata={
            "source": "private_runner",
            "runner_id": runner_id,
            "connector_kind": row.connector_type,
            "connector": {"error": str(error_message)[:1000]} if error_message else {},
        },
    )
    intent.proof_status = intent_proof_status_for_check(outcome)
    intent.receipt_status = RECEIPT_PENDING
    db.add(intent)
    receipt = enqueue_action_post_execution_job(
        db,
        project_id=project_id,
        action_id=intent.id,
        attempt_id=row.execution_attempt_id,
        job_type=JOB_GENERATE_RECEIPT,
        payload={"trigger": "private_runner_verification", "outcome_reconciliation_id": outcome.id},
    )
    row.status = "failed" if error_message else "succeeded"
    row.error_message = str(error_message)[:1000] if error_message else None
    row.result_json = _json_dumps(
        {"outcome_reconciliation_id": outcome.id, "proof_status": outcome.proof_status}
    )
    row.finished_at = _now()
    db.add(row)
    record_action_timeline_event(
        db,
        project_id=project_id,
        action_id=intent.id,
        event_type="private_runner_verification_completed",
        payload={"verification_job_id": row.id, "outcome_reconciliation_id": outcome.id, "receipt_job_id": receipt.id},
        actor=runner_id,
    )
    db.flush()
    return row


def sweep_stale_private_runner_verifications(
    db: Session,
    *,
    stale_after_seconds: int,
    limit: int = 100,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Close jobs whose assigned runner never returned evidence.

    A remote runner is unavailable evidence, not evidence that the action did
    not happen. The resulting proof therefore settles as unverifiable or
    not-verified and the receipt captures that limitation.
    """
    current = now or _now()
    cutoff = current.timestamp() - max(1, int(stale_after_seconds))
    rows = list(
        db.execute(
            select(PrivateRunnerVerificationJob)
            .where(PrivateRunnerVerificationJob.status.in_(("queued", "claimed")))
            .order_by(PrivateRunnerVerificationJob.created_at.asc())
            .limit(max(1, min(500, int(limit))))
        ).scalars()
    )
    expired: list[str] = []
    for row in rows:
        reference = row.claimed_at or row.created_at
        if reference is None or reference.timestamp() > cutoff:
            continue
        finish_private_runner_verification(
            db,
            project_id=row.project_id,
            runner_id=row.runner_id,
            job_id=row.id,
            actual_record={},
            record_found=False,
            error_message="runner_verification_timed_out",
        )
        expired.append(row.id)
    return {"expired": len(expired), "verification_job_ids": expired}


def verification_job_plan(row: PrivateRunnerVerificationJob) -> dict[str, Any]:
    return _json_loads(row.plan_json)


def verification_job_result(row: PrivateRunnerVerificationJob) -> dict[str, Any]:
    return _json_loads(row.result_json)
