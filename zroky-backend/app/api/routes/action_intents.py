from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

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
    list_action_intents,
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
    generate_action_receipt,
    get_action_receipt,
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
    claim_next_execution_attempt,
    create_execution_attempt,
    dispatch_execution_attempt,
    finish_execution_attempt,
    list_action_runners,
    list_execution_adapter_contracts,
    list_execution_attempts,
    list_project_execution_attempts,
    record_runner_heartbeat,
    register_action_runner,
    start_execution_attempt,
)
from app.services.action_timeline import list_action_timeline
from app.services.protected_action_billing import (
    ProtectedActionMeteringUnavailable,
    ProtectedActionQuotaExceeded,
)
from app.services.notification_dispatch import dispatch_runtime_policy_approval_slack_request
from app.api.routes._action_intents_helpers import *  # noqa: F403
from app.api.routes._action_intents_schemas import *  # noqa: F403


router = APIRouter()
logger = logging.getLogger(__name__)

ACTION_INTENT_STATUSES = {"validated", "deciding", "denied", "approval_pending", "authorized", "expired"}
ACTION_INTENT_PROOF_STATUSES = {"not_started", "pending", "matched", "mismatched", "not_verified"}
ACTION_INTENT_RECEIPT_STATUSES = {"missing", "pending", "generated", "failed"}
ACTION_EXECUTION_ATTEMPT_STATUSES = {
    "planned",
    "dispatched",
    "running",
    "succeeded",
    "failed",
    "ambiguous",
    "cancelled",
}


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
            agent_id=body.agent_id,
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
            execution_request=body.execution_request,
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
    return _intent_response(db, result.row)


@router.get("/v1/action-intents", response_model=ActionIntentListResponse)
@limiter.limit("240/minute")
def list_intents(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    proof_status: str | None = Query(default=None),
    receipt_status: str | None = Query(default=None),
    agent_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionIntentListResponse:
    _require_role(context, "viewer")
    _validate_optional_filter("status", status_filter, ACTION_INTENT_STATUSES)
    _validate_optional_filter("proof_status", proof_status, ACTION_INTENT_PROOF_STATUSES)
    _validate_optional_filter("receipt_status", receipt_status, ACTION_INTENT_RECEIPT_STATUSES)
    rows = list_action_intents(
        db,
        project_id=context.tenant_id,
        agent_id=agent_id,
        status=status_filter,
        proof_status=proof_status,
        receipt_status=receipt_status,
        limit=limit,
        offset=offset,
    )
    return ActionIntentListResponse(
        items=[_intent_response(db, row) for row in rows],
        total_in_page=len(rows),
        limit=limit,
        offset=offset,
    )


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
    return _intent_response(db, row)


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


@router.get("/v1/action-execution-attempts", response_model=ActionExecutionAttemptListResponse)
@limiter.limit("240/minute")
def list_project_execution_attempts_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    stale: bool = Query(default=False),
    stale_after_seconds: int = Query(default=600, ge=1, le=86_400),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionExecutionAttemptListResponse:
    _require_role(context, "viewer")
    statuses = _parse_status_filter("status", status_filter, ACTION_EXECUTION_ATTEMPT_STATUSES)
    rows = list_project_execution_attempts(
        db,
        project_id=context.tenant_id,
        statuses=statuses,
        stale=stale,
        stale_after_seconds=stale_after_seconds,
        limit=limit,
        offset=offset,
    )
    return ActionExecutionAttemptListResponse(items=[_execution_attempt_response(row) for row in rows])


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
        **_intent_response(db, result.row).model_dump(),
        allowed=result.allowed,
        requires_approval=result.requires_approval,
        reasons=result.reasons,
    )
