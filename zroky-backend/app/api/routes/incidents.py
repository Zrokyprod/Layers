from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import FinalDomainOutboxJob, FinalOutcomeGraph, FinalOutcomeIncident, FinalRecoveryPlan
from app.db.session import get_db_session
from app.services.action_kernel import canonical_json, sha256_digest
from app.services.audit_logs import AUDIT_ACTION_RECOVERY_EXECUTE_REQUESTED, add_audit_log


router = APIRouter(prefix="/v1/incidents")


class IncidentResponse(BaseModel):
    id: str
    project_id: str
    environment: str
    outcome_graph_id: str
    severity: str
    status: str
    incident: dict[str, Any]
    created_at: datetime
    resolved_at: datetime | None


class IncidentAssignRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=255)


class IncidentManualResolveRequest(BaseModel):
    verified_outcome_graph_id: str = Field(min_length=1, max_length=36)
    note: str = Field(default="", max_length=1000)


class IncidentRecoveryExecuteRequest(BaseModel):
    executor_ref: str = Field(min_length=1, max_length=255)
    plan: dict[str, Any] = Field(default_factory=dict)


class IncidentRecoveryExecutionResponse(BaseModel):
    incident: IncidentResponse
    recovery_plan_id: str
    execution_status: str
    outbox_job_id: str
    idempotency_key: str


def incident_response(row: FinalOutcomeIncident) -> IncidentResponse:
    return IncidentResponse(
        id=row.id,
        project_id=row.project_id,
        environment=row.environment,
        outcome_graph_id=row.outcome_graph_id,
        severity=row.severity,
        status=row.status,
        incident=json.loads(row.incident_json),
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


def _require_admin(context: TenantContext) -> None:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required.")


def _load_incident(db: Session, *, project_id: str, incident_id: str) -> FinalOutcomeIncident:
    row = db.execute(
        select(FinalOutcomeIncident).where(
            FinalOutcomeIncident.id == incident_id,
            FinalOutcomeIncident.project_id == project_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return row


def _validate_executor_ref(value: str) -> str:
    normalized = value.strip()
    if not normalized.startswith("customer-recovery-executor://"):
        raise HTTPException(status_code=422, detail="executor_ref must be a customer recovery executor reference.")
    return normalized


def _require_recovery_separation_of_duties(row: FinalOutcomeIncident, context: TenantContext) -> None:
    if not context.subject:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authenticated subject required for recovery execution.")
    owner = str(json.loads(row.incident_json).get("owner") or "").strip()
    if owner and owner == context.subject:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Incident owner cannot execute recovery.")


@router.get("", response_model=list[IncidentResponse])
@limiter.limit("120/minute")
def list_incidents(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> list[IncidentResponse]:
    rows = db.execute(
        select(FinalOutcomeIncident)
        .where(FinalOutcomeIncident.project_id == context.tenant_id)
        .order_by(FinalOutcomeIncident.created_at.desc())
    ).scalars().all()
    return [incident_response(row) for row in rows]


@router.get("/{incident_id}", response_model=IncidentResponse)
@limiter.limit("120/minute")
def get_incident(
    request: Request,
    incident_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> IncidentResponse:
    row = _load_incident(db, project_id=context.tenant_id, incident_id=incident_id)
    return incident_response(row)


@router.post("/{incident_id}/assign", response_model=IncidentResponse)
@limiter.limit("120/minute")
def assign_incident(
    request: Request,
    incident_id: str,
    body: IncidentAssignRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> IncidentResponse:
    row = _load_incident(db, project_id=context.tenant_id, incident_id=incident_id)
    incident = json.loads(row.incident_json)
    incident["owner"] = body.owner
    incident["assigned_by"] = context.subject
    incident["assigned_at"] = datetime.now(UTC).isoformat()
    row.incident_json = json.dumps(incident, sort_keys=True, separators=(",", ":"))
    db.commit()
    db.refresh(row)
    return incident_response(row)


@router.post("/{incident_id}/resolve-manually", response_model=IncidentResponse)
@limiter.limit("60/minute")
def resolve_incident_manually(
    request: Request,
    incident_id: str,
    body: IncidentManualResolveRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> IncidentResponse:
    row = _load_incident(db, project_id=context.tenant_id, incident_id=incident_id)
    if row.status == "resolved":
        return incident_response(row)

    verified_graph = db.execute(
        select(FinalOutcomeGraph).where(
            FinalOutcomeGraph.id == body.verified_outcome_graph_id,
            FinalOutcomeGraph.project_id == context.tenant_id,
            FinalOutcomeGraph.intent_id == json.loads(row.incident_json).get("intent_id"),
            FinalOutcomeGraph.verification_status == "verified",
            FinalOutcomeGraph.id != row.outcome_graph_id,
        )
    ).scalar_one_or_none()
    if verified_graph is None:
        raise HTTPException(status_code=409, detail="Manual resolution requires a fresh verified outcome graph.")

    incident = json.loads(row.incident_json)
    incident["manual_resolution"] = {
        "verified_outcome_graph_id": verified_graph.id,
        "resolved_by": context.subject,
        "resolved_at": datetime.now(UTC).isoformat(),
        "note": body.note,
    }
    row.status = "resolved"
    row.resolved_at = datetime.now(UTC)
    row.incident_json = json.dumps(incident, sort_keys=True, separators=(",", ":"))
    db.commit()
    db.refresh(row)
    return incident_response(row)


@router.post("/{incident_id}/execute-recovery", response_model=IncidentRecoveryExecutionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def execute_incident_recovery(
    request: Request,
    incident_id: str,
    body: IncidentRecoveryExecuteRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> IncidentRecoveryExecutionResponse:
    _require_admin(context)
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required.")
    key = idempotency_key.strip()
    incident = _load_incident(db, project_id=context.tenant_id, incident_id=incident_id)
    if incident.status == "resolved":
        raise HTTPException(status_code=409, detail="Resolved incident cannot execute recovery.")
    _require_recovery_separation_of_duties(incident, context)

    existing_job = db.execute(
        select(FinalDomainOutboxJob).where(
            FinalDomainOutboxJob.project_id == context.tenant_id,
            FinalDomainOutboxJob.environment == incident.environment,
            FinalDomainOutboxJob.idempotency_key == key,
        )
    ).scalar_one_or_none()
    if existing_job is not None:
        plan = db.get(FinalRecoveryPlan, existing_job.aggregate_id)
        if plan is None or plan.incident_id != incident.id:
            raise HTTPException(status_code=409, detail="Recovery idempotency key belongs to another aggregate.")
        return IncidentRecoveryExecutionResponse(
            incident=incident_response(incident),
            recovery_plan_id=plan.id,
            execution_status=plan.execution_status,
            outbox_job_id=existing_job.id,
            idempotency_key=key,
        )

    executor_ref = _validate_executor_ref(body.executor_ref)
    plan_doc = {
        "schema_version": "zroky.recovery_plan.v1",
        "incident_id": incident.id,
        "outcome_graph_id": incident.outcome_graph_id,
        "executor_ref": executor_ref,
        "plan": body.plan,
    }
    plan_json = canonical_json(plan_doc)
    plan = FinalRecoveryPlan(
        project_id=context.tenant_id,
        environment=incident.environment,
        incident_id=incident.id,
        plan_digest=sha256_digest(plan_json),
        plan_json=plan_json,
        approval_status="approved",
        execution_status="dispatched",
    )
    db.add(plan)
    db.flush()
    job = FinalDomainOutboxJob(
        project_id=context.tenant_id,
        environment=incident.environment,
        job_type="execute_recovery",
        aggregate_type="recovery_plan",
        aggregate_id=plan.id,
        idempotency_key=key,
        payload_json=canonical_json({"recovery_plan_id": plan.id, "executor_ref": executor_ref}),
    )
    db.add(job)
    incident.status = "recovering"
    incident_doc = json.loads(incident.incident_json)
    incident_doc["recovery_execution"] = {
        "recovery_plan_id": plan.id,
        "outbox_job_id": job.id,
        "executor_ref": executor_ref,
        "requested_by": context.subject,
        "requested_at": datetime.now(UTC).isoformat(),
    }
    incident.incident_json = json.dumps(incident_doc, sort_keys=True, separators=(",", ":"))
    add_audit_log(
        db,
        tenant_id=context.tenant_id,
        diagnosis_id=incident.id,
        action=AUDIT_ACTION_RECOVERY_EXECUTE_REQUESTED,
        actor_subject=context.subject,
        metadata={
            "incident_id": incident.id,
            "recovery_plan_id": plan.id,
            "outbox_job_id": job.id,
            "executor_ref": executor_ref,
        },
    )
    db.commit()
    db.refresh(incident)
    db.refresh(plan)
    db.refresh(job)
    return IncidentRecoveryExecutionResponse(
        incident=incident_response(incident),
        recovery_plan_id=plan.id,
        execution_status=plan.execution_status,
        outbox_job_id=job.id,
        idempotency_key=key,
    )
