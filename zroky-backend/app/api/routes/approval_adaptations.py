"""Owner controls for evidence-backed approval adaptation."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import get_settings
from app.db.session import get_db_session
from app.services.approval_adaptations import (
    ApprovalAdaptationCandidate,
    ApprovalAdaptationNotEligible,
    ApprovalAdaptationNotFound,
    activate_recommendation,
    list_recommendations,
    list_rules,
    revoke_rule,
)


router = APIRouter(prefix="/v1/approval-adaptations")


class ApprovalAdaptationRecommendationResponse(BaseModel):
    scope_hash: str
    agent_id: str | None
    action_type: str
    operation_kind: str
    contract_key: str
    environment: str
    approved_count: int
    matched_count: int
    mismatched_count: int
    unresolved_count: int


class ApprovalAdaptationRecommendationsResponse(BaseModel):
    minimum_matched_approvals: int
    enforcement_enabled: bool
    items: list[ApprovalAdaptationRecommendationResponse]


class ApprovalAdaptationActivateRequest(BaseModel):
    duration_days: int = Field(default=30, ge=1, le=365)


class ApprovalAdaptationRevokeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class ApprovalAdaptationRuleResponse(BaseModel):
    id: str
    scope_hash: str
    agent_id: str | None
    action_type: str
    operation_kind: str
    contract_key: str
    environment: str
    evidence_approved_count: int
    evidence_matched_count: int
    status: str
    activated_by_subject: str | None
    revoked_by_subject: str | None
    revocation_reason: str | None
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    enforcement_enabled: bool


class ApprovalAdaptationRulesResponse(BaseModel):
    items: list[ApprovalAdaptationRuleResponse]


def _require_owner(context: TenantContext) -> None:
    if ROLE_RANK[context.role] < ROLE_RANK["owner"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant owner role is required for approval adaptation.",
        )


def _recommendation_response(candidate: ApprovalAdaptationCandidate) -> ApprovalAdaptationRecommendationResponse:
    return ApprovalAdaptationRecommendationResponse(
        scope_hash=candidate.scope_hash,
        agent_id=candidate.agent_id,
        action_type=candidate.action_type,
        operation_kind=candidate.operation_kind,
        contract_key=candidate.contract_key,
        environment=candidate.environment,
        approved_count=candidate.approved_count,
        matched_count=candidate.matched_count,
        mismatched_count=candidate.mismatched_count,
        unresolved_count=candidate.unresolved_count,
    )


def _rule_response(row) -> ApprovalAdaptationRuleResponse:
    settings = get_settings()
    effective_status = row.status
    now = datetime.now(timezone.utc)
    if row.status == "active" and row.expires_at <= now:
        effective_status = "expired"
    return ApprovalAdaptationRuleResponse(
        id=row.id,
        scope_hash=row.scope_hash,
        agent_id=row.agent_id,
        action_type=row.action_type,
        operation_kind=row.operation_kind,
        contract_key=row.contract_key,
        environment=row.environment,
        evidence_approved_count=row.evidence_approved_count,
        evidence_matched_count=row.evidence_matched_count,
        status=effective_status,
        activated_by_subject=row.activated_by_subject,
        revoked_by_subject=row.revoked_by_subject,
        revocation_reason=row.revocation_reason,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
        enforcement_enabled=settings.APPROVAL_ADAPTATION_ENABLED,
    )


@router.get("/recommendations", response_model=ApprovalAdaptationRecommendationsResponse)
def get_recommendations(
    limit: int = Query(default=50, ge=1, le=100),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ApprovalAdaptationRecommendationsResponse:
    _require_owner(context)
    settings = get_settings()
    candidates = list_recommendations(
        db,
        project_id=context.tenant_id,
        minimum_matched_approvals=settings.APPROVAL_ADAPTATION_MIN_MATCHED_APPROVALS,
    )
    return ApprovalAdaptationRecommendationsResponse(
        minimum_matched_approvals=settings.APPROVAL_ADAPTATION_MIN_MATCHED_APPROVALS,
        enforcement_enabled=settings.APPROVAL_ADAPTATION_ENABLED,
        items=[_recommendation_response(candidate) for candidate in candidates[:limit]],
    )


@router.post(
    "/recommendations/{scope_hash}/activate",
    response_model=ApprovalAdaptationRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def activate_recommendation_rule(
    scope_hash: str,
    body: ApprovalAdaptationActivateRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ApprovalAdaptationRuleResponse:
    _require_owner(context)
    settings = get_settings()
    if body.duration_days > settings.APPROVAL_ADAPTATION_MAX_DURATION_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "duration_days exceeds APPROVAL_ADAPTATION_MAX_DURATION_DAYS "
                f"({settings.APPROVAL_ADAPTATION_MAX_DURATION_DAYS})."
            ),
        )
    try:
        row = activate_recommendation(
            db,
            project_id=context.tenant_id,
            scope_hash=scope_hash,
            minimum_matched_approvals=settings.APPROVAL_ADAPTATION_MIN_MATCHED_APPROVALS,
            duration_days=body.duration_days,
            actor=context.subject,
        )
    except ApprovalAdaptationNotEligible as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _rule_response(row)


@router.get("/rules", response_model=ApprovalAdaptationRulesResponse)
def get_rules(
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ApprovalAdaptationRulesResponse:
    _require_owner(context)
    return ApprovalAdaptationRulesResponse(
        items=[_rule_response(row) for row in list_rules(db, project_id=context.tenant_id)]
    )


@router.post("/rules/{rule_id}/revoke", response_model=ApprovalAdaptationRuleResponse)
def revoke_adaptation_rule(
    rule_id: str,
    body: ApprovalAdaptationRevokeRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ApprovalAdaptationRuleResponse:
    _require_owner(context)
    try:
        row = revoke_rule(
            db,
            project_id=context.tenant_id,
            rule_id=rule_id,
            actor=context.subject,
            reason=body.reason,
        )
    except ApprovalAdaptationNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _rule_response(row)
