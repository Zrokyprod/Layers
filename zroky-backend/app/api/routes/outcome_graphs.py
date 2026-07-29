from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.api.dependencies.authorization import ROLE_RANK
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.models import FinalAgentRun, FinalAssurancePack, FinalObservation, FinalOutcomeGraph, FinalWorkflowIntent
from app.db.models import FinalOutcomeIncident
from app.db.session import get_db_session
from app.domain.incident import build_incident_from_outcome_graph
from app.domain.outcome_graph import build_outcome_graph_snapshot
from app.services.action_receipts import ActionReceiptSigningError, action_receipt_public_key_payload
from app.services.dsse import sign_envelope
from app.services.final_outcome_graphs import (
    FINAL_OUTCOME_CLASSIFICATIONS,
    apply_outcome_graph_ledger_state,
    graph_digest,
    recheck_due_outcome_graphs,
)


router = APIRouter()


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
    classification: str | None = None
    reason_code: str | None = None
    last_checked_at: datetime | None = None
    next_check_at: datetime | None = None
    verified_at: datetime | None
    created_at: datetime


class OutcomeGraphListResponse(BaseModel):
    items: list[OutcomeGraphResponse]


class OutcomeGraphCoverageSummaryResponse(BaseModel):
    counts: dict[str, int]
    total: int
    coverage_percent: float


class OutcomeGraphRecheckDueResponse(BaseModel):
    checked: int
    updated: int


class AttestationPublicKeyResponse(BaseModel):
    key_id: str
    algorithm: str
    public_key: str
    public_key_encoding: str


def _response(row: FinalOutcomeGraph) -> OutcomeGraphResponse:
    return OutcomeGraphResponse(
        id=row.id,
        project_id=row.project_id,
        environment=row.environment,
        intent_id=row.intent_id,
        graph_digest=row.graph_digest,
        graph=json.loads(row.graph_json),
        verification_status=row.verification_status,
        classification=row.classification,
        reason_code=row.reason_code,
        last_checked_at=row.last_checked_at,
        next_check_at=row.next_check_at,
        verified_at=row.verified_at,
        created_at=row.created_at,
    )


def _signing_unavailable(exc: ActionReceiptSigningError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="attestation signing key not configured",
    )


def _public_key_payload() -> dict[str, Any]:
    payload = action_receipt_public_key_payload()
    return {
        "key_id": payload["key_id"],
        "algorithm": "ed25519",
        "public_key": payload["public_key"],
        "public_key_encoding": payload["public_key_encoding"],
    }


def _get_graph(db: Session, context: TenantContext, graph_id: str) -> FinalOutcomeGraph:
    row = db.execute(
        select(FinalOutcomeGraph).where(
            FinalOutcomeGraph.id == graph_id,
            FinalOutcomeGraph.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outcome graph not found.")
    return row


def _loads(value: str) -> dict[str, Any]:
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else {}


def _canonical_graph_digest(graph: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(graph, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _outcome_graph_statement(db: Session, row: FinalOutcomeGraph) -> dict[str, Any]:
    graph = _loads(row.graph_json)
    intent = db.execute(
        select(FinalWorkflowIntent).where(
            FinalWorkflowIntent.id == row.intent_id,
            FinalWorkflowIntent.project_id == row.project_id,
        )
    ).scalar_one_or_none()
    if intent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trusted intent not found.")
    incident = db.execute(
        select(FinalOutcomeIncident)
        .where(FinalOutcomeIncident.project_id == row.project_id, FinalOutcomeIncident.outcome_graph_id == row.id)
        .order_by(FinalOutcomeIncident.created_at.desc())
    ).scalars().first()
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {"name": f"outcome-graph/{row.id}", "digest": {"sha256": _canonical_graph_digest(graph)}},
            {"name": f"intent/{row.intent_id}", "digest": {"sha256": intent.intent_digest}},
        ],
        "predicateType": "https://zroky.com/attestations/outcome-proof/v1",
        "predicate": {
            "workflow_key": graph.get("workflow_key"),
            "pack_version": graph.get("pack_version"),
            "classification": row.classification,
            "verification_status": row.verification_status,
            "effects": [
                {
                    "effect_key": effect.get("effect_key"),
                    "matched": bool(effect.get("matched")),
                    "observation_digest": effect.get("observation_digest"),
                }
                for effect in graph.get("actual_effects", [])
                if isinstance(effect, dict)
            ],
            "verified_at": row.verified_at.isoformat() if row.verified_at else None,
            "recovered": bool(incident and incident.status == "resolved"),
            "incident_id": incident.id if incident else None,
        },
    }


def _evidence_summary(row: FinalOutcomeGraph) -> dict[str, Any]:
    graph = _loads(row.graph_json)
    effects = [effect for effect in graph.get("actual_effects", []) if isinstance(effect, dict)]
    return {
        "workflow": graph.get("workflow_key"),
        "claim": f"{len(graph.get('expected_effects', []))} expected effect(s)",
        "observed": f"{sum(1 for effect in effects if effect.get('observed') is True)} observed effect(s)",
        "classification": row.classification,
        "verification_status": row.verification_status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
    }


@router.get("/v1/attestations/public-key", response_model=AttestationPublicKeyResponse)
@limiter.limit("120/minute")
def get_attestation_public_key(
    request: Request,
) -> AttestationPublicKeyResponse:
    try:
        return AttestationPublicKeyResponse(**_public_key_payload())
    except ActionReceiptSigningError as exc:
        raise _signing_unavailable(exc) from exc


@router.get("/v1/outcome-graphs", response_model=OutcomeGraphListResponse)
@limiter.limit("120/minute")
def list_outcome_graphs(
    request: Request,
    classification: str | None = None,
    limit: int = 50,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> OutcomeGraphListResponse:
    if classification is not None and classification not in FINAL_OUTCOME_CLASSIFICATIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid classification.")
    query = select(FinalOutcomeGraph).where(FinalOutcomeGraph.project_id == context.tenant_id)
    if classification is not None:
        query = query.where(FinalOutcomeGraph.classification == classification)
    rows = db.execute(
        query.order_by(FinalOutcomeGraph.created_at.desc()).limit(max(1, min(int(limit), 100)))
    ).scalars()
    return OutcomeGraphListResponse(items=[_response(row) for row in rows])


@router.get("/v1/outcome-graphs/coverage-summary", response_model=OutcomeGraphCoverageSummaryResponse)
@limiter.limit("120/minute")
def outcome_graph_coverage_summary(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> OutcomeGraphCoverageSummaryResponse:
    counts = {classification: 0 for classification in sorted(FINAL_OUTCOME_CLASSIFICATIONS)}
    rows = db.execute(
        select(FinalOutcomeGraph.classification, func.count())
        .where(FinalOutcomeGraph.project_id == context.tenant_id)
        .group_by(FinalOutcomeGraph.classification)
    ).all()
    for classification, count in rows:
        key = classification or "unknown"
        if key in counts:
            counts[key] = int(count)
    total = sum(counts.values())
    verified = counts["verified"]
    coverage = round((verified / total) * 100, 2) if total else 0.0
    return OutcomeGraphCoverageSummaryResponse(counts=counts, total=total, coverage_percent=coverage)


@router.post("/v1/outcome-graphs/recheck-due", response_model=OutcomeGraphRecheckDueResponse)
@limiter.limit("20/minute")
def recheck_due_outcome_graphs_now(
    request: Request,
    limit: int = 100,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> OutcomeGraphRecheckDueResponse:
    if ROLE_RANK[context.role] < ROLE_RANK["admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required.")
    result = recheck_due_outcome_graphs(
        db,
        limit=max(1, min(int(limit), 100)),
        project_id=context.tenant_id,
        verification_window_seconds=get_settings().FINAL_OUTCOME_GRAPH_VERIFICATION_WINDOW_SECONDS,
    )
    return OutcomeGraphRecheckDueResponse(**result)


@router.get("/v1/outcome-graphs/{graph_id}/attestation")
@limiter.limit("120/minute")
def get_outcome_graph_attestation(
    request: Request,
    graph_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    row = _get_graph(db, context, graph_id)
    try:
        return sign_envelope(_outcome_graph_statement(db, row))
    except ActionReceiptSigningError as exc:
        raise _signing_unavailable(exc) from exc


@router.get("/v1/outcome-graphs/{graph_id}/evidence-export")
@limiter.limit("60/minute")
def get_outcome_graph_evidence_export(
    request: Request,
    graph_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    row = _get_graph(db, context, graph_id)
    try:
        return {
            "attestation": sign_envelope(_outcome_graph_statement(db, row)),
            "public_key": _public_key_payload(),
            "summary": _evidence_summary(row),
            "verify_instructions": "python -m zroky.verify_attestation zroky-evidence-%s.json" % row.id,
        }
    except ActionReceiptSigningError as exc:
        raise _signing_unavailable(exc) from exc


@router.post("/v1/runs/{run_id}/outcome-graph", response_model=OutcomeGraphResponse, status_code=status.HTTP_201_CREATED)
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
    digest = graph_digest(graph)
    row = FinalOutcomeGraph(
        project_id=context.tenant_id,
        environment=run.environment,
        intent_id=intent.id,
        graph_digest=digest,
        graph_json=json.dumps(graph, sort_keys=True, separators=(",", ":")),
    )
    apply_outcome_graph_ledger_state(
        row,
        graph,
        verification_window_seconds=get_settings().FINAL_OUTCOME_GRAPH_VERIFICATION_WINDOW_SECONDS,
    )
    db.add(row)
    db.flush()
    if row.verification_status != "verified":
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
