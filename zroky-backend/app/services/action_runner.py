from __future__ import annotations

import json
from dataclasses import dataclass
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


class ActionRunnerError(ValueError):
    pass


class ActionRunnerConflict(ActionRunnerError):
    pass


class ActionRunnerNotFound(ActionRunnerError):
    pass


class ActionExecutionAttemptConflict(ActionRunnerError):
    pass


class ActionExecutionAttemptNotFound(ActionRunnerError):
    pass


class ActionExecutionStateError(ActionRunnerError):
    pass


class ActionExecutionNotAuthorized(ActionRunnerError):
    pass


class ActionCredentialReferenceError(ActionRunnerError):
    pass


class ActionExecutionPlanError(ActionRunnerError):
    pass


ALLOWED_CREDENTIAL_REF_PREFIXES = (
    "zroky-secret://",
    "vault://",
    "aws-secretsmanager://",
    "gcp-secretmanager://",
    "azure-keyvault://",
    "customer-runner-secret://",
)

RAW_SECRET_KEY_MARKERS = (
    "authorization",
    "bearer_token",
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
)
RAW_SECRET_VALUE_MARKERS = (
    "bearer ",
    "sk_live_",
    "sk_test_",
    "xoxb-",
    "xoxp-",
    "ghp_",
    "gho_",
    "github_pat_",
    "-----begin private key-----",
)

EXECUTION_ADAPTER_CONTRACTS: dict[str, dict[str, Any]] = {
    "stripe_refund": {
        "adapter": "stripe_refund",
        "display_name": "Stripe refund runner",
        "operation_kinds": ["TRANSFER"],
        "operations": ["refund.create", "refund.cancel"],
        "required_target_fields": ["refund_id"],
        "required_argument_fields": ["amount_minor", "currency"],
        "required_result_fields": ["provider_ref", "status"],
        "verification_connector": "ledger_refund_api",
    },
    "razorpay_refund": {
        "adapter": "razorpay_refund",
        "display_name": "Razorpay refund runner",
        "operation_kinds": ["TRANSFER"],
        "operations": ["refund.create", "refund.cancel"],
        "required_target_fields": ["refund_id"],
        "required_argument_fields": ["amount_minor", "currency"],
        "required_result_fields": ["provider_ref", "status"],
        "verification_connector": "ledger_refund_api",
    },
    "zendesk_ticket": {
        "adapter": "zendesk_ticket",
        "display_name": "Zendesk ticket update runner",
        "operation_kinds": ["UPDATE"],
        "operations": ["ticket.update"],
        "required_target_fields": ["ticket_id"],
        "required_argument_fields": ["fields"],
        "required_result_fields": ["provider_ref", "status"],
        "verification_connector": "zendesk_ticket",
    },
    "customer_message": {
        "adapter": "customer_message",
        "display_name": "Customer message runner",
        "operation_kinds": ["SEND"],
        "operations": ["message.send"],
        "required_target_fields": ["recipient"],
        "required_argument_fields": ["body"],
        "required_result_fields": ["provider_ref", "delivery_status"],
        "verification_connector": "generic_rest_api",
    },
    "generic_rest": {
        "adapter": "generic_rest",
        "display_name": "Generic REST protected action runner",
        "operation_kinds": ["UPDATE", "SEND", "EXECUTE"],
        "operations": ["rest.post", "rest.patch", "rest.put", "workflow.execute"],
        "required_target_fields": ["resource_ref"],
        "required_argument_fields": [],
        "required_result_fields": ["provider_ref", "status"],
        "verification_connector": "generic_rest_api",
    },
}


@dataclass(frozen=True)
class RegisteredActionRunner:
    row: ActionRunner
    created: bool


@dataclass(frozen=True)
class CreatedExecutionAttempt:
    row: ActionExecutionAttempt
    created: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _json_list(value: list[str] | tuple[str, ...] | None) -> str:
    return json.dumps(list(value or []), ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def validate_credential_ref(credential_ref: str) -> str:
    normalized = credential_ref.strip()
    if not normalized:
        raise ActionCredentialReferenceError("credential_ref is required.")
    if not normalized.startswith(ALLOWED_CREDENTIAL_REF_PREFIXES):
        raise ActionCredentialReferenceError(
            "credential_ref must be a protected reference, not a raw secret."
        )
    if any(marker in normalized.lower() for marker in ("sk_live_", "sk_test_", "secret=", "password=", "bearer ")):
        raise ActionCredentialReferenceError("credential_ref appears to contain raw secret material.")
    return normalized


def list_execution_adapter_contracts() -> list[dict[str, Any]]:
    return [
        {
            **contract,
            "schema_version": "zroky.execution_adapter.v1",
            "credential_boundary": "runner_resolves_credential_ref",
            "protected_credential_returned": False,
        }
        for contract in EXECUTION_ADAPTER_CONTRACTS.values()
    ]


def _contains_raw_secret(value: Any, *, key_path: tuple[str, ...] = ()) -> str | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key).strip().lower()
            if any(marker in key_text for marker in RAW_SECRET_KEY_MARKERS):
                return ".".join((*key_path, str(key)))
            found = _contains_raw_secret(nested, key_path=(*key_path, str(key)))
            if found is not None:
                return found
        return None
    if isinstance(value, list | tuple):
        for index, nested in enumerate(value):
            found = _contains_raw_secret(nested, key_path=(*key_path, str(index)))
            if found is not None:
                return found
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if any(marker in lowered for marker in RAW_SECRET_VALUE_MARKERS):
            return ".".join(key_path) or "execution_plan"
    return None


def _required_fields_missing(
    payload: Mapping[str, Any],
    fields: list[str],
) -> list[str]:
    missing: list[str] = []
    for field in fields:
        value = payload.get(field)
        if value is None:
            missing.append(field)
        elif isinstance(value, str) and not value.strip():
            missing.append(field)
    return missing


def normalize_execution_plan_for_intent(
    *,
    intent: ActionIntent,
    execution_plan: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(execution_plan, Mapping):
        raise ActionExecutionPlanError("execution_plan must be an object.")
    raw_secret_path = _contains_raw_secret(execution_plan)
    if raw_secret_path is not None:
        raise ActionExecutionPlanError(
            f"execution_plan must not include raw secret material at {raw_secret_path}."
        )

    adapter = str(execution_plan.get("adapter") or "").strip().lower()
    if not adapter:
        raise ActionExecutionPlanError("execution_plan.adapter is required.")
    contract = EXECUTION_ADAPTER_CONTRACTS.get(adapter)
    if contract is None:
        raise ActionExecutionPlanError(f"Unsupported execution adapter: {adapter}.")
    if intent.operation_kind not in set(contract["operation_kinds"]):
        allowed = ", ".join(contract["operation_kinds"])
        raise ActionExecutionPlanError(
            f"Execution adapter {adapter} does not support {intent.operation_kind}; allowed operation kinds: {allowed}."
        )

    operation = str(execution_plan.get("operation") or "").strip()
    if not operation:
        raise ActionExecutionPlanError("execution_plan.operation is required.")
    if operation not in set(contract["operations"]):
        allowed = ", ".join(contract["operations"])
        raise ActionExecutionPlanError(
            f"Execution adapter {adapter} does not support operation {operation}; allowed operations: {allowed}."
        )

    target = execution_plan.get("target")
    if not isinstance(target, Mapping) or not target:
        raise ActionExecutionPlanError("execution_plan.target must be a non-empty object.")
    arguments = execution_plan.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, Mapping):
        raise ActionExecutionPlanError("execution_plan.arguments must be an object when provided.")

    missing_target = _required_fields_missing(target, contract["required_target_fields"])
    if missing_target:
        raise ActionExecutionPlanError(
            f"execution_plan.target missing required field(s): {', '.join(missing_target)}."
        )
    missing_arguments = _required_fields_missing(arguments, contract["required_argument_fields"])
    if missing_arguments:
        raise ActionExecutionPlanError(
            f"execution_plan.arguments missing required field(s): {', '.join(missing_arguments)}."
        )

    verification = execution_plan.get("verification")
    if verification is None:
        verification = {}
    if not isinstance(verification, Mapping):
        raise ActionExecutionPlanError("execution_plan.verification must be an object when provided.")

    return {
        **dict(execution_plan),
        "adapter": adapter,
        "operation": operation,
        "target": dict(target),
        "arguments": dict(arguments),
        "verification": {
            "connector": contract["verification_connector"],
            **dict(verification),
        },
        "adapter_contract": {
            "schema_version": "zroky.execution_adapter.v1",
            "adapter": adapter,
            "operation_kind": intent.operation_kind,
            "required_result_fields": list(contract["required_result_fields"]),
            "verification_connector": contract["verification_connector"],
            "credential_boundary": "runner_resolves_credential_ref",
            "protected_credential_returned": False,
        },
    }


def register_action_runner(
    db: Session,
    *,
    project_id: str,
    name: str,
    runner_type: str,
    environment: str,
    supported_operation_kinds: list[str] | None = None,
    credential_scope: Mapping[str, Any] | None = None,
    capability_version: str | None = None,
    registered_by_subject: str | None = None,
) -> RegisteredActionRunner:
    existing = db.execute(
        select(ActionRunner).where(
            ActionRunner.project_id == project_id,
            ActionRunner.name == name,
            ActionRunner.environment == environment,
        )
    ).scalar_one_or_none()
    supported_json = _json_list(supported_operation_kinds)
    scope_json = _json_dumps(credential_scope)
    if existing is not None:
        if existing.runner_type != runner_type:
            raise ActionRunnerConflict("Action runner already exists with a different runner_type.")
        existing.supported_operation_kinds_json = supported_json
        existing.credential_scope_json = scope_json
        existing.capability_version = capability_version
        db.add(existing)
        db.flush()
        return RegisteredActionRunner(existing, created=False)

    row = ActionRunner(
        project_id=project_id,
        name=name,
        runner_type=runner_type,
        environment=environment,
        supported_operation_kinds_json=supported_json,
        credential_scope_json=scope_json,
        capability_version=capability_version,
        registered_by_subject=registered_by_subject,
    )
    db.add(row)
    db.flush()
    return RegisteredActionRunner(row, created=True)


def get_action_runner(db: Session, *, project_id: str, runner_id: str) -> ActionRunner:
    row = db.execute(
        select(ActionRunner).where(
            ActionRunner.project_id == project_id,
            ActionRunner.id == runner_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ActionRunnerNotFound("Action runner not found.")
    return row


def list_action_runners(db: Session, *, project_id: str) -> list[ActionRunner]:
    return list(
        db.execute(
            select(ActionRunner)
            .where(ActionRunner.project_id == project_id)
            .order_by(ActionRunner.created_at.desc(), ActionRunner.id.desc())
        ).scalars()
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
            .limit(max(1, min(100, int(limit))))
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
