from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id
from app.db.models import (
    ActionIntent,
    ActionReceipt,
    OutcomeReconciliationCheck,
    RuntimePolicyDecision,
    SourceMutationRecord,
)
from app.db.session import get_db_session
from app.core.limiter import limiter
from app.schemas.home import HomeSummaryMetrics, HomeSummaryResponse

router = APIRouter(prefix="/v1/home", tags=["home"])


def _count(db: Session, statement) -> int:
    return int(db.execute(statement).scalar_one() or 0)


def _has_sequence_risk(policy_hit_json: str | None, reasons_json: str | None) -> bool:
    try:
        policy_hit: Any = json.loads(policy_hit_json or "{}")
    except json.JSONDecodeError:
        policy_hit = {}
    if isinstance(policy_hit, dict) and "sequence_risk" in policy_hit:
        return True
    try:
        reasons: Any = json.loads(reasons_json or "[]")
    except json.JSONDecodeError:
        reasons = []
    return any(isinstance(reason, str) and "sequence risk" in reason.lower() for reason in reasons)


@router.get("/summary", response_model=HomeSummaryResponse)
@limiter.limit("60/minute")
def get_home_summary(
    request: Request,
    days: int = Query(default=30, ge=1, le=90),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> HomeSummaryResponse:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    controlled_actions = _count(
        db,
        select(func.count(ActionIntent.id)).where(
            ActionIntent.project_id == tenant_id,
            ActionIntent.created_at >= since,
        ),
    )
    pending_approvals = _count(
        db,
        select(func.count(RuntimePolicyDecision.id)).where(
            RuntimePolicyDecision.project_id == tenant_id,
            RuntimePolicyDecision.status == "pending_approval",
        ),
    )
    outcome_rows = db.execute(
        select(OutcomeReconciliationCheck.verdict, func.count(OutcomeReconciliationCheck.id))
        .where(
            OutcomeReconciliationCheck.project_id == tenant_id,
            OutcomeReconciliationCheck.checked_at >= since,
        )
        .group_by(OutcomeReconciliationCheck.verdict)
    ).all()
    outcome_counts = {str(verdict): int(count or 0) for verdict, count in outcome_rows}
    outcome_checks = sum(outcome_counts.values())
    verified_outcomes = outcome_counts.get("matched", 0)

    receipts_generated = _count(
        db,
        select(func.count(ActionReceipt.id)).where(
            ActionReceipt.project_id == tenant_id,
            ActionReceipt.generated_at >= since,
        ),
    )
    mutation_rows = db.execute(
        select(SourceMutationRecord.classification, func.count(SourceMutationRecord.id))
        .where(
            SourceMutationRecord.project_id == tenant_id,
            SourceMutationRecord.occurred_at >= since,
        )
        .group_by(SourceMutationRecord.classification)
    ).all()
    mutation_counts = {str(classification): int(count or 0) for classification, count in mutation_rows}
    bypass_mutations = mutation_counts.get("policy_bypass", 0)
    unreceipted_mutations = sum(
        mutation_counts.get(classification, 0)
        for classification in ("legacy_path", "unmanaged_agent_action", "policy_bypass", "unknown_actor")
    )

    sequence_rows = db.execute(
        select(RuntimePolicyDecision.policy_hit_json, RuntimePolicyDecision.reasons_json).where(
            RuntimePolicyDecision.project_id == tenant_id,
            RuntimePolicyDecision.created_at >= since,
        )
    ).all()
    sequence_risks = sum(1 for policy_hit_json, reasons_json in sequence_rows if _has_sequence_risk(policy_hit_json, reasons_json))

    return HomeSummaryResponse(
        project_id=tenant_id,
        window_days=days,
        window_start=since,
        generated_at=now,
        metrics=HomeSummaryMetrics(
            controlled_actions=controlled_actions,
            pending_approvals=pending_approvals,
            verified_outcomes=verified_outcomes,
            outcome_checks=outcome_checks,
            receipts_generated=receipts_generated,
            bypass_mutations=bypass_mutations,
            unreceipted_mutations=unreceipted_mutations,
            sequence_risks=sequence_risks,
        ),
    )
