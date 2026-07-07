from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.api.routes._action_intents_helpers import _execution_attempt_response, _intent_response
from app.api.routes.billing import get_billing_usage
from app.api.routes.outcome_serializers import _serialize_reconciliation, _serialize_source_mutation
from app.api.routes.runtime_policy import _decision_to_response
from app.core.limiter import limiter
from app.db.models import ActionIntent, RuntimePolicyDecision
from app.db.session import get_db_session
from app.schemas.actions import (
    ActionsLifecycleData,
    ActionsLifecycleMetrics,
    ActionsLifecycleSources,
    ActionsLifecycleSummaryResponse,
)
from app.schemas.outcomes import OutcomeReconciliationSummaryResponse, SourceMutationSummaryResponse
from app.services.action_kernel import list_action_intents
from app.services.action_runner import list_project_execution_attempts
from app.services.outcome_reconciliation import get_reconciliation_summary, list_reconciliations
from app.services.source_mutations import list_source_mutations, source_mutation_summary

router = APIRouter(prefix="/v1/actions", tags=["actions"])


def _dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return dict(value)


@router.get("/lifecycle-summary", response_model=ActionsLifecycleSummaryResponse)
@limiter.limit("60/minute")
def get_actions_lifecycle_summary(
    request: Request,
    days: int = Query(default=30, ge=1, le=90),
    limit: int = Query(default=100, ge=25, le=100),
    db: Session = Depends(get_db_session),
    context: TenantContext = Depends(require_tenant_context),
) -> ActionsLifecycleSummaryResponse:
    tenant_id = context.tenant_id
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    sources = ActionsLifecycleSources()

    intents = list_action_intents(db, project_id=tenant_id, limit=limit, offset=0)
    approvals = list(
        db.execute(
            select(RuntimePolicyDecision)
            .where(RuntimePolicyDecision.project_id == tenant_id)
            .order_by(RuntimePolicyDecision.created_at.desc())
            .limit(limit)
        ).scalars()
    )
    outcomes = list_reconciliations(db, project_id=tenant_id, verdict=None, limit=limit)
    outcome_summary = get_reconciliation_summary(db, project_id=tenant_id, days=days)
    source_summary = source_mutation_summary(db, project_id=tenant_id)
    mutations = list_source_mutations(db, project_id=tenant_id, unreceipted_only=True, limit=limit)
    stale_attempts = list_project_execution_attempts(
        db,
        project_id=tenant_id,
        statuses=["planned", "dispatched", "running"],
        stale=True,
        stale_after_seconds=600,
        limit=limit,
        offset=0,
    )

    try:
        billing_usage = get_billing_usage(request=request, tenant_id=tenant_id, db=db)
    except Exception:
        billing_usage = None
        sources.billing_usage = False

    controlled_actions = int(
        db.execute(
            select(func.count(ActionIntent.id)).where(
                ActionIntent.project_id == tenant_id,
                ActionIntent.created_at >= since,
            )
        ).scalar_one()
        or 0
    )
    held_actions = int(
        db.execute(
            select(func.count(RuntimePolicyDecision.id)).where(
                RuntimePolicyDecision.project_id == tenant_id,
                RuntimePolicyDecision.status == "pending_approval",
            )
        ).scalar_one()
        or 0
    )

    data = ActionsLifecycleData(
        intents=[_dump(_intent_response(db, row)) for row in intents],
        approvals=[_dump(_decision_to_response(row)) for row in approvals],
        outcomes=[_dump(_serialize_reconciliation(row)) for row in outcomes],
        outcome_summary=_dump(
            OutcomeReconciliationSummaryResponse(
                window_days=outcome_summary.window_days,
                total=outcome_summary.total,
                matched=outcome_summary.matched,
                mismatched=outcome_summary.mismatched,
                not_verified=outcome_summary.not_verified,
                verified=outcome_summary.verified,
                pending=outcome_summary.pending,
                unverifiable=outcome_summary.unverifiable,
                cancelled=outcome_summary.cancelled,
            )
        ),
        source_summary=_dump(SourceMutationSummaryResponse(**source_summary)),
        mutations=[_dump(_serialize_source_mutation(row)) for row in mutations],
        stale_attempts=[_dump(_execution_attempt_response(row)) for row in stale_attempts],
        billing_usage=_dump(billing_usage) if billing_usage is not None else None,
    )

    return ActionsLifecycleSummaryResponse(
        project_id=tenant_id,
        window_days=days,
        window_start=since,
        generated_at=now,
        row_limit=limit,
        metrics=ActionsLifecycleMetrics(
            controlled_actions=controlled_actions,
            held_actions=held_actions,
            matched_outcomes=outcome_summary.matched,
            mismatched_outcomes=outcome_summary.mismatched,
            not_verified_outcomes=outcome_summary.not_verified,
            bypass_risk=int(source_summary.get("unreceipted", 0) or 0),
        ),
        sources=sources,
        data=data,
    )
