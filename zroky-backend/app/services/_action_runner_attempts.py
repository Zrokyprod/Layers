from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ActionExecutionAttempt, ActionIntent, ActionRunner
from app.services.action_kernel import (
    ActionIntentNotFound,
    canonical_json,
    get_action_intent,
    sha256_digest,
)
from app.services.action_timeline import record_action_timeline_event
from app.services.protected_action_billing import (
    METER_RUNNER_EXECUTIONS,
    reserve_usage_meter,
)
from app.services._action_runner_core import (
    ActionCredentialReferenceError,
    ActionExecutionAttemptConflict,
    ActionExecutionAttemptNotFound,
    ActionExecutionNotAuthorized,
    ActionExecutionPlanError,
    ActionExecutionStateError,
    ActionRunnerError,
    ActionRunnerNotFound,
    CreatedExecutionAttempt,
    _json_dumps,
    _json_list,
    _json_loads,
    _now,
    get_action_runner,
    normalize_execution_plan_for_intent,
    validate_credential_ref,
)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _execution_request(intent: ActionIntent) -> dict[str, Any] | None:
    value = _json_loads(intent.execution_request_json, None)
    return value if isinstance(value, dict) else None


def _credential_pointer(request: Mapping[str, Any]) -> str | None:
    pointer = _text(request.get("credential_pointer"))
    credential = request.get("credential")
    if pointer is None and isinstance(credential, Mapping):
        pointer = _text(credential.get("pointer"))
    if pointer and "://" in pointer:
        raise ActionCredentialReferenceError(
            "execution_request credential_pointer must be a non-secret alias, not a protected credential ref."
        )
    return pointer


def _credential_ref_allowed_by_scope(scope: Mapping[str, Any], credential_ref: str) -> bool:
    allowed = scope.get("allowed_prefixes")
    if not isinstance(allowed, list) or not allowed:
        return True
    prefixes = [str(item).strip() for item in allowed if str(item).strip()]
    return not prefixes or any(credential_ref.startswith(prefix) for prefix in prefixes)


def _resolve_credential_ref_from_runner_scope(
    runner: ActionRunner,
    *,
    credential_pointer: str | None,
) -> str:
    scope = _json_loads(runner.credential_scope_json, {})
    if not isinstance(scope, Mapping):
        scope = {}
    credential_ref: str | None = None
    refs = scope.get("credential_refs")
    if refs is None:
        refs = scope.get("credentials")
    if credential_pointer:
        if isinstance(refs, Mapping):
            credential_ref = _text(refs.get(credential_pointer))
        if credential_ref is None:
            raise ActionCredentialReferenceError(
                f"runner {runner.id} does not define credential pointer {credential_pointer!r}."
            )
    else:
        credential_ref = _text(scope.get("default_credential_ref"))

    if credential_ref is None:
        raise ActionCredentialReferenceError(
            f"runner {runner.id} does not define a default credential_ref for backend-owned execution."
        )
    normalized = validate_credential_ref(credential_ref)
    if not _credential_ref_allowed_by_scope(scope, normalized):
        raise ActionCredentialReferenceError(
            f"runner {runner.id} credential_ref is outside the runner credential_scope allowed_prefixes."
        )
    return normalized


def _runner_matches_capability(
    runner: ActionRunner,
    *,
    intent: ActionIntent,
    execution_plan: Mapping[str, Any],
    capability: Mapping[str, Any],
) -> bool:
    if runner.status == "disabled":
        return False
    if runner.environment not in ("*", "all", intent.environment):
        return False
    if not _runner_supports_intent(runner, intent):
        return False
    runner_type = _text(capability.get("runner_type"))
    if runner_type and runner.runner_type != runner_type:
        return False
    capability_version = _text(capability.get("capability_version"))
    if capability_version and runner.capability_version != capability_version:
        return False
    operation_kind = _text(capability.get("operation_kind"))
    if operation_kind and operation_kind != intent.operation_kind:
        return False
    adapter = _text(capability.get("adapter"))
    if adapter and adapter != execution_plan.get("adapter"):
        return False
    operation = _text(capability.get("operation"))
    if operation and operation != execution_plan.get("operation"):
        return False
    return True


def _eligible_runners(
    db: Session,
    *,
    intent: ActionIntent,
    execution_plan: Mapping[str, Any],
    capability: Mapping[str, Any],
) -> list[ActionRunner]:
    rows = list(
        db.execute(
            select(ActionRunner)
            .where(ActionRunner.project_id == intent.project_id)
            .order_by(ActionRunner.created_at.asc(), ActionRunner.id.asc())
        ).scalars()
    )
    return [
        row
        for row in rows
        if _runner_matches_capability(
            row,
            intent=intent,
            execution_plan=execution_plan,
            capability=capability,
        )
    ]


def auto_create_execution_attempt_for_intent(
    db: Session,
    *,
    intent: ActionIntent,
    actor: str | None = None,
) -> CreatedExecutionAttempt | None:
    """Create the backend-owned claimable attempt for an authorized intent.

    The agent supplies an execution_request, not a runner id or protected
    credential ref. This resolver chooses a matching runner and resolves the
    protected credential reference from runner/project configuration.
    """
    request = _execution_request(intent)
    if request is None:
        return None
    if intent.status != "authorized":
        raise ActionExecutionNotAuthorized("Action intent must be authorized before execution can be planned.")

    existing = db.execute(
        select(ActionExecutionAttempt)
        .where(
            ActionExecutionAttempt.project_id == intent.project_id,
            ActionExecutionAttempt.action_intent_id == intent.id,
        )
        .order_by(ActionExecutionAttempt.attempt_number.asc(), ActionExecutionAttempt.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return CreatedExecutionAttempt(existing, created=False)

    execution_plan_raw = request.get("execution_plan")
    if not isinstance(execution_plan_raw, Mapping):
        raise ActionExecutionPlanError("execution_request.execution_plan must be an object.")
    normalized_plan = normalize_execution_plan_for_intent(
        intent=intent,
        execution_plan=execution_plan_raw,
    )
    capability_raw = request.get("capability")
    capability = capability_raw if isinstance(capability_raw, Mapping) else {}
    credential_pointer = _credential_pointer(request)

    last_credential_error: ActionCredentialReferenceError | None = None
    for runner in _eligible_runners(
        db,
        intent=intent,
        execution_plan=normalized_plan,
        capability=capability,
    ):
        try:
            credential_ref = _resolve_credential_ref_from_runner_scope(
                runner,
                credential_pointer=credential_pointer,
            )
        except ActionCredentialReferenceError as exc:
            last_credential_error = exc
            continue
        return create_execution_attempt(
            db,
            project_id=intent.project_id,
            action_id=intent.id,
            runner_id=runner.id,
            idempotency_key=f"auto-execution:{intent.id}",
            credential_ref=credential_ref,
            execution_plan=normalized_plan,
            requested_by_subject=actor,
        )

    if last_credential_error is not None:
        raise last_credential_error
    raise ActionRunnerNotFound("No action runner matched execution_request capability.")


def record_runner_heartbeat(
    db: Session,
    *,
    project_id: str,
    runner_id: str,
    status: str,
    heartbeat_payload: Mapping[str, Any] | None = None,
    supported_operation_kinds: list[str] | None = None,
    capability_version: str | None = None,
) -> ActionRunner:
    row = get_action_runner(db, project_id=project_id, runner_id=runner_id)
    row.status = status
    row.last_heartbeat_at = _now()
    row.heartbeat_payload_json = _json_dumps(heartbeat_payload)
    if supported_operation_kinds is not None:
        row.supported_operation_kinds_json = _json_list(supported_operation_kinds)
    if capability_version is not None:
        row.capability_version = capability_version
    db.add(row)
    db.flush()
    return row


def _runner_supports_intent(runner: ActionRunner, intent: ActionIntent) -> bool:
    supported = _json_loads(runner.supported_operation_kinds_json, [])
    if not supported:
        return True
    return intent.operation_kind in supported


def _build_execution_plan_document(
    *,
    intent: ActionIntent,
    runner: ActionRunner,
    credential_ref: str,
    execution_plan: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "action_intent_id": intent.id,
        "intent_digest": intent.intent_digest,
        "contract_version": f"{intent.contract_key}/{intent.contract_version}",
        "action_type": intent.action_type,
        "operation_kind": intent.operation_kind,
        "environment": intent.environment,
        "runner": {
            "id": runner.id,
            "type": runner.runner_type,
            "environment": runner.environment,
            "capability_version": runner.capability_version,
        },
        "credential_ref": credential_ref,
        "execution_plan": dict(execution_plan),
    }


def create_execution_attempt(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    runner_id: str,
    idempotency_key: str,
    credential_ref: str,
    execution_plan: Mapping[str, Any],
    requested_by_subject: str | None = None,
) -> CreatedExecutionAttempt:
    try:
        intent = get_action_intent(db, project_id=project_id, action_id=action_id)
    except ActionIntentNotFound as exc:
        raise ActionIntentNotFound(str(exc)) from exc
    if intent.status != "authorized":
        raise ActionExecutionNotAuthorized("Action intent must be authorized before execution can be planned.")

    runner = get_action_runner(db, project_id=project_id, runner_id=runner_id)
    if runner.status == "disabled":
        raise ActionRunnerError("Action runner is disabled.")
    if runner.environment not in ("*", "all", intent.environment):
        raise ActionRunnerError("Action runner environment does not match the action intent environment.")
    if not _runner_supports_intent(runner, intent):
        raise ActionRunnerError("Action runner does not support this action operation kind.")

    normalized_credential_ref = validate_credential_ref(credential_ref)
    normalized_execution_plan = normalize_execution_plan_for_intent(
        intent=intent,
        execution_plan=execution_plan,
    )
    plan_document = _build_execution_plan_document(
        intent=intent,
        runner=runner,
        credential_ref=normalized_credential_ref,
        execution_plan=normalized_execution_plan,
    )
    plan_canonical = canonical_json(plan_document)
    plan_digest = sha256_digest(plan_canonical)

    existing = db.execute(
        select(ActionExecutionAttempt).where(
            ActionExecutionAttempt.project_id == project_id,
            ActionExecutionAttempt.action_intent_id == action_id,
            ActionExecutionAttempt.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.plan_digest != plan_digest:
            raise ActionExecutionAttemptConflict(
                "Execution idempotency key already belongs to a different execution plan."
            )
        return CreatedExecutionAttempt(existing, created=False)

    attempt_number = int(
        db.execute(
            select(func.count(ActionExecutionAttempt.id)).where(
                ActionExecutionAttempt.project_id == project_id,
                ActionExecutionAttempt.action_intent_id == action_id,
            )
        ).scalar_one()
        or 0
    ) + 1

    reserve_usage_meter(db, project_id, METER_RUNNER_EXECUTIONS)
    row = ActionExecutionAttempt(
        project_id=project_id,
        action_intent_id=action_id,
        runner_id=runner_id,
        attempt_number=attempt_number,
        idempotency_key=idempotency_key,
        credential_ref=normalized_credential_ref,
        plan_digest=plan_digest,
        plan_json=plan_canonical,
        protected_credential_returned=False,
        requested_by_subject=requested_by_subject,
    )
    db.add(row)
    db.flush()
    record_action_timeline_event(
        db,
        project_id=project_id,
        action_id=action_id,
        event_type="execution_planned",
        payload={
            "execution_attempt_id": row.id,
            "runner_id": runner_id,
            "attempt_number": attempt_number,
            "idempotency_key": idempotency_key,
            "plan_digest": plan_digest,
            "credential_ref": normalized_credential_ref,
        },
        actor=requested_by_subject,
    )
    return CreatedExecutionAttempt(row, created=True)


def list_execution_attempts(
    db: Session,
    *,
    project_id: str,
    action_id: str,
) -> list[ActionExecutionAttempt]:
    get_action_intent(db, project_id=project_id, action_id=action_id)
    return list(
        db.execute(
            select(ActionExecutionAttempt)
            .where(
                ActionExecutionAttempt.project_id == project_id,
                ActionExecutionAttempt.action_intent_id == action_id,
            )
            .order_by(ActionExecutionAttempt.attempt_number.asc(), ActionExecutionAttempt.created_at.asc())
        ).scalars()
    )


def list_project_execution_attempts(
    db: Session,
    *,
    project_id: str,
    statuses: list[str] | None = None,
    stale: bool = False,
    stale_after_seconds: int = 600,
    limit: int = 50,
    offset: int = 0,
    now: datetime | None = None,
    max_limit: int = 100,
) -> list[ActionExecutionAttempt]:
    query = select(ActionExecutionAttempt).where(ActionExecutionAttempt.project_id == project_id)
    if statuses:
        query = query.where(ActionExecutionAttempt.status.in_(statuses))
    if stale:
        cutoff = (now or _now()) - timedelta(seconds=max(1, int(stale_after_seconds)))
        query = query.where(ActionExecutionAttempt.updated_at <= cutoff)
    return list(
        db.execute(
            query.order_by(ActionExecutionAttempt.updated_at.asc(), ActionExecutionAttempt.created_at.asc())
            .offset(max(0, int(offset)))
            .limit(max(1, min(max(1, int(max_limit)), int(limit))))
        ).scalars()
    )


def get_execution_attempt(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    attempt_id: str,
) -> ActionExecutionAttempt:
    row = db.execute(
        select(ActionExecutionAttempt).where(
            ActionExecutionAttempt.project_id == project_id,
            ActionExecutionAttempt.action_intent_id == action_id,
            ActionExecutionAttempt.id == attempt_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ActionExecutionAttemptNotFound("Action execution attempt not found.")
    return row


def _merge_result_summary(row: ActionExecutionAttempt, payload: Mapping[str, Any] | None) -> dict[str, Any]:
    current = _json_loads(row.result_summary_json, {})
    if not isinstance(current, dict):
        current = {}
    if payload:
        current.update(dict(payload))
    return current


def _set_execution_attempt_status(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    attempt_id: str,
    status: str,
    allowed_from: set[str],
    result_summary: Mapping[str, Any] | None = None,
    error_message: str | None = None,
    actor: str | None = None,
) -> ActionExecutionAttempt:
    row = get_execution_attempt(db, project_id=project_id, action_id=action_id, attempt_id=attempt_id)
    if row.status not in allowed_from:
        raise ActionExecutionStateError(f"Execution attempt cannot move from {row.status!r} to {status!r}.")
    now = _now()
    row.status = status
    if status == "running" and row.started_at is None:
        row.started_at = now
    if status in {"succeeded", "failed", "ambiguous", "cancelled"}:
        if row.started_at is None:
            row.started_at = now
        row.finished_at = now
    row.result_summary_json = _json_dumps(_merge_result_summary(row, result_summary))
    row.error_message = error_message
    row.protected_credential_returned = False
    db.add(row)
    db.flush()
    record_action_timeline_event(
        db,
        project_id=project_id,
        action_id=action_id,
        event_type=f"execution_{status}",
        payload={
            "execution_attempt_id": row.id,
            "runner_id": row.runner_id,
            "attempt_number": row.attempt_number,
            "status": status,
            "result_summary": _merge_result_summary(row, None),
            "error_message": error_message,
        },
        actor=actor,
    )
    return row


def dispatch_execution_attempt(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    attempt_id: str,
    dispatch_metadata: Mapping[str, Any] | None = None,
    actor: str | None = None,
) -> ActionExecutionAttempt:
    return _set_execution_attempt_status(
        db,
        project_id=project_id,
        action_id=action_id,
        attempt_id=attempt_id,
        status="dispatched",
        allowed_from={"planned"},
        result_summary={"dispatch": dict(dispatch_metadata or {})},
        actor=actor,
    )


def start_execution_attempt(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    attempt_id: str,
    runner_metadata: Mapping[str, Any] | None = None,
    actor: str | None = None,
) -> ActionExecutionAttempt:
    return _set_execution_attempt_status(
        db,
        project_id=project_id,
        action_id=action_id,
        attempt_id=attempt_id,
        status="running",
        allowed_from={"planned", "dispatched"},
        result_summary={"runner": dict(runner_metadata or {})},
        actor=actor,
    )


def claim_next_execution_attempt(
    db: Session,
    *,
    project_id: str,
    runner_id: str,
    runner_metadata: Mapping[str, Any] | None = None,
    actor: str | None = None,
) -> ActionExecutionAttempt:
    get_action_runner(db, project_id=project_id, runner_id=runner_id)
    row = db.execute(
        select(ActionExecutionAttempt)
        .where(
            ActionExecutionAttempt.project_id == project_id,
            ActionExecutionAttempt.runner_id == runner_id,
            ActionExecutionAttempt.status.in_(("planned", "dispatched")),
        )
        .order_by(ActionExecutionAttempt.created_at.asc(), ActionExecutionAttempt.attempt_number.asc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise ActionExecutionAttemptNotFound("No claimable execution attempt found for this runner.")
    return _set_execution_attempt_status(
        db,
        project_id=project_id,
        action_id=row.action_intent_id,
        attempt_id=row.id,
        status="running",
        allowed_from={"planned", "dispatched"},
        result_summary={"runner": {"claimed": True, **dict(runner_metadata or {})}},
        actor=actor,
    )


def finish_execution_attempt(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    attempt_id: str,
    final_status: str,
    result_summary: Mapping[str, Any] | None = None,
    error_message: str | None = None,
    actor: str | None = None,
) -> ActionExecutionAttempt:
    if final_status not in {"succeeded", "failed", "ambiguous", "cancelled"}:
        raise ActionExecutionStateError("final_status must be succeeded, failed, ambiguous, or cancelled.")
    row = _set_execution_attempt_status(
        db,
        project_id=project_id,
        action_id=action_id,
        attempt_id=attempt_id,
        status=final_status,
        allowed_from={"planned", "dispatched", "running"},
        result_summary=result_summary,
        error_message=error_message,
        actor=actor,
    )
    from app.services.action_post_execution import enqueue_post_execution_verification

    enqueue_post_execution_verification(
        db,
        project_id=project_id,
        action_id=action_id,
        attempt_id=attempt_id,
        actor=actor,
    )
    return row


def action_runner_supported_operation_kinds(row: ActionRunner) -> list[str]:
    value = _json_loads(row.supported_operation_kinds_json, [])
    return value if isinstance(value, list) else []


def action_runner_credential_scope(row: ActionRunner) -> dict[str, Any]:
    value = _json_loads(row.credential_scope_json, {})
    return value if isinstance(value, dict) else {}


def action_runner_heartbeat_payload(row: ActionRunner) -> dict[str, Any]:
    value = _json_loads(row.heartbeat_payload_json, {})
    return value if isinstance(value, dict) else {}


def execution_attempt_plan(row: ActionExecutionAttempt) -> dict[str, Any]:
    value = _json_loads(row.plan_json, {})
    return value if isinstance(value, dict) else {}


def execution_attempt_result_summary(row: ActionExecutionAttempt) -> dict[str, Any]:
    value = _json_loads(row.result_summary_json, {})
    return value if isinstance(value, dict) else {}
