from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.db.models import RuntimePolicyDecision
from app.db.session import get_db_session
from app.services.evidence_pack import build_runtime_policy_evidence_pack
from app.services.notification_dispatch import dispatch_runtime_policy_approval_slack_request
from app.services.pilot import PolicyValidationError, get_or_create_policy, parse_policy_json, upsert_policy
from app.services.runtime_policy import (
    RuntimePolicyApprovalConflict,
    evaluate_runtime_policy,
    list_runtime_policy_audit_events,
    list_runtime_policy_decisions,
    resolve_runtime_policy_decision,
)
from app.services.runtime_policy_rules import (
    RuntimePolicyRuleNotFound,
    RuntimePolicyRuleValidationError,
    create_runtime_policy_rule,
    disable_runtime_policy_rule,
    list_runtime_policy_rules,
    resolve_runtime_policy,
    runtime_policy_rule_to_dict,
    update_runtime_policy_rule,
)


router = APIRouter(prefix="/v1/runtime-policy")
logger = logging.getLogger(__name__)

VALID_DECISION_STATUSES = {
    "allowed",
    "blocked",
    "pending_approval",
    "approved",
    "rejected",
    "expired",
}


class RuntimePolicyCheckRequest(BaseModel):
    trace_id: str | None = Field(default=None, max_length=128)
    span_id: str | None = Field(default=None, max_length=128)
    call_id: str | None = Field(default=None, max_length=64)
    agent_id: str | None = Field(default=None, max_length=36)
    agent_name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=64)
    action_type: str | None = Field(default=None, max_length=64)
    tool_name: str | None = Field(default=None, max_length=255)
    tool_args: dict[str, Any] | list[Any] | str | None = None
    tool_call_count: int | None = Field(default=None, ge=0)
    retry_count: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    input_text: str | None = None
    user_input: str | None = None
    output_text: str | None = None
    external_action: bool | None = None
    prompt_injection_detected: bool | None = None
    pii_detected: bool | None = None
    approval_id: str | None = Field(default=None, max_length=36)
    user_id: str | None = Field(default=None, max_length=255)
    workflow_name: str | None = Field(default=None, max_length=255)
    environment: str | None = Field(default=None, max_length=64)
    business_impact: dict[str, Any] | str | None = None
    business_impact_summary: str | None = None
    impact_usd: float | None = Field(default=None, ge=0)
    customer_id: str | None = None
    account_id: str | None = None
    order_id: str | None = None
    resource_id: str | None = None
    metadata: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class RuntimePolicyAuditEventResponse(BaseModel):
    id: str
    event_type: str
    actor: str | None
    reason: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime


class RuntimePolicyDecisionResponse(BaseModel):
    id: str
    project_id: str
    trace_id: str | None
    call_id: str | None
    agent_name: str | None
    role: str | None
    action_type: str | None
    tool_name: str | None
    decision: str
    status: str
    allowed: bool
    requires_approval: bool
    reasons: list[str]
    request: dict[str, Any]
    policy_snapshot: dict[str, Any]
    intended_action: dict[str, Any]
    trace_context: dict[str, Any]
    policy_hit: dict[str, Any]
    business_impact: dict[str, Any]
    audit_log: list[RuntimePolicyAuditEventResponse]
    created_at: datetime
    expires_at: datetime | None
    resolved_at: datetime | None
    resolved_by: str | None
    resolution_reason: str | None
    consumed_at: datetime | None
    consumed_by_decision_id: str | None
    required_approval_count: int
    approval_count: int
    approver_subjects: list[str]


class RuntimePolicyListResponse(BaseModel):
    items: list[RuntimePolicyDecisionResponse]
    total_in_page: int


class RuntimePolicyCheckResponse(RuntimePolicyDecisionResponse):
    approval_queue_item: RuntimePolicyDecisionResponse | None = None


class RuntimePolicyDryRunResponse(BaseModel):
    recorded: bool = False
    decision: str
    status: str
    allowed: bool
    requires_approval: bool
    reasons: list[str]
    request: dict[str, Any]
    policy_hit: dict[str, Any]
    business_impact: dict[str, Any]
    intended_action: dict[str, Any]
    required_approval_count: int


class RuntimePolicyResolveRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class RuntimePolicyKillSwitchRequest(BaseModel):
    enabled: bool


class RuntimePolicyKillSwitchResponse(BaseModel):
    project_id: str
    enabled: bool
    policy: dict[str, Any]


class RuntimePolicyRuleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    agent_id: str | None = Field(default=None, max_length=36)
    action_type: str | None = Field(default=None, max_length=64)
    environment: str | None = Field(default=None, max_length=64)
    policy_patch: dict[str, Any]
    priority: int = 0
    is_enabled: bool = True


class RuntimePolicyRuleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    agent_id: str | None = Field(default=None, max_length=36)
    action_type: str | None = Field(default=None, max_length=64)
    environment: str | None = Field(default=None, max_length=64)
    policy_patch: dict[str, Any] | None = None
    priority: int | None = None
    is_enabled: bool | None = None


class RuntimePolicyRuleResponse(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    agent_id: str | None
    action_type: str | None
    environment: str | None
    policy_patch: dict[str, Any]
    priority: int
    version: int
    is_enabled: bool
    created_by_subject: str | None
    updated_by_subject: str | None
    created_at: datetime
    updated_at: datetime


class RuntimePolicyRuleListResponse(BaseModel):
    items: list[RuntimePolicyRuleResponse]
    total_in_page: int


class RuntimePolicyResolvePreviewRequest(BaseModel):
    agent_id: str | None = Field(default=None, max_length=36)
    action_type: str | None = Field(default=None, max_length=64)
    tool_name: str | None = Field(default=None, max_length=255)
    environment: str | None = Field(default=None, max_length=64)


class RuntimePolicyResolvePreviewResponse(BaseModel):
    project_id: str
    policy: dict[str, Any]
    matched_rules: list[dict[str, Any]]


class RuntimePolicyEvidencePackResponse(BaseModel):
    schema_version: str
    project_id: str
    decision_id: str
    verification_status: str
    decision: dict[str, Any]
    related_decisions: list[dict[str, Any]]
    audit_log: list[dict[str, Any]]
    trace_policy_spans: list[dict[str, Any]]
    outcome_reconciliation: list[dict[str, Any]]
    call: dict[str, Any] | None
    generated_at: str
    hash_algorithm: str
    evidence_hash: str
    hash_payload_excludes: list[str]


def _require_role(context: TenantContext, minimum: str) -> None:
    if ROLE_RANK[context.role] < ROLE_RANK[minimum]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant role '{context.role}' does not allow this action.",
        )


def _parse_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _audit_to_response(event) -> RuntimePolicyAuditEventResponse:
    return RuntimePolicyAuditEventResponse(
        id=event.id,
        event_type=event.event_type,
        actor=event.actor,
        reason=event.reason,
        before=_parse_json(event.before_json, None),
        after=_parse_json(event.after_json, None),
        created_at=event.created_at,
    )


def _decision_to_response(
    row: RuntimePolicyDecision,
    *,
    audit_events: list[Any] | None = None,
) -> RuntimePolicyDecisionResponse:
    return RuntimePolicyDecisionResponse(
        id=row.id,
        project_id=row.project_id,
        trace_id=row.trace_id,
        call_id=row.call_id,
        agent_name=row.agent_name,
        role=row.role,
        action_type=row.action_type,
        tool_name=row.tool_name,
        decision=row.decision,
        status=row.status,
        allowed=row.status == "allowed" or row.status == "approved",
        requires_approval=row.status == "pending_approval",
        reasons=_parse_json(row.reasons_json, []),
        request=_parse_json(row.request_json, {}),
        policy_snapshot=_parse_json(row.policy_snapshot_json, {}),
        intended_action=_parse_json(row.intended_action_json, {}),
        trace_context=_parse_json(row.trace_context_json, {}),
        policy_hit=_parse_json(row.policy_hit_json, {}),
        business_impact=_parse_json(row.business_impact_json, {}),
        audit_log=[_audit_to_response(event) for event in (audit_events or [])],
        created_at=row.created_at,
        expires_at=row.expires_at,
        resolved_at=row.resolved_at,
        resolved_by=row.resolved_by,
        resolution_reason=row.resolution_reason,
        consumed_at=row.consumed_at,
        consumed_by_decision_id=row.consumed_by_decision_id,
        required_approval_count=row.required_approval_count or 0,
        approval_count=row.approval_count or 0,
        approver_subjects=_parse_json(row.approver_subjects_json, []),
    )


def _rule_to_response(row) -> RuntimePolicyRuleResponse:
    return RuntimePolicyRuleResponse(**runtime_policy_rule_to_dict(row))


@router.post("/check", response_model=RuntimePolicyCheckResponse)
def check_runtime_policy(
    body: RuntimePolicyCheckRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RuntimePolicyCheckResponse:
    _require_role(context, "member")
    result = evaluate_runtime_policy(
        db,
        project_id=context.tenant_id,
        payload=body.model_dump(exclude_none=True),
    )
    audit = list_runtime_policy_audit_events(
        db,
        project_id=context.tenant_id,
        decision_ids=[result.decision.id],
    )
    response = RuntimePolicyCheckResponse(
        **_decision_to_response(
            result.decision,
            audit_events=audit.get(result.decision.id, []),
        ).model_dump()
    )
    if result.requires_approval:
        response.approval_queue_item = _decision_to_response(
            result.decision,
            audit_events=audit.get(result.decision.id, []),
        )
        try:
            dispatch_runtime_policy_approval_slack_request(
                db,
                tenant_id=context.tenant_id,
                decision=result.decision,
            )
        except Exception:
            logger.debug("runtime_policy.slack_approval_dispatch_failed", exc_info=True)
    return response


@router.post("/dry-run", response_model=RuntimePolicyDryRunResponse)
def dry_run_runtime_policy(
    body: RuntimePolicyCheckRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RuntimePolicyDryRunResponse:
    _require_role(context, "member")
    result = evaluate_runtime_policy(
        db,
        project_id=context.tenant_id,
        payload=body.model_dump(exclude_none=True),
        persist=False,
    )
    row = result.decision
    return RuntimePolicyDryRunResponse(
        recorded=False,
        decision=row.decision,
        status=row.status,
        allowed=result.allowed,
        requires_approval=result.requires_approval,
        reasons=result.reasons,
        request=_parse_json(row.request_json, {}),
        policy_hit=_parse_json(row.policy_hit_json, {}),
        business_impact=_parse_json(row.business_impact_json, {}),
        intended_action=_parse_json(row.intended_action_json, {}),
        required_approval_count=row.required_approval_count or 0,
    )


@router.post("/resolve-preview", response_model=RuntimePolicyResolvePreviewResponse)
def resolve_runtime_policy_preview(
    body: RuntimePolicyResolvePreviewRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RuntimePolicyResolvePreviewResponse:
    _require_role(context, "viewer")
    resolved = resolve_runtime_policy(
        db,
        project_id=context.tenant_id,
        payload=body.model_dump(exclude_none=True),
    )
    return RuntimePolicyResolvePreviewResponse(
        project_id=context.tenant_id,
        policy=resolved.policy,
        matched_rules=resolved.matched_rules,
    )


@router.get("/rules", response_model=RuntimePolicyRuleListResponse)
def list_rules(
    enabled: bool | None = Query(default=None),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RuntimePolicyRuleListResponse:
    _require_role(context, "viewer")
    rows = list_runtime_policy_rules(
        db,
        project_id=context.tenant_id,
        enabled=enabled,
    )
    return RuntimePolicyRuleListResponse(
        items=[_rule_to_response(row) for row in rows],
        total_in_page=len(rows),
    )


@router.post("/rules", response_model=RuntimePolicyRuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(
    body: RuntimePolicyRuleCreateRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RuntimePolicyRuleResponse:
    _require_role(context, "admin")
    try:
        row = create_runtime_policy_rule(
            db,
            project_id=context.tenant_id,
            name=body.name,
            description=body.description,
            agent_id=body.agent_id,
            action_type=body.action_type,
            environment=body.environment,
            policy_patch=body.policy_patch,
            priority=body.priority,
            is_enabled=body.is_enabled,
            actor=context.subject,
        )
    except RuntimePolicyRuleValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return _rule_to_response(row)


@router.patch("/rules/{rule_id}", response_model=RuntimePolicyRuleResponse)
def update_rule(
    rule_id: str,
    body: RuntimePolicyRuleUpdateRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RuntimePolicyRuleResponse:
    _require_role(context, "admin")
    update_fields = body.model_dump(exclude_unset=True)
    for clearable in ("agent_id", "action_type", "environment", "description"):
        if clearable in body.model_fields_set and update_fields.get(clearable) is None:
            update_fields[clearable] = ""
    try:
        row = update_runtime_policy_rule(
            db,
            project_id=context.tenant_id,
            rule_id=rule_id,
            actor=context.subject,
            **update_fields,
        )
    except RuntimePolicyRuleNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RuntimePolicyRuleValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return _rule_to_response(row)


@router.delete("/rules/{rule_id}", response_model=RuntimePolicyRuleResponse)
def disable_rule(
    rule_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RuntimePolicyRuleResponse:
    _require_role(context, "admin")
    try:
        row = disable_runtime_policy_rule(
            db,
            project_id=context.tenant_id,
            rule_id=rule_id,
            actor=context.subject,
        )
    except RuntimePolicyRuleNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return _rule_to_response(row)


@router.get("/approvals", response_model=RuntimePolicyListResponse)
def list_approvals(
    status_filter: str | None = Query(default="pending_approval", alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RuntimePolicyListResponse:
    _require_role(context, "viewer")
    effective_status = None if status_filter == "all" else status_filter
    if effective_status is not None and effective_status not in VALID_DECISION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of: all, {', '.join(sorted(VALID_DECISION_STATUSES))}",
        )
    rows = list_runtime_policy_decisions(
        db,
        project_id=context.tenant_id,
        status=effective_status,
        limit=limit,
    )
    audit = list_runtime_policy_audit_events(
        db,
        project_id=context.tenant_id,
        decision_ids=[row.id for row in rows],
    )
    return RuntimePolicyListResponse(
        items=[_decision_to_response(row, audit_events=audit.get(row.id, [])) for row in rows],
        total_in_page=len(rows),
    )


@router.get("/decisions/{decision_id}/evidence", response_model=RuntimePolicyEvidencePackResponse)
def get_runtime_policy_decision_evidence(
    decision_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RuntimePolicyEvidencePackResponse:
    _require_role(context, "viewer")
    pack = build_runtime_policy_evidence_pack(
        db,
        project_id=context.tenant_id,
        decision_id=decision_id,
    )
    if pack is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Runtime policy decision evidence was not found.",
        )
    return RuntimePolicyEvidencePackResponse(**pack)


@router.post("/approvals/{decision_id}/approve", response_model=RuntimePolicyDecisionResponse)
def approve_runtime_policy_decision(
    decision_id: str,
    body: RuntimePolicyResolveRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RuntimePolicyDecisionResponse:
    _require_role(context, "admin")
    try:
        row = resolve_runtime_policy_decision(
            db,
            project_id=context.tenant_id,
            decision_id=decision_id,
            approved=True,
            actor=context.subject,
            reason=body.reason,
        )
    except RuntimePolicyApprovalConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending runtime policy approval was not found.",
        )
    audit = list_runtime_policy_audit_events(
        db,
        project_id=context.tenant_id,
        decision_ids=[row.id],
    )
    return _decision_to_response(row, audit_events=audit.get(row.id, []))


@router.post("/approvals/{decision_id}/reject", response_model=RuntimePolicyDecisionResponse)
def reject_runtime_policy_decision(
    decision_id: str,
    body: RuntimePolicyResolveRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RuntimePolicyDecisionResponse:
    _require_role(context, "admin")
    row = resolve_runtime_policy_decision(
        db,
        project_id=context.tenant_id,
        decision_id=decision_id,
        approved=False,
        actor=context.subject,
        reason=body.reason,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending runtime policy approval was not found.",
        )
    audit = list_runtime_policy_audit_events(
        db,
        project_id=context.tenant_id,
        decision_ids=[row.id],
    )
    return _decision_to_response(row, audit_events=audit.get(row.id, []))


@router.post("/kill-switch", response_model=RuntimePolicyKillSwitchResponse)
def set_runtime_kill_switch(
    body: RuntimePolicyKillSwitchRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RuntimePolicyKillSwitchResponse:
    _require_role(context, "admin")
    policy_row = get_or_create_policy(db, project_id=context.tenant_id)
    policy = parse_policy_json(policy_row.policy_json)
    policy["kill_switch"] = body.enabled
    try:
        updated = upsert_policy(
            db,
            project_id=context.tenant_id,
            payload=policy,
            updated_by=context.subject,
        )
    except PolicyValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    parsed = parse_policy_json(updated.policy_json)
    return RuntimePolicyKillSwitchResponse(
        project_id=context.tenant_id,
        enabled=bool(parsed.get("kill_switch")),
        policy=parsed,
    )
