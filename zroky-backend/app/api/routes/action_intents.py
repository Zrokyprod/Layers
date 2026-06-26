from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.services.action_kernel import (
    ActionContractConflict,
    ActionContractNotFound,
    ActionIntentConflict,
    ActionIntentNotFound,
    ActionKernelError,
    create_action_intent,
    decide_action_intent,
    get_action_intent,
    register_action_contract,
)
from app.services.action_packs import (
    ActionPackNotFound,
    action_pack_to_dict,
    get_action_pack,
    install_action_pack,
    list_action_packs,
)
from app.services.action_receipts import (
    ActionReceiptNotFound,
    ActionReceiptSigningError,
    action_receipt_payload,
    generate_action_receipt,
    get_action_receipt,
    verify_action_receipt_signature,
)
from app.services.action_runner import (
    ActionCredentialReferenceError,
    ActionExecutionAttemptConflict,
    ActionExecutionAttemptNotFound,
    ActionExecutionPlanError,
    ActionExecutionStateError,
    ActionExecutionNotAuthorized,
    ActionRunnerConflict,
    ActionRunnerError,
    ActionRunnerNotFound,
    action_runner_credential_scope,
    action_runner_heartbeat_payload,
    action_runner_supported_operation_kinds,
    claim_next_execution_attempt,
    create_execution_attempt,
    dispatch_execution_attempt,
    execution_attempt_plan,
    execution_attempt_result_summary,
    finish_execution_attempt,
    list_action_runners,
    list_execution_adapter_contracts,
    list_execution_attempts,
    record_runner_heartbeat,
    register_action_runner,
    start_execution_attempt,
)
from app.services.action_timeline import action_timeline_event_payload, list_action_timeline
from app.services.protected_action_billing import (
    ProtectedActionMeteringUnavailable,
    ProtectedActionQuotaExceeded,
    quota_error_detail,
)
from app.services.notification_dispatch import dispatch_runtime_policy_approval_slack_request


router = APIRouter()
logger = logging.getLogger(__name__)


class ActionContractRegisterRequest(BaseModel):
    contract_key: str = Field(min_length=3, max_length=160)
    version: str = Field(min_length=1, max_length=32)
    action_type: str = Field(min_length=3, max_length=160)
    operation_kind: str = Field(min_length=3, max_length=32)
    domain_family: str = Field(min_length=3, max_length=64)
    schema_: dict[str, Any] = Field(alias="schema")
    risk_class: str = Field(default="R2", max_length=8)
    verification_profile: dict[str, Any] | None = None
    connector_family: str | None = Field(default=None, max_length=80)


class ActionContractResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    project_id: str
    contract_key: str
    version: str
    contract_version: str
    action_type: str
    operation_kind: str
    domain_family: str
    schema_digest: str
    schema_: dict[str, Any] = Field(alias="schema")
    risk_class: str
    verification_profile: dict[str, Any]
    connector_family: str | None
    status: str
    created_at: datetime


class ActionIntentCreateRequest(BaseModel):
    contract_version: str = Field(min_length=5, max_length=200)
    action_type: str = Field(min_length=3, max_length=160)
    operation_kind: str = Field(min_length=3, max_length=32)
    environment: str = Field(default="production", max_length=64)
    principal: dict[str, Any] = Field(default_factory=dict)
    actor_chain: list[dict[str, Any]] = Field(default_factory=list)
    purpose: dict[str, Any] = Field(default_factory=dict)
    resource: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    verification_profile: str | None = Field(default=None, max_length=160)
    deadline: datetime | None = None
    trace_context: dict[str, Any] | None = None


class ActionIntentResponse(BaseModel):
    action_id: str
    project_id: str
    contract_version: str
    action_type: str
    operation_kind: str
    environment: str
    status: str
    idempotency_key: str
    intent_digest: str
    canonical_intent: dict[str, Any]
    created_at: datetime
    decided_at: datetime | None
    authorized_at: datetime | None
    runtime_policy_decision_id: str | None
    deadline: datetime | None
    status_url: str


class ActionIntentDecisionRequest(BaseModel):
    approval_id: str | None = Field(default=None, max_length=36)


class ActionIntentDecisionResponse(ActionIntentResponse):
    allowed: bool
    requires_approval: bool
    reasons: list[str] = Field(default_factory=list)


class ActionRunnerRegisterRequest(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    runner_type: str = Field(default="customer_hosted", max_length=32)
    environment: str = Field(default="production", max_length=64)
    supported_operation_kinds: list[str] = Field(default_factory=list)
    credential_scope: dict[str, Any] = Field(default_factory=dict)
    capability_version: str | None = Field(default=None, max_length=64)


class ActionRunnerHeartbeatRequest(BaseModel):
    status: str = Field(default="online", max_length=32)
    heartbeat_payload: dict[str, Any] = Field(default_factory=dict)
    supported_operation_kinds: list[str] | None = None
    capability_version: str | None = Field(default=None, max_length=64)


class ActionRunnerClaimRequest(BaseModel):
    runner_metadata: dict[str, Any] = Field(default_factory=dict)


class ActionRunnerResponse(BaseModel):
    runner_id: str
    project_id: str
    name: str
    runner_type: str
    environment: str
    status: str
    supported_operation_kinds: list[str]
    credential_scope: dict[str, Any]
    heartbeat_payload: dict[str, Any]
    capability_version: str | None
    last_heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActionRunnerListResponse(BaseModel):
    items: list[ActionRunnerResponse]


class ActionExecutionAdapterContractResponse(BaseModel):
    schema_version: str
    adapter: str
    display_name: str
    operation_kinds: list[str]
    operations: list[str]
    required_target_fields: list[str]
    required_argument_fields: list[str]
    required_result_fields: list[str]
    verification_connector: str
    credential_boundary: str
    protected_credential_returned: bool


class ActionExecutionAdapterListResponse(BaseModel):
    items: list[ActionExecutionAdapterContractResponse]


class ActionExecutionAttemptCreateRequest(BaseModel):
    runner_id: str = Field(min_length=36, max_length=36)
    credential_ref: str = Field(min_length=12, max_length=512)
    execution_plan: dict[str, Any] = Field(default_factory=dict)


class ActionExecutionDispatchRequest(BaseModel):
    dispatch_metadata: dict[str, Any] = Field(default_factory=dict)


class ActionExecutionStartRequest(BaseModel):
    runner_metadata: dict[str, Any] = Field(default_factory=dict)


class ActionExecutionFinishRequest(BaseModel):
    final_status: str = Field(max_length=32)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = Field(default=None, max_length=2000)


class ActionExecutionAttemptResponse(BaseModel):
    attempt_id: str
    project_id: str
    action_id: str
    runner_id: str
    attempt_number: int
    status: str
    idempotency_key: str
    credential_ref: str
    plan_digest: str
    execution_plan: dict[str, Any]
    result_summary: dict[str, Any]
    error_message: str | None
    protected_credential_returned: bool
    requested_by_subject: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActionExecutionAttemptListResponse(BaseModel):
    items: list[ActionExecutionAttemptResponse]


class ActionTimelineEventResponse(BaseModel):
    event_id: str
    action_id: str
    project_id: str
    event_type: str
    event_digest: str
    actor: str | None
    payload: dict[str, Any]
    created_at: datetime


class ActionTimelineResponse(BaseModel):
    items: list[ActionTimelineEventResponse]


class ActionReceiptResponse(BaseModel):
    receipt_id: str
    project_id: str
    action_id: str
    receipt_digest: str
    evidence_hash: str | None
    signature_algorithm: str
    signature: str
    signing_key_id: str
    signature_valid: bool
    generated_at: datetime
    receipt: dict[str, Any]


class ActionPackContractTemplateResponse(BaseModel):
    contract_key: str
    version: str
    contract_version: str
    action_type: str
    operation_kind: str
    domain_family: str
    risk_class: str
    connector_family: str
    schema_: dict[str, Any] = Field(alias="schema")
    verification_profile: dict[str, Any]


class ActionPackResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    display_name: str
    summary: str
    primary_runtime_path: str
    recommended_connectors: list[str]
    native_tool_families: list[str]
    dashboard_href: str
    contract_templates: list[ActionPackContractTemplateResponse]


class ActionPackListResponse(BaseModel):
    items: list[ActionPackResponse]


class ActionPackInstallResultResponse(BaseModel):
    contract: ActionContractResponse
    created: bool


class ActionPackInstallResponse(BaseModel):
    pack: ActionPackResponse
    installed_contracts: list[ActionPackInstallResultResponse]


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


def _intent_response(row) -> ActionIntentResponse:
    return ActionIntentResponse(
        action_id=row.id,
        project_id=row.project_id,
        contract_version=f"{row.contract_key}/{row.contract_version}",
        action_type=row.action_type,
        operation_kind=row.operation_kind,
        environment=row.environment,
        status=row.status,
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


@router.get("/v1/action-execution-adapters", response_model=ActionExecutionAdapterListResponse)
@limiter.limit("120/minute")
def list_action_execution_adapters(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
) -> ActionExecutionAdapterListResponse:
    _require_role(context, "viewer")
    return ActionExecutionAdapterListResponse(
        items=[
            ActionExecutionAdapterContractResponse(**item)
            for item in list_execution_adapter_contracts()
        ]
    )


@router.post("/v1/action-runners", response_model=ActionRunnerResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def register_runner(
    request: Request,
    body: ActionRunnerRegisterRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionRunnerResponse:
    _require_role(context, "admin")
    try:
        result = register_action_runner(
            db,
            project_id=context.tenant_id,
            name=body.name,
            runner_type=body.runner_type,
            environment=body.environment,
            supported_operation_kinds=body.supported_operation_kinds,
            credential_scope=body.credential_scope,
            capability_version=body.capability_version,
            registered_by_subject=context.subject,
        )
    except ActionRunnerConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ActionRunnerError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return _runner_response(result.row)


@router.get("/v1/action-runners", response_model=ActionRunnerListResponse)
@limiter.limit("120/minute")
def list_runners(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionRunnerListResponse:
    _require_role(context, "viewer")
    return ActionRunnerListResponse(
        items=[_runner_response(row) for row in list_action_runners(db, project_id=context.tenant_id)]
    )


@router.post("/v1/action-runners/{runner_id}/heartbeat", response_model=ActionRunnerResponse)
@limiter.limit("120/minute")
def runner_heartbeat(
    request: Request,
    runner_id: str,
    body: ActionRunnerHeartbeatRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionRunnerResponse:
    _require_role(context, "member")
    try:
        row = record_runner_heartbeat(
            db,
            project_id=context.tenant_id,
            runner_id=runner_id,
            status=body.status,
            heartbeat_payload=body.heartbeat_payload,
            supported_operation_kinds=body.supported_operation_kinds,
            capability_version=body.capability_version,
        )
    except ActionRunnerNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ActionRunnerError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return _runner_response(row)


@router.post(
    "/v1/action-runners/{runner_id}/execution-attempts/claim",
    response_model=ActionExecutionAttemptResponse,
)
@limiter.limit("120/minute")
def claim_runner_execution_attempt(
    request: Request,
    runner_id: str,
    body: ActionRunnerClaimRequest | None = None,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionExecutionAttemptResponse:
    _require_role(context, "member")
    try:
        row = claim_next_execution_attempt(
            db,
            project_id=context.tenant_id,
            runner_id=runner_id,
            runner_metadata=body.runner_metadata if body else None,
            actor=context.subject,
        )
    except ActionRunnerNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ActionExecutionAttemptNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ActionExecutionStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return _execution_attempt_response(row)


@router.get("/v1/action-packs", response_model=ActionPackListResponse)
@limiter.limit("120/minute")
def list_packs(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
) -> ActionPackListResponse:
    _require_role(context, "viewer")
    return ActionPackListResponse(
        items=[_pack_response(action_pack_to_dict(pack)) for pack in list_action_packs()]
    )


@router.get("/v1/action-packs/{pack_id}", response_model=ActionPackResponse)
@limiter.limit("120/minute")
def get_pack(
    request: Request,
    pack_id: str,
    context: TenantContext = Depends(require_tenant_context),
) -> ActionPackResponse:
    _require_role(context, "viewer")
    try:
        pack = get_action_pack(pack_id)
    except ActionPackNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _pack_response(action_pack_to_dict(pack))


@router.post(
    "/v1/action-packs/{pack_id}/install",
    response_model=ActionPackInstallResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def install_pack(
    request: Request,
    pack_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionPackInstallResponse:
    _require_role(context, "admin")
    try:
        pack, results = install_action_pack(
            db,
            project_id=context.tenant_id,
            pack_id=pack_id,
            created_by_subject=context.subject,
        )
    except ActionPackNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ActionContractConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ActionKernelError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return ActionPackInstallResponse(
        pack=_pack_response(action_pack_to_dict(pack)),
        installed_contracts=[
            ActionPackInstallResultResponse(
                contract=_contract_response(result.row),
                created=result.created,
            )
            for result in results
        ],
    )


@router.post("/v1/action-contracts", response_model=ActionContractResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def register_contract(
    request: Request,
    body: ActionContractRegisterRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionContractResponse:
    _require_role(context, "admin")
    try:
        result = register_action_contract(
            db,
            project_id=context.tenant_id,
            contract_key=body.contract_key,
            version=body.version,
            action_type=body.action_type,
            operation_kind=body.operation_kind,
            domain_family=body.domain_family,
            schema=body.schema_,
            risk_class=body.risk_class,
            verification_profile=body.verification_profile,
            connector_family=body.connector_family,
            created_by_subject=context.subject,
        )
    except ActionContractConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ActionKernelError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return _contract_response(result.row)


@router.post("/v1/action-intents", response_model=ActionIntentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("120/minute")
def create_intent(
    request: Request,
    body: ActionIntentCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionIntentResponse:
    _require_role(context, "member")
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key header is required.")
    try:
        result = create_action_intent(
            db,
            project_id=context.tenant_id,
            contract_version=body.contract_version,
            action_type=body.action_type,
            operation_kind=body.operation_kind,
            environment=body.environment,
            idempotency_key=idempotency_key.strip(),
            principal=body.principal,
            actor_chain=body.actor_chain,
            purpose=body.purpose,
            resource=body.resource,
            parameters=body.parameters,
            verification_profile=body.verification_profile,
            deadline_at=body.deadline,
            trace_context=body.trace_context,
        )
    except ActionContractNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ActionIntentConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        _raise_billing_error(exc)
    except ActionKernelError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return _intent_response(result.row)


@router.get("/v1/action-intents/{action_id}", response_model=ActionIntentResponse)
@limiter.limit("240/minute")
def get_intent(
    request: Request,
    action_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionIntentResponse:
    _require_role(context, "viewer")
    try:
        row = get_action_intent(db, project_id=context.tenant_id, action_id=action_id)
    except ActionIntentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _intent_response(row)


@router.get("/v1/action-intents/{action_id}/timeline", response_model=ActionTimelineResponse)
@limiter.limit("240/minute")
def get_intent_timeline(
    request: Request,
    action_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionTimelineResponse:
    _require_role(context, "viewer")
    try:
        get_action_intent(db, project_id=context.tenant_id, action_id=action_id)
    except ActionIntentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ActionTimelineResponse(
        items=[
            _timeline_event_response(row)
            for row in list_action_timeline(db, project_id=context.tenant_id, action_id=action_id)
        ]
    )


@router.post(
    "/v1/action-intents/{action_id}/receipt",
    response_model=ActionReceiptResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("120/minute")
def generate_intent_receipt(
    request: Request,
    action_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionReceiptResponse:
    _require_role(context, "member")
    try:
        result = generate_action_receipt(
            db,
            project_id=context.tenant_id,
            action_id=action_id,
            actor=context.subject,
        )
    except ActionIntentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ActionReceiptSigningError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        _raise_billing_error(exc)
    db.commit()
    return _receipt_response(result.row)


@router.get("/v1/action-intents/{action_id}/receipt", response_model=ActionReceiptResponse)
@limiter.limit("240/minute")
def get_intent_receipt(
    request: Request,
    action_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionReceiptResponse:
    _require_role(context, "viewer")
    try:
        row = get_action_receipt(db, project_id=context.tenant_id, action_id=action_id)
    except ActionReceiptNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _receipt_response(row)


@router.post(
    "/v1/action-intents/{action_id}/execution-attempts",
    response_model=ActionExecutionAttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("120/minute")
def create_intent_execution_attempt(
    request: Request,
    action_id: str,
    body: ActionExecutionAttemptCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionExecutionAttemptResponse:
    _require_role(context, "member")
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key header is required.")
    try:
        result = create_execution_attempt(
            db,
            project_id=context.tenant_id,
            action_id=action_id,
            runner_id=body.runner_id,
            idempotency_key=idempotency_key.strip(),
            credential_ref=body.credential_ref,
            execution_plan=body.execution_plan,
            requested_by_subject=context.subject,
        )
    except ActionIntentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ActionRunnerNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ActionExecutionAttemptConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ActionExecutionNotAuthorized as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ActionCredentialReferenceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ActionExecutionPlanError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        _raise_billing_error(exc)
    except ActionRunnerError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return _execution_attempt_response(result.row)


@router.get(
    "/v1/action-intents/{action_id}/execution-attempts",
    response_model=ActionExecutionAttemptListResponse,
)
@limiter.limit("240/minute")
def list_intent_execution_attempts(
    request: Request,
    action_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionExecutionAttemptListResponse:
    _require_role(context, "viewer")
    try:
        rows = list_execution_attempts(db, project_id=context.tenant_id, action_id=action_id)
    except ActionIntentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ActionExecutionAttemptListResponse(items=[_execution_attempt_response(row) for row in rows])


@router.post(
    "/v1/action-intents/{action_id}/execution-attempts/{attempt_id}/dispatch",
    response_model=ActionExecutionAttemptResponse,
)
@limiter.limit("120/minute")
def dispatch_intent_execution_attempt(
    request: Request,
    action_id: str,
    attempt_id: str,
    body: ActionExecutionDispatchRequest | None = None,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionExecutionAttemptResponse:
    _require_role(context, "member")
    try:
        row = dispatch_execution_attempt(
            db,
            project_id=context.tenant_id,
            action_id=action_id,
            attempt_id=attempt_id,
            dispatch_metadata=body.dispatch_metadata if body else None,
            actor=context.subject,
        )
    except ActionExecutionAttemptNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ActionExecutionStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return _execution_attempt_response(row)


@router.post(
    "/v1/action-intents/{action_id}/execution-attempts/{attempt_id}/start",
    response_model=ActionExecutionAttemptResponse,
)
@limiter.limit("120/minute")
def start_intent_execution_attempt(
    request: Request,
    action_id: str,
    attempt_id: str,
    body: ActionExecutionStartRequest | None = None,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionExecutionAttemptResponse:
    _require_role(context, "member")
    try:
        row = start_execution_attempt(
            db,
            project_id=context.tenant_id,
            action_id=action_id,
            attempt_id=attempt_id,
            runner_metadata=body.runner_metadata if body else None,
            actor=context.subject,
        )
    except ActionExecutionAttemptNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ActionExecutionStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return _execution_attempt_response(row)


@router.post(
    "/v1/action-intents/{action_id}/execution-attempts/{attempt_id}/finish",
    response_model=ActionExecutionAttemptResponse,
)
@limiter.limit("120/minute")
def finish_intent_execution_attempt(
    request: Request,
    action_id: str,
    attempt_id: str,
    body: ActionExecutionFinishRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionExecutionAttemptResponse:
    _require_role(context, "member")
    try:
        row = finish_execution_attempt(
            db,
            project_id=context.tenant_id,
            action_id=action_id,
            attempt_id=attempt_id,
            final_status=body.final_status,
            result_summary=body.result_summary,
            error_message=body.error_message,
            actor=context.subject,
        )
    except ActionExecutionAttemptNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ActionExecutionStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return _execution_attempt_response(row)


@router.post("/v1/action-intents/{action_id}/decide", response_model=ActionIntentDecisionResponse)
@limiter.limit("120/minute")
def decide_intent(
    request: Request,
    action_id: str,
    body: ActionIntentDecisionRequest | None = None,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionIntentDecisionResponse:
    _require_role(context, "member")
    try:
        result = decide_action_intent(
            db,
            project_id=context.tenant_id,
            action_id=action_id,
            approval_id=body.approval_id if body else None,
            actor=context.subject,
        )
    except ActionIntentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        _raise_billing_error(exc)
    except ActionKernelError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.requires_approval and result.runtime_result is not None:
        try:
            dispatch_runtime_policy_approval_slack_request(
                db,
                tenant_id=context.tenant_id,
                decision=result.runtime_result.decision,
            )
        except Exception:
            logger.debug("action_intents.slack_approval_dispatch_failed", exc_info=True)
    db.commit()
    return ActionIntentDecisionResponse(
        **_intent_response(result.row).model_dump(),
        allowed=result.allowed,
        requires_approval=result.requires_approval,
        reasons=result.reasons,
    )
