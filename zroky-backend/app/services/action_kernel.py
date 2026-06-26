from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ActionContractVersion, ActionIntent, RuntimePolicyDecision
from app.services.action_timeline import record_action_timeline_event
from app.services.protected_action_billing import (
    METER_POLICY_CHECKS,
    METER_PROTECTED_ACTIONS,
    reserve_usage_meter,
)
from app.services.runtime_policy import RuntimePolicyResult, evaluate_runtime_policy


class ActionKernelError(ValueError):
    pass


class ActionContractConflict(ActionKernelError):
    pass


class ActionContractNotFound(ActionKernelError):
    pass


class ActionIntentConflict(ActionKernelError):
    pass


class ActionIntentNotFound(ActionKernelError):
    pass


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _stable_json(value: Any) -> str:
    return _json_dumps(value if value is not None else {})


def canonical_json(value: Mapping[str, Any]) -> str:
    """Return deterministic JSON for digesting typed action intents.

    This is the first kernel slice. It uses strict sorted JSON today and keeps
    the call site isolated so an RFC 8785 implementation can replace it without
    changing the ActionIntent storage model.
    """

    return _json_dumps(value)


def sha256_digest(canonical_payload: str) -> str:
    return f"sha256:{hashlib.sha256(canonical_payload.encode('utf-8')).hexdigest()}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


@dataclass(frozen=True)
class RegisteredActionContract:
    row: ActionContractVersion
    created: bool


@dataclass(frozen=True)
class CreatedActionIntent:
    row: ActionIntent
    created: bool


@dataclass(frozen=True)
class ActionIntentDecision:
    row: ActionIntent
    runtime_result: RuntimePolicyResult | None
    allowed: bool
    requires_approval: bool
    reasons: list[str]


def schema_digest(schema: Mapping[str, Any]) -> str:
    return sha256_digest(canonical_json(schema))


def register_action_contract(
    db: Session,
    *,
    project_id: str,
    contract_key: str,
    version: str,
    action_type: str,
    operation_kind: str,
    domain_family: str,
    schema: Mapping[str, Any],
    risk_class: str = "R2",
    verification_profile: Mapping[str, Any] | None = None,
    connector_family: str | None = None,
    created_by_subject: str | None = None,
) -> RegisteredActionContract:
    existing = db.execute(
        select(ActionContractVersion).where(
            ActionContractVersion.project_id == project_id,
            ActionContractVersion.contract_key == contract_key,
            ActionContractVersion.version == version,
        )
    ).scalar_one_or_none()
    digest = schema_digest(schema)
    if existing is not None:
        if existing.schema_digest != digest:
            raise ActionContractConflict("Action contract version already exists with a different schema digest.")
        return RegisteredActionContract(existing, created=False)

    row = ActionContractVersion(
        project_id=project_id,
        contract_key=contract_key,
        version=version,
        action_type=action_type,
        operation_kind=operation_kind,
        domain_family=domain_family,
        schema_digest=digest,
        schema_json=canonical_json(schema),
        risk_class=risk_class,
        verification_profile_json=_stable_json(verification_profile),
        connector_family=connector_family,
        created_by_subject=created_by_subject,
    )
    db.add(row)
    db.flush()
    return RegisteredActionContract(row, created=True)


def get_action_contract(
    db: Session,
    *,
    project_id: str,
    contract_key: str,
    version: str,
) -> ActionContractVersion:
    row = db.execute(
        select(ActionContractVersion).where(
            ActionContractVersion.project_id == project_id,
            ActionContractVersion.contract_key == contract_key,
            ActionContractVersion.version == version,
            ActionContractVersion.status == "active",
        )
    ).scalar_one_or_none()
    if row is None:
        raise ActionContractNotFound("Action contract version not found.")
    return row


def split_contract_version(contract_version: str) -> tuple[str, str]:
    contract_version = contract_version.strip()
    if "/" not in contract_version:
        raise ActionKernelError("contract_version must use '<contract_key>/<version>'.")
    contract_key, version = contract_version.rsplit("/", 1)
    contract_key = contract_key.strip()
    version = version.strip()
    if not contract_key or not version:
        raise ActionKernelError("contract_version must include a contract key and version.")
    return contract_key, version


def build_intent_payload(
    *,
    contract_key: str,
    version: str,
    action_type: str,
    operation_kind: str,
    environment: str,
    principal: Mapping[str, Any],
    actor_chain: list[Mapping[str, Any]],
    purpose: Mapping[str, Any],
    resource: Mapping[str, Any],
    parameters: Mapping[str, Any],
    verification_profile: str | None,
    deadline_at: datetime | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_version": f"{contract_key}/{version}",
        "action_type": action_type,
        "operation_kind": operation_kind,
        "environment": environment,
        "principal": principal,
        "actor_chain": actor_chain,
        "purpose": purpose,
        "resource": resource,
        "parameters": parameters,
    }
    if verification_profile:
        payload["verification_profile"] = verification_profile
    if deadline_at:
        payload["deadline"] = deadline_at.astimezone().isoformat()
    return payload


def create_action_intent(
    db: Session,
    *,
    project_id: str,
    contract_version: str,
    action_type: str,
    operation_kind: str,
    environment: str,
    idempotency_key: str,
    principal: Mapping[str, Any],
    actor_chain: list[Mapping[str, Any]],
    purpose: Mapping[str, Any],
    resource: Mapping[str, Any],
    parameters: Mapping[str, Any],
    verification_profile: str | None = None,
    deadline_at: datetime | None = None,
    trace_context: Mapping[str, Any] | None = None,
) -> CreatedActionIntent:
    contract_key, version = split_contract_version(contract_version)
    contract = get_action_contract(db, project_id=project_id, contract_key=contract_key, version=version)
    if contract.action_type != action_type or contract.operation_kind != operation_kind:
        raise ActionKernelError("Action intent does not match the registered contract action type or operation kind.")

    payload = build_intent_payload(
        contract_key=contract_key,
        version=version,
        action_type=action_type,
        operation_kind=operation_kind,
        environment=environment,
        principal=principal,
        actor_chain=actor_chain,
        purpose=purpose,
        resource=resource,
        parameters=parameters,
        verification_profile=verification_profile,
        deadline_at=deadline_at,
    )
    canonical = canonical_json(payload)
    digest = sha256_digest(canonical)

    existing = db.execute(
        select(ActionIntent).where(
            ActionIntent.project_id == project_id,
            ActionIntent.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.intent_digest != digest:
            raise ActionIntentConflict("Idempotency key already belongs to a different action intent.")
        return CreatedActionIntent(existing, created=False)

    reserve_usage_meter(db, project_id, METER_PROTECTED_ACTIONS)
    row = ActionIntent(
        project_id=project_id,
        contract_version_id=contract.id,
        contract_key=contract_key,
        contract_version=version,
        action_type=action_type,
        operation_kind=operation_kind,
        environment=environment,
        idempotency_key=idempotency_key,
        intent_digest=digest,
        canonical_intent_json=canonical,
        principal_json=_stable_json(principal),
        actor_chain_json=_json_dumps(actor_chain),
        purpose_json=_stable_json(purpose),
        resource_json=_stable_json(resource),
        parameters_json=_stable_json(parameters),
        verification_profile=verification_profile,
        trace_context_json=_stable_json(trace_context),
        deadline_at=deadline_at,
    )
    db.add(row)
    db.flush()
    record_action_timeline_event(
        db,
        project_id=project_id,
        action_id=row.id,
        event_type="intent_created",
        payload={
            "contract_version": f"{contract_key}/{version}",
            "action_type": action_type,
            "operation_kind": operation_kind,
            "environment": environment,
            "idempotency_key": idempotency_key,
            "intent_digest": digest,
        },
        actor=str(principal.get("id")) if isinstance(principal, Mapping) and principal.get("id") else None,
    )
    return CreatedActionIntent(row, created=True)


def get_action_intent(
    db: Session,
    *,
    project_id: str,
    action_id: str,
) -> ActionIntent:
    row = db.execute(
        select(ActionIntent).where(
            ActionIntent.project_id == project_id,
            ActionIntent.id == action_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ActionIntentNotFound("Action intent not found.")
    return row


def _first_actor_chain_value(actor_chain: Any, key: str) -> str | None:
    if not isinstance(actor_chain, list):
        return None
    for actor in actor_chain:
        if isinstance(actor, dict) and actor.get(key):
            return str(actor[key])
    return None


def build_runtime_policy_payload(
    intent: ActionIntent,
    *,
    approval_id: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    trace_context = _json_loads(intent.trace_context_json, {})
    principal = _json_loads(intent.principal_json, {})
    actor_chain = _json_loads(intent.actor_chain_json, [])
    purpose = _json_loads(intent.purpose_json, {})
    resource = _json_loads(intent.resource_json, {})
    parameters = _json_loads(intent.parameters_json, {})
    agent_name = (
        trace_context.get("agent_name")
        or _first_actor_chain_value(actor_chain, "id")
        or _first_actor_chain_value(actor_chain, "name")
        or principal.get("id")
    )
    runtime_payload: dict[str, Any] = {
        "trace_id": trace_context.get("trace_id"),
        "span_id": trace_context.get("span_id"),
        "call_id": trace_context.get("call_id"),
        "agent_name": agent_name,
        "role": principal.get("role") or principal.get("type"),
        "actor": actor or principal.get("id") or agent_name,
        "action_type": intent.action_type,
        "operation_kind": intent.operation_kind,
        "tool_name": intent.action_type,
        "tool_args": {
            "contract_version": f"{intent.contract_key}/{intent.contract_version}",
            "intent_digest": intent.intent_digest,
            "resource": resource,
            "parameters": parameters,
        },
        "external_action": intent.operation_kind != "READ_SENSITIVE",
        "business_impact": {
            "summary": purpose.get("summary") or purpose.get("code") or intent.action_type,
            "resource_id": resource.get("id") if isinstance(resource, dict) else None,
            "estimated_value_usd": purpose.get("estimated_value_usd") or purpose.get("impact_usd"),
        },
        "environment": intent.environment,
        "zroky_action_id": intent.id,
    }
    if approval_id:
        runtime_payload["approval_id"] = approval_id
    return runtime_payload


def _linked_policy_decision(
    db: Session,
    *,
    project_id: str,
    decision_id: str | None,
) -> RuntimePolicyDecision | None:
    if not decision_id:
        return None
    return db.execute(
        select(RuntimePolicyDecision).where(
            RuntimePolicyDecision.project_id == project_id,
            RuntimePolicyDecision.id == decision_id,
        )
    ).scalar_one_or_none()


def decide_action_intent(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    approval_id: str | None = None,
    actor: str | None = None,
) -> ActionIntentDecision:
    intent = get_action_intent(db, project_id=project_id, action_id=action_id)
    linked_decision = _linked_policy_decision(
        db,
        project_id=project_id,
        decision_id=intent.runtime_policy_decision_id,
    )
    if intent.status == "authorized":
        return ActionIntentDecision(intent, runtime_result=None, allowed=True, requires_approval=False, reasons=["action intent already authorized"])
    reserve_usage_meter(db, project_id, METER_POLICY_CHECKS)
    if linked_decision is not None and linked_decision.status == "rejected":
        intent.status = "denied"
        intent.decided_at = _now()
        intent.authorized_at = None
        db.add(intent)
        db.flush()
        record_action_timeline_event(
            db,
            project_id=project_id,
            action_id=intent.id,
            event_type="policy_decided",
            payload={
                "status": intent.status,
                "runtime_policy_decision_id": linked_decision.id,
                "allowed": False,
                "requires_approval": False,
                "reasons": ["linked approval was rejected"],
            },
            actor=actor,
        )
        return ActionIntentDecision(intent, runtime_result=None, allowed=False, requires_approval=False, reasons=["linked approval was rejected"])
    if linked_decision is not None and linked_decision.status == "expired":
        intent.status = "expired"
        intent.decided_at = _now()
        intent.authorized_at = None
        db.add(intent)
        db.flush()
        record_action_timeline_event(
            db,
            project_id=project_id,
            action_id=intent.id,
            event_type="policy_decided",
            payload={
                "status": intent.status,
                "runtime_policy_decision_id": linked_decision.id,
                "allowed": False,
                "requires_approval": False,
                "reasons": ["linked approval expired"],
            },
            actor=actor,
        )
        return ActionIntentDecision(intent, runtime_result=None, allowed=False, requires_approval=False, reasons=["linked approval expired"])

    effective_approval_id = approval_id
    if effective_approval_id is None and linked_decision is not None and linked_decision.status == "approved":
        effective_approval_id = linked_decision.id

    intent.status = "deciding"
    db.add(intent)
    db.flush()
    result = evaluate_runtime_policy(
        db,
        project_id=project_id,
        payload=build_runtime_policy_payload(intent, approval_id=effective_approval_id, actor=actor),
    )
    intent.runtime_policy_decision_id = result.decision.id
    intent.decided_at = _now()
    if result.allowed:
        intent.status = "authorized"
        intent.authorized_at = intent.decided_at
    elif result.requires_approval:
        intent.status = "approval_pending"
        intent.authorized_at = None
    else:
        intent.status = "denied"
        intent.authorized_at = None
    db.add(intent)
    db.flush()
    record_action_timeline_event(
        db,
        project_id=project_id,
        action_id=intent.id,
        event_type="policy_decided",
        payload={
            "status": intent.status,
            "runtime_policy_decision_id": result.decision.id,
            "allowed": result.allowed,
            "requires_approval": result.requires_approval,
            "reasons": result.reasons,
        },
        actor=actor,
    )
    return ActionIntentDecision(
        intent,
        runtime_result=result,
        allowed=result.allowed,
        requires_approval=result.requires_approval,
        reasons=result.reasons,
    )
