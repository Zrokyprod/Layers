from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.api.routes.policy import ApprovalRequirementListResponse, ApprovalRequirementResponse, _approval_binding_digest
from app.core.limiter import limiter
from app.db.models import FinalApprovalRequirement, FinalPolicyDecision, FinalWorkflowIntent
from app.db.session import get_db_session

router = APIRouter(prefix="/v1/approvals")


class ApprovalResolutionRequest(BaseModel):
    binding_digest: str
    reason: str | None = None


def _to_response(row: FinalApprovalRequirement) -> ApprovalRequirementResponse:
    return ApprovalRequirementResponse(
        id=row.id,
        project_id=row.project_id,
        environment=row.environment,
        intent_id=row.intent_id,
        policy_decision_id=row.policy_decision_id,
        required_role=row.required_role,
        binding_digest=row.binding_digest,
        status=row.status,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


def _load_bound_approval(
    db: Session,
    *,
    context: TenantContext,
    approval_id: str,
    binding_digest: str,
) -> tuple[FinalApprovalRequirement, FinalWorkflowIntent, FinalPolicyDecision]:
    row = db.execute(
        select(FinalApprovalRequirement).where(
            FinalApprovalRequirement.id == approval_id,
            FinalApprovalRequirement.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval requirement not found.")
    if row.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval requirement is already resolved.")
    if binding_digest != row.binding_digest:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval binding digest does not match.")
    if ROLE_RANK[context.role] < ROLE_RANK[row.required_role]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Required approver role is missing.")

    intent = db.execute(
        select(FinalWorkflowIntent).where(
            FinalWorkflowIntent.id == row.intent_id,
            FinalWorkflowIntent.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    policy = db.execute(
        select(FinalPolicyDecision).where(
            FinalPolicyDecision.id == row.policy_decision_id,
            FinalPolicyDecision.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if intent is None or policy is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval binding target no longer exists.")
    if _approval_binding_digest(intent.intent_digest, policy.policy_digest) != row.binding_digest:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval binding is stale.")
    return row, intent, policy


@router.get("", response_model=ApprovalRequirementListResponse)
@limiter.limit("120/minute")
def list_approvals(
    request: Request,
    status_filter: Literal["pending", "all"] = Query("pending", alias="status"),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ApprovalRequirementListResponse:
    query = select(FinalApprovalRequirement).where(FinalApprovalRequirement.project_id == context.tenant_id)
    if status_filter == "pending":
        query = query.where(FinalApprovalRequirement.status == "pending")
    rows = db.execute(query.order_by(FinalApprovalRequirement.created_at.desc()).limit(50)).scalars().all()
    return ApprovalRequirementListResponse(items=[_to_response(row) for row in rows])


@router.post("/{approval_id}/approve", response_model=ApprovalRequirementResponse)
@limiter.limit("120/minute")
def approve_approval(
    request: Request,
    approval_id: str,
    body: ApprovalResolutionRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ApprovalRequirementResponse:
    row, intent, policy = _load_bound_approval(db, context=context, approval_id=approval_id, binding_digest=body.binding_digest)
    row.status = "approved"
    row.resolved_at = datetime.now(UTC)
    db.add(row)

    remaining = db.execute(
        select(FinalApprovalRequirement).where(
            FinalApprovalRequirement.project_id == context.tenant_id,
            FinalApprovalRequirement.policy_decision_id == policy.id,
            FinalApprovalRequirement.id != row.id,
            FinalApprovalRequirement.status != "approved",
        )
    ).scalar_one_or_none()
    if remaining is None:
        intent.status = "authorized"
        db.add(intent)
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.post("/{approval_id}/deny", response_model=ApprovalRequirementResponse)
@limiter.limit("120/minute")
def deny_approval(
    request: Request,
    approval_id: str,
    body: ApprovalResolutionRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ApprovalRequirementResponse:
    row, intent, _policy = _load_bound_approval(db, context=context, approval_id=approval_id, binding_digest=body.binding_digest)
    row.status = "denied"
    row.resolved_at = datetime.now(UTC)
    intent.status = "policy_denied"
    db.add_all([row, intent])
    db.commit()
    db.refresh(row)
    return _to_response(row)
