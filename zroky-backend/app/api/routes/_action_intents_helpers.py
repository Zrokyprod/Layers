from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext
from app.db.models import Agent
from app.services.action_receipts import (
    action_receipt_payload,
    verify_action_receipt_signature,
)
from app.services.action_runner import (
    action_runner_capability_manifest,
    action_runner_credential_scope,
    action_runner_heartbeat_payload,
    action_runner_supported_operation_kinds,
    execution_attempt_plan,
    execution_attempt_result_summary,
)
from app.services.action_timeline import action_timeline_event_payload
from app.services.protected_action_billing import (
    ProtectedActionMeteringUnavailable,
    ProtectedActionQuotaExceeded,
    quota_error_detail,
)
from app.api.routes._action_intents_schemas import *  # noqa: F403


def _require_role(context: TenantContext, minimum: str) -> None:
    if ROLE_RANK[context.role] < ROLE_RANK[minimum]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant role '{context.role}' does not allow this action.",
        )


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _contract_response(row) -> ActionContractResponse:
    return ActionContractResponse(
        id=row.id,
        project_id=row.project_id,
        contract_key=row.contract_key,
        version=row.version,
        contract_version=f"{row.contract_key}/{row.version}",
        action_type=row.action_type,
        operation_kind=row.operation_kind,
        domain_family=row.domain_family,
        schema_digest=row.schema_digest,
        schema=_loads(row.schema_json, {}),
        risk_class=row.risk_class,
        verification_profile=_loads(row.verification_profile_json, {}),
        connector_family=row.connector_family,
        status=row.status,
        created_at=row.created_at,
    )


def _intent_agent_profile_response(db: Session, row) -> ActionIntentAgentProfileResponse | None:
    if not row.agent_id:
        return None
    agent = db.get(Agent, row.agent_id)
    if agent is None or agent.project_id != row.project_id:
        return None
    return ActionIntentAgentProfileResponse(
        id=agent.id,
        display_name=agent.name,
        slug=agent.slug,
        runtime_path=agent.runtime_path,
        environment=agent.environment,
    )


def _intent_response(db: Session, row) -> ActionIntentResponse:
    return ActionIntentResponse(
        action_id=row.id,
        project_id=row.project_id,
        agent_id=row.agent_id,
        agent_profile=_intent_agent_profile_response(db, row),
        contract_version=f"{row.contract_key}/{row.contract_version}",
        action_type=row.action_type,
        operation_kind=row.operation_kind,
        environment=row.environment,
        status=row.status,
        proof_status=row.proof_status,
        receipt_status=row.receipt_status,
        idempotency_key=row.idempotency_key,
        intent_digest=row.intent_digest,
        canonical_intent=_loads(row.canonical_intent_json, {}),
        created_at=row.created_at,
        decided_at=row.decided_at,
        authorized_at=row.authorized_at,
        runtime_policy_decision_id=row.runtime_policy_decision_id,
        deadline=row.deadline_at,
        status_url=f"/v1/action-intents/{row.id}",
    )


def _runner_response(row) -> ActionRunnerResponse:
    return ActionRunnerResponse(
        runner_id=row.id,
        project_id=row.project_id,
        name=row.name,
        runner_type=row.runner_type,
        environment=row.environment,
        status=row.status,
        supported_operation_kinds=action_runner_supported_operation_kinds(row),
        credential_scope=action_runner_credential_scope(row),
        capability_manifest=action_runner_capability_manifest(row),
        heartbeat_payload=action_runner_heartbeat_payload(row),
        capability_version=row.capability_version,
        last_heartbeat_at=row.last_heartbeat_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _execution_attempt_response(row) -> ActionExecutionAttemptResponse:
    return ActionExecutionAttemptResponse(
        attempt_id=row.id,
        project_id=row.project_id,
        action_id=row.action_intent_id,
        runner_id=row.runner_id,
        attempt_number=row.attempt_number,
        status=row.status,
        idempotency_key=row.idempotency_key,
        credential_ref=row.credential_ref,
        plan_digest=row.plan_digest,
        execution_plan=execution_attempt_plan(row),
        result_summary=execution_attempt_result_summary(row),
        error_message=row.error_message,
        protected_credential_returned=row.protected_credential_returned,
        requested_by_subject=row.requested_by_subject,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _timeline_event_response(row) -> ActionTimelineEventResponse:
    return ActionTimelineEventResponse(
        event_id=row.id,
        action_id=row.action_intent_id,
        project_id=row.project_id,
        event_type=row.event_type,
        event_digest=row.event_digest,
        actor=row.actor,
        payload=action_timeline_event_payload(row),
        created_at=row.created_at,
    )


def _receipt_response(row) -> ActionReceiptResponse:
    return ActionReceiptResponse(
        receipt_id=row.id,
        project_id=row.project_id,
        action_id=row.action_intent_id,
        receipt_digest=row.receipt_digest,
        evidence_hash=row.evidence_hash,
        signature_algorithm=row.signature_algorithm,
        signature=row.signature,
        signing_key_id=row.signing_key_id,
        signature_valid=verify_action_receipt_signature(row),
        signed_payload=row.receipt_json,
        generated_at=row.generated_at,
        receipt=action_receipt_payload(row),
    )


def _pack_response(payload: dict[str, Any]) -> ActionPackResponse:
    return ActionPackResponse(**payload)


def _raise_billing_error(exc: ProtectedActionQuotaExceeded | ProtectedActionMeteringUnavailable) -> None:
    if isinstance(exc, ProtectedActionQuotaExceeded):
        detail = quota_error_detail(exc)
        headers = {}
        if detail.get("current_plan"):
            headers["X-Zroky-Plan-Hint"] = str(detail["current_plan"])
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail,
            headers=headers,
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(exc),
    ) from exc


def _validate_optional_filter(name: str, value: str | None, allowed: set[str]) -> None:
    if value is not None and value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {name} filter.",
        )


def _parse_status_filter(name: str, value: str | None, allowed: set[str]) -> list[str] | None:
    if value is None:
        return None
    parsed = [item.strip() for item in value.split(",") if item.strip()]
    if not parsed:
        return None
    if any(item not in allowed for item in parsed):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {name} filter.",
        )
    return parsed


__all__ = [name for name in globals() if not name.startswith("__")]
