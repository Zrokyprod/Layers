from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.db.models import RuntimePolicyDecision
from app.db.session import get_db_session
from app.services.pilot import PolicyValidationError, get_or_create_policy, parse_policy_json, upsert_policy
from app.services.runtime_policy import (
    evaluate_runtime_policy,
    list_runtime_policy_audit_events,
    list_runtime_policy_decisions,
    resolve_runtime_policy_decision,
)


router = APIRouter(prefix="/v1/runtime-policy")

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


class RuntimePolicyListResponse(BaseModel):
    items: list[RuntimePolicyDecisionResponse]
    total_in_page: int


class RuntimePolicyCheckResponse(RuntimePolicyDecisionResponse):
    approval_queue_item: RuntimePolicyDecisionResponse | None = None


class RuntimePolicyResolveRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class RuntimePolicyKillSwitchRequest(BaseModel):
    enabled: bool


class RuntimePolicyKillSwitchResponse(BaseModel):
    project_id: str
    enabled: bool
    policy: dict[str, Any]


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
    )


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
    return response


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


@router.post("/approvals/{decision_id}/approve", response_model=RuntimePolicyDecisionResponse)
def approve_runtime_policy_decision(
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
        approved=True,
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
