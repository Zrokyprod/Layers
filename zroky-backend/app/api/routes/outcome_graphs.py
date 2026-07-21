from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import FinalAgentRun, FinalAssurancePack, FinalObservation, FinalOutcomeGraph, FinalWorkflowIntent
from app.db.models import FinalOutcomeIncident
from app.db.session import get_db_session
from app.domain.incident import build_incident_from_outcome_graph
from app.domain.outcome_graph import build_outcome_graph_snapshot


router = APIRouter(prefix="/v1/runs")


class OutcomeGraphBuildRequest(BaseModel):
    assurance_pack_id: str | None = None


class OutcomeGraphResponse(BaseModel):
    id: str
    project_id: str
    environment: str
    intent_id: str
    graph_digest: str
    graph: dict[str, Any]
    verification_status: str
    verified_at: datetime | None
    created_at: datetime


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _response(row: FinalOutcomeGraph) -> OutcomeGraphResponse:
    return OutcomeGraphResponse(
        id=row.id,
        project_id=row.project_id,
        environment=row.environment,
        intent_id=row.intent_id,
        graph_digest=row.graph_digest,
        graph=json.loads(row.graph_json),
        verification_status=row.verification_status,
        verified_at=row.verified_at,
        created_at=row.created_at,
    )


@router.post("/{run_id}/outcome-graph", response_model=OutcomeGraphResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def build_run_outcome_graph(
    request: Request,
    run_id: str,
    body: OutcomeGraphBuildRequest | None = None,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> OutcomeGraphResponse:
    run = db.execute(
        select(FinalAgentRun).where(FinalAgentRun.id == run_id, FinalAgentRun.project_id == context.tenant_id)
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    if not run.intent_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run must reference a trusted intent.")

    intent = db.execute(
        select(FinalWorkflowIntent).where(FinalWorkflowIntent.id == run.intent_id, FinalWorkflowIntent.project_id == context.tenant_id)
    ).scalar_one_or_none()
    if intent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trusted intent not found.")

    pack_query = select(FinalAssurancePack).where(
        FinalAssurancePack.project_id == context.tenant_id,
        FinalAssurancePack.environment == run.environment,
        FinalAssurancePack.status == "active",
    )
    if body and body.assurance_pack_id:
        pack_query = pack_query.where(FinalAssurancePack.id == body.assurance_pack_id)
    elif run.workflow_key:
        pack_query = pack_query.where(FinalAssurancePack.workflow_key == run.workflow_key)
    pack = db.execute(pack_query.order_by(FinalAssurancePack.created_at.desc())).scalars().first()
    if pack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active Assurance Pack not found.")

    observations = db.execute(
        select(FinalObservation).where(
            FinalObservation.project_id == context.tenant_id,
            FinalObservation.environment == run.environment,
            FinalObservation.intent_id == run.intent_id,
        )
    ).scalars().all()
    observation_payloads = []
    for observation in observations:
        payload = json.loads(observation.observation_json)
        payload["observation_digest"] = observation.observation_digest
        observation_payloads.append(payload)

    graph = build_outcome_graph_snapshot(
        intent=json.loads(intent.intent_json),
        assurance_pack=json.loads(pack.pack_json),
        observations=observation_payloads,
    )
    graph.update({"run_id": run.id, "intent_id": intent.id, "assurance_pack_id": pack.id})
    digest = _digest(graph)
    verification_status = "verified" if graph["classification"] == "verified" else "failed"
    row = FinalOutcomeGraph(
        project_id=context.tenant_id,
        environment=run.environment,
        intent_id=intent.id,
        graph_digest=digest,
        graph_json=json.dumps(graph, sort_keys=True, separators=(",", ":")),
        verification_status=verification_status,
    )
    db.add(row)
    db.flush()
    if verification_status != "verified":
        incident = build_incident_from_outcome_graph(row.id, graph)
        db.add(
            FinalOutcomeIncident(
                project_id=context.tenant_id,
                environment=run.environment,
                outcome_graph_id=row.id,
                severity=incident["severity"],
                status="open",
                incident_json=json.dumps(incident, sort_keys=True, separators=(",", ":")),
            )
        )
    db.commit()
    db.refresh(row)
    return _response(row)
