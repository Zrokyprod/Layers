from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import FinalApprovalRequirement, FinalPolicyDecision, FinalWorkflowIntent
from app.db.session import get_db_session


Decision = Literal["allow", "deny", "approval_required", "observe_only"]

router = APIRouter(prefix="/v1/policy")


class PolicyCheckRequest(BaseModel):
    intent_id: str
    decision: Decision | None = None
    reason: str | None = None


class PolicyDecisionResponse(BaseModel):
    id: str
    project_id: str
    environment: str
    intent_id: str
    decision: Decision
    policy_digest: str
    decision_detail: dict[str, Any]
    approval_requirements: list[dict[str, Any]] = Field(default_factory=list)
    decided_at: datetime


class ApprovalRequirementResponse(BaseModel):
    id: str
    project_id: str
    environment: str
    intent_id: str
    policy_decision_id: str
    required_role: str
    binding_digest: str
    status: str
    created_at: datetime
    resolved_at: datetime | None


class ApprovalRequirementListResponse(BaseModel):
    items: list[ApprovalRequirementResponse]


def _digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _approval_binding_digest(intent_digest: str, policy_digest: str) -> str:
    return hashlib.sha256(f"{intent_digest}:{policy_digest}".encode("utf-8")).hexdigest()


def _response(row: FinalPolicyDecision, approvals: list[FinalApprovalRequirement] | None = None) -> PolicyDecisionResponse:
    return PolicyDecisionResponse(
        id=row.id,
        project_id=row.project_id,
        environment=row.environment,
        intent_id=row.intent_id,
        decision=row.decision,  # type: ignore[arg-type]
        policy_digest=row.policy_digest,
        decision_detail=json.loads(row.decision_json),
        approval_requirements=[
            {
                "id": approval.id,
                "required_role": approval.required_role,
                "binding_digest": approval.binding_digest,
                "status": approval.status,
            }
            for approval in (approvals or [])
        ],
        decided_at=row.decided_at,
    )


@router.post("/check", response_model=PolicyDecisionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("120/minute")
def check_policy(
    request: Request,
    body: PolicyCheckRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> PolicyDecisionResponse:
    intent = db.execute(
        select(FinalWorkflowIntent).where(
            FinalWorkflowIntent.id == body.intent_id,
            FinalWorkflowIntent.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if intent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trusted intent not found.")

    decision: Decision = body.decision or "observe_only"
    if body.decision and ROLE_RANK[context.role] < ROLE_RANK["admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role is required to force a policy decision.")

    detail = {
        "decision": decision,
        "reason": body.reason or ("No final policy rules configured; observe-only default." if decision == "observe_only" else "Admin-forced decision."),
        "source": "manual_admin_override" if body.decision else "safe_default",
    }
    row = FinalPolicyDecision(
        project_id=context.tenant_id,
        environment=intent.environment,
        intent_id=intent.id,
        decision=decision,
        policy_digest=_digest(detail),
        decision_json=json.dumps(detail, sort_keys=True, separators=(",", ":")),
    )
    db.add(row)
    db.flush()
    approvals: list[FinalApprovalRequirement] = []
    if decision == "approval_required":
        approval = FinalApprovalRequirement(
            project_id=context.tenant_id,
            environment=intent.environment,
            intent_id=intent.id,
            policy_decision_id=row.id,
            required_role="admin",
            binding_digest=_approval_binding_digest(intent.intent_digest, row.policy_digest),
        )
        db.add(approval)
        approvals.append(approval)
    db.commit()
    db.refresh(row)
    for approval in approvals:
        db.refresh(approval)
    return _response(row, approvals)


@router.get("/approval-requirements", response_model=ApprovalRequirementListResponse)
@limiter.limit("120/minute")
def list_approval_requirements(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ApprovalRequirementListResponse:
    rows = db.execute(
        select(FinalApprovalRequirement)
        .where(FinalApprovalRequirement.project_id == context.tenant_id)
        .order_by(FinalApprovalRequirement.created_at.desc())
        .limit(50)
    ).scalars().all()
    return ApprovalRequirementListResponse(
        items=[
            ApprovalRequirementResponse(
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
            for row in rows
        ]
    )


@router.get("/decisions/{decision_id}", response_model=PolicyDecisionResponse)
@limiter.limit("120/minute")
def get_policy_decision(
    request: Request,
    decision_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> PolicyDecisionResponse:
    row = db.execute(
        select(FinalPolicyDecision).where(
            FinalPolicyDecision.id == decision_id,
            FinalPolicyDecision.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy decision not found.")
    approvals = db.execute(
        select(FinalApprovalRequirement).where(
            FinalApprovalRequirement.project_id == context.tenant_id,
            FinalApprovalRequirement.policy_decision_id == row.id,
        )
    ).scalars().all()
    return _response(row, approvals)
