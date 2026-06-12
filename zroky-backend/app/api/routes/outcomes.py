"""Cost-of-Failure Attribution API — outcome ingest + attribution reads + webhooks.

Surface:
  POST /v1/outcomes                      — ingest (SDK + direct)
  GET  /v1/outcomes/summary              — KPI strip: total cost, by-type, by-cluster
  GET  /v1/outcomes/by-call/{call_id}    — outcome events for a specific call
  GET  /v1/outcomes/replay/{run_id}      — prevented savings for a replay run
  POST /v1/outcomes/webhooks/zendesk     — Zendesk ticket.created / ticket.updated
  POST /v1/outcomes/webhooks/salesforce  — Salesforce Opportunity stage-change
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.services.outcome_attribution import (
    KNOWN_OUTCOME_TYPES,
    AttributionClusterRow,
    CallOutcomeView,
    OutcomeSummary,
    OutcomeTypeRow,
    get_attribution_summary,
    get_call_outcomes,
    get_replay_prevented_savings,
    ingest_outcome,
    normalise_salesforce_event,
    normalise_zendesk_ticket,
)

router = APIRouter(prefix="/v1/outcomes", tags=["outcomes"])
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────


class OutcomeIngest(BaseModel):
    call_id: str | None = Field(None, description="Zroky call_id to attribute this outcome to.")
    outcome_type: str = Field(
        ...,
        description=(
            "Business event type: refund_issued | ticket_escalated | "
            "human_handoff | churn | compliance_fine | retry_cost | custom"
        ),
    )
    amount_usd: float = Field(..., ge=0, description="Monetary cost of this outcome in USD.")
    occurred_at: datetime | None = Field(None, description="When the event happened (defaults to now).")
    external_ref: str | None = Field(None, description="Your own reference ID (order_id, ticket_id, …).")
    idempotency_key: str | None = Field(
        None,
        description="Dedup key — same key + project always returns the same row.",
    )
    metadata: dict[str, Any] | None = Field(None, description="Arbitrary key-value context.")

    @field_validator("outcome_type")
    @classmethod
    def _normalise_type(cls, v: str) -> str:
        return v.strip().lower()


class OutcomeView(BaseModel):
    id: str
    project_id: str
    call_id: str | None
    outcome_type: str
    amount_usd: float
    source: str
    occurred_at: datetime
    external_ref: str | None
    created_at: datetime


class OutcomeTypeView(BaseModel):
    outcome_type: str
    total_usd: float
    count: int
    avg_usd: float


class ClusterView(BaseModel):
    agent_name: str | None
    detector: str | None
    outcome_cost_usd: float
    outcome_count: int
    failure_count: int
    estimated_monthly_savings_usd: float
    top_outcome_type: str | None


class SummaryResponse(BaseModel):
    window_days: int
    total_outcome_usd: float
    linked_outcome_count: int
    unlinked_outcome_count: int
    avg_cost_per_linked: float
    by_type: list[OutcomeTypeView]
    by_cluster: list[ClusterView]


class ReplaySavingsResponse(BaseModel):
    run_id: str
    prevented_outcome_cost_usd: float
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _serialize_outcome(o) -> OutcomeView:
    return OutcomeView(
        id=o.id,
        project_id=o.project_id,
        call_id=o.call_id,
        outcome_type=o.outcome_type,
        amount_usd=float(o.amount_usd),
        source=o.source,
        occurred_at=o.occurred_at,
        external_ref=o.external_ref,
        created_at=o.created_at,
    )


def _serialize_summary(s: OutcomeSummary) -> SummaryResponse:
    return SummaryResponse(
        window_days=s.window_days,
        total_outcome_usd=s.total_outcome_usd,
        linked_outcome_count=s.linked_outcome_count,
        unlinked_outcome_count=s.unlinked_outcome_count,
        avg_cost_per_linked=s.avg_cost_per_linked,
        by_type=[
            OutcomeTypeView(
                outcome_type=t.outcome_type,
                total_usd=t.total_usd,
                count=t.count,
                avg_usd=t.avg_usd,
            )
            for t in s.by_type
        ],
        by_cluster=[
            ClusterView(
                agent_name=c.agent_name,
                detector=c.detector,
                outcome_cost_usd=c.outcome_cost_usd,
                outcome_count=c.outcome_count,
                failure_count=c.failure_count,
                estimated_monthly_savings_usd=c.estimated_monthly_savings_usd,
                top_outcome_type=c.top_outcome_type,
            )
            for c in s.by_cluster
        ],
    )


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("", response_model=OutcomeView, status_code=201)
@limiter.limit("120/minute")
def create_outcome(
    request: Request,
    body: OutcomeIngest,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeView:
    """Ingest one business-outcome event and attribute it to a call."""
    evt = ingest_outcome(
        db,
        project_id=tenant_id,
        call_id=body.call_id,
        outcome_type=body.outcome_type,
        amount_usd=body.amount_usd,
        source="api",
        external_ref=body.external_ref,
        idempotency_key=body.idempotency_key,
        occurred_at=body.occurred_at,
        metadata=body.metadata,
    )
    return _serialize_outcome(evt)


@router.get("/summary", response_model=SummaryResponse)
@limiter.limit("30/minute")
def get_summary(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    days: int = Query(default=30, ge=1, le=365),
) -> SummaryResponse:
    """Attribution summary: total cost + by-type + by-cluster (agent × detector)."""
    s = get_attribution_summary(db, project_id=tenant_id, days=days)
    return _serialize_summary(s)


@router.get("/by-call/{call_id}", response_model=list[OutcomeTypeView])
@limiter.limit("60/minute")
def get_outcomes_for_call(
    request: Request,
    call_id: str,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> list[OutcomeTypeView]:
    """All outcome events linked to a specific call."""
    views = get_call_outcomes(db, project_id=tenant_id, call_id=call_id)
    return [
        OutcomeTypeView(
            outcome_type=v.outcome_type,
            total_usd=v.amount_usd,
            count=1,
            avg_usd=v.amount_usd,
        )
        for v in views
    ]


@router.get("/replay/{run_id}", response_model=ReplaySavingsResponse)
@limiter.limit("30/minute")
def get_replay_savings(
    request: Request,
    run_id: str,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> ReplaySavingsResponse:
    """Compute the $ value of failures a replay run's candidate prompt would prevent."""
    savings = get_replay_prevented_savings(db, project_id=tenant_id, run_id=run_id)
    return ReplaySavingsResponse(
        run_id=run_id,
        prevented_outcome_cost_usd=savings,
        message=(
            f"This candidate prevents failures worth ${savings:,.2f} in linked outcome costs."
            if savings > 0
            else "No linked outcome events found for passing traces in this run."
        ),
    )


# ── Webhooks ──────────────────────────────────────────────────────────────────


@router.post("/webhooks/zendesk", status_code=200)
@limiter.limit("30/minute")
async def zendesk_webhook(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, str]:
    """Receive Zendesk ticket webhook and ingest escalations as outcome_events."""
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    fields = normalise_zendesk_ticket(payload)
    ingest_outcome(db, project_id=tenant_id, **fields)
    return {"status": "ok"}


@router.post("/webhooks/salesforce", status_code=200)
@limiter.limit("30/minute")
async def salesforce_webhook(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, str]:
    """Receive Salesforce Opportunity stage-change and ingest churn as outcome_events."""
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    fields = normalise_salesforce_event(payload)
    ingest_outcome(db, project_id=tenant_id, **fields)
    return {"status": "ok"}
