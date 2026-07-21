from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
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
    "openbao://",
    "bao://",
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
LOCAL_VAULT_CREDENTIAL_REF_PREFIXES = ("vault://", "openbao://", "bao://")
CAPABILITY_MANIFEST_SCHEMA_VERSION = "zroky.runner_capability_manifest.v1"
ENFORCEMENT_SCHEMA_VERSION = "zroky.executor_enforcement.v1"
EXECUTOR_ENFORCEMENT_OPTIONS = {
    "isolation": ["gvisor"],
    "policy": ["kyverno"],
    "telemetry": ["tetragon"],
}

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
    settings = get_settings()
    if settings.CUSTOMER_LOCAL_SECRETS_MODE:
        prefixes = tuple(
            item.strip()
            for item in settings.CUSTOMER_LOCAL_SECRET_REF_PREFIXES.split(",")
            if item.strip()
        ) or LOCAL_VAULT_CREDENTIAL_REF_PREFIXES
        if not normalized.startswith(prefixes):
            raise ActionCredentialReferenceError(
                "credential_ref must point to the customer-local Vault/OpenBao secret backend."
            )
    return normalized


def list_execution_adapter_contracts() -> list[dict[str, Any]]:
    return [
        {
            **contract,
            "schema_version": "zroky.execution_adapter.v1",
            "credential_boundary": "runner_resolves_credential_ref",
            "protected_credential_returned": False,
            "executor_enforcement_options": EXECUTOR_ENFORCEMENT_OPTIONS,
        }
        for contract in EXECUTION_ADAPTER_CONTRACTS.values()
    ]


def _normalize_executor_enforcement(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ActionRunnerError("capability_manifest.enforcement must be an object.")
    schema_version = str(value.get("schema_version") or ENFORCEMENT_SCHEMA_VERSION).strip()
    if schema_version != ENFORCEMENT_SCHEMA_VERSION:
        raise ActionRunnerError(f"capability_manifest.enforcement.schema_version must be {ENFORCEMENT_SCHEMA_VERSION}.")
    normalized: dict[str, Any] = {"schema_version": ENFORCEMENT_SCHEMA_VERSION}
    for key, allowed in EXECUTOR_ENFORCEMENT_OPTIONS.items():
        selected = str(value.get(key) or "").strip().lower()
        if not selected:
            continue
        if selected not in allowed:
            raise ActionRunnerError(
                f"capability_manifest.enforcement.{key} must be one of: {', '.join(allowed)}."
            )
        normalized[key] = selected
    if len(normalized) == 1:
        raise ActionRunnerError("capability_manifest.enforcement must declare isolation, policy, or telemetry.")
    references = value.get("references")
    if references is not None:
        if not isinstance(references, Mapping):
            raise ActionRunnerError("capability_manifest.enforcement.references must be an object.")
        normalized["references"] = {str(key): str(item) for key, item in references.items()}
    return normalized


def normalize_capability_manifest(manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return {}
    if not isinstance(manifest, Mapping):
        raise ActionRunnerError("capability_manifest must be an object.")
    payload = {key: value for key, value in dict(manifest).items() if key != "signature"}
    if payload.get("schema_version") != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ActionRunnerError(f"capability_manifest.schema_version must be {CAPABILITY_MANIFEST_SCHEMA_VERSION}.")
    signature = manifest.get("signature")
    if not isinstance(signature, Mapping) or not str(signature.get("digest") or "").strip():
        raise ActionRunnerError("capability_manifest.signature.digest is required.")
    if str(signature["digest"]).strip() != sha256_digest(canonical_json(payload)):
        raise ActionRunnerError("capability_manifest signature digest does not match payload.")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise ActionRunnerError("capability_manifest.capabilities must be a non-empty list.")
    normalized_capabilities: list[dict[str, str]] = []
    for item in capabilities:
        if not isinstance(item, Mapping):
            raise ActionRunnerError("capability_manifest capabilities must be objects.")
        adapter = str(item.get("adapter") or "").strip().lower()
        operation_kind = str(item.get("operation_kind") or "").strip()
        operation = str(item.get("operation") or "").strip()
        contract = EXECUTION_ADAPTER_CONTRACTS.get(adapter)
        if contract is None:
            raise ActionRunnerError(f"Unsupported capability adapter: {adapter}.")
        if operation_kind not in contract["operation_kinds"]:
            raise ActionRunnerError(f"Capability adapter {adapter} does not allow operation_kind {operation_kind}.")
        if operation not in contract["operations"]:
            raise ActionRunnerError(f"Capability adapter {adapter} does not allow operation {operation}.")
        normalized_capabilities.append({"adapter": adapter, "operation_kind": operation_kind, "operation": operation})
    normalized = {**payload, "capabilities": normalized_capabilities, "signature": dict(signature)}
    enforcement = _normalize_executor_enforcement(payload.get("enforcement"))
    if enforcement is not None:
        normalized["enforcement"] = enforcement
    return normalized


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
    capability_manifest: Mapping[str, Any] | None = None,
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
    manifest_json = _json_dumps(normalize_capability_manifest(capability_manifest))
    if existing is not None:
        if existing.runner_type != runner_type:
            raise ActionRunnerConflict("Action runner already exists with a different runner_type.")
        existing.supported_operation_kinds_json = supported_json
        existing.credential_scope_json = scope_json
        existing.capability_manifest_json = manifest_json
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
        capability_manifest_json=manifest_json,
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
