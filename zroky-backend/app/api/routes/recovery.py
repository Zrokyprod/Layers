from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.models import (
    FinalAssurancePack,
    FinalDomainOutboxJob,
    FinalObservation,
    FinalOutcomeGraph,
    FinalOutcomeIncident,
    FinalRecoveryPlan,
    FinalWorkflowIntent,
)
from app.db.session import get_db_session
from app.domain.outcome_graph import build_outcome_graph_snapshot
from app.services.action_kernel import canonical_json, sha256_digest


router = APIRouter(prefix="/v1/recovery")


class RecoveryPlaybookResponse(BaseModel):
    id: str
    project_id: str
    environment: str
    workflow_key: str
    version: str
    key: str
    incident_type: str
    playbook_digest: str
    steps: list[dict[str, Any]]


class RecoveryPlaybookListResponse(BaseModel):
    items: list[RecoveryPlaybookResponse]


class RecoveryPlanCompileRequest(BaseModel):
    incident_id: str
    playbook_key: str


class RecoveryPlanCompileResponse(BaseModel):
    incident_id: str
    playbook_id: str
    plan_digest: str
    plan: dict[str, Any]
    included_effects: list[str]
    skipped_effects: list[str]


class RecoveryDispatchClaimRequest(BaseModel):
    executor_ref: str
    lease_seconds: int = Field(default=300, ge=30, le=3600)


class RecoveryDispatchClaimResponse(BaseModel):
    outbox_job_id: str
    recovery_plan_id: str
    executor_ref: str
    nonce: str
    fencing_token: str
    lease_expires_at: datetime
    signed_payload: dict[str, Any]
    signature: str


class RecoveryResultReconstructRequest(BaseModel):
    outbox_job_id: str


class RecoveryResultReconstructResponse(BaseModel):
    outbox_job_id: str
    recovery_plan_id: str
    reconstruction_status: str
    outcome_graph_id: str
    recovery_execution_status: str
    incident_status: str
    graph_digest: str


def _playbook_response(row: FinalAssurancePack, playbook: dict[str, Any]) -> RecoveryPlaybookResponse:
    key = str(playbook.get("key") or "").strip()
    incident_type = str(playbook.get("incident_type") or "").strip()
    steps = playbook.get("steps")
    step_items = steps if isinstance(steps, list) else []
    doc = {
        "workflow_key": row.workflow_key,
        "version": row.version,
        "key": key,
        "incident_type": incident_type,
        "steps": step_items,
    }
    return RecoveryPlaybookResponse(
        id=f"{row.workflow_key}:{row.version}:{key}",
        project_id=row.project_id,
        environment=row.environment,
        workflow_key=row.workflow_key,
        version=row.version,
        key=key,
        incident_type=incident_type,
        playbook_digest=sha256_digest(canonical_json(doc)),
        steps=step_items,
    )


def _effect_keys(step: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    value = step.get("effect_key")
    if isinstance(value, str) and value.strip():
        keys.add(value.strip())
    values = step.get("effect_keys") or step.get("repairs_effects")
    if isinstance(values, list):
        keys.update(str(item).strip() for item in values if str(item).strip())
    return keys


def _active_packs(db: Session, *, project_id: str) -> list[FinalAssurancePack]:
    return list(
        db.execute(
            select(FinalAssurancePack)
            .where(FinalAssurancePack.project_id == project_id, FinalAssurancePack.status == "active")
            .order_by(FinalAssurancePack.workflow_key.asc(), FinalAssurancePack.version.desc())
        ).scalars()
    )


def _find_playbook(row: FinalAssurancePack, playbook_key: str) -> dict[str, Any] | None:
    pack = json.loads(row.pack_json)
    for playbook in pack.get("recovery_playbooks") or []:
        if isinstance(playbook, dict) and playbook.get("key") == playbook_key:
            return playbook
    return None


def _normalize_executor_ref(executor_ref: str) -> str:
    value = executor_ref.strip()
    if not value.startswith("customer-recovery-executor://"):
        raise HTTPException(status_code=400, detail="Unsupported recovery executor.")
    return value


def _dispatch_secret() -> str:
    settings = get_settings()
    return (
        settings.ACTION_RECEIPT_SIGNING_SECRET
        or settings.AUTH_JWT_SECRET
        or settings.INTERNAL_DEBUG_TOKEN
        or "local-dev-recovery-dispatch-secret"
    )


def _sign_dispatch(payload: dict[str, Any]) -> str:
    return hmac.new(_dispatch_secret().encode("utf-8"), canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def _observation_payloads(db: Session, *, project_id: str, environment: str, intent_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(FinalObservation)
        .where(
            FinalObservation.project_id == project_id,
            FinalObservation.environment == environment,
            FinalObservation.intent_id == intent_id,
        )
        .order_by(FinalObservation.observed_at.asc(), FinalObservation.created_at.asc())
    ).scalars()
    payloads = []
    for row in rows:
        payload = json.loads(row.observation_json)
        payload["observation_digest"] = row.observation_digest
        payloads.append(payload)
    return payloads


@router.get("/playbooks", response_model=RecoveryPlaybookListResponse)
@limiter.limit("120/minute")
def list_recovery_playbooks(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RecoveryPlaybookListResponse:
    items: list[RecoveryPlaybookResponse] = []
    for row in _active_packs(db, project_id=context.tenant_id):
        pack = json.loads(row.pack_json)
        for playbook in pack.get("recovery_playbooks") or []:
            if isinstance(playbook, dict):
                items.append(_playbook_response(row, playbook))
    return RecoveryPlaybookListResponse(items=items)


@router.get("/playbooks/{workflow_key}/{version}/{playbook_key}", response_model=RecoveryPlaybookResponse)
@limiter.limit("120/minute")
def get_recovery_playbook(
    request: Request,
    workflow_key: str,
    version: str,
    playbook_key: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RecoveryPlaybookResponse:
    row = db.execute(
        select(FinalAssurancePack).where(
            FinalAssurancePack.project_id == context.tenant_id,
            FinalAssurancePack.workflow_key == workflow_key,
            FinalAssurancePack.version == version,
            FinalAssurancePack.status == "active",
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Recovery playbook not found.")
    pack = json.loads(row.pack_json)
    for playbook in pack.get("recovery_playbooks") or []:
        if isinstance(playbook, dict) and playbook.get("key") == playbook_key:
            return _playbook_response(row, playbook)
    raise HTTPException(status_code=404, detail="Recovery playbook not found.")


@router.post("/compile-plan", response_model=RecoveryPlanCompileResponse)
@limiter.limit("120/minute")
def compile_recovery_plan(
    request: Request,
    body: RecoveryPlanCompileRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RecoveryPlanCompileResponse:
    incident = db.execute(
        select(FinalOutcomeIncident).where(
            FinalOutcomeIncident.id == body.incident_id,
            FinalOutcomeIncident.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    graph = db.execute(
        select(FinalOutcomeGraph).where(
            FinalOutcomeGraph.id == incident.outcome_graph_id,
            FinalOutcomeGraph.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if graph is None:
        raise HTTPException(status_code=404, detail="Outcome graph not found.")
    snapshot = json.loads(graph.graph_json)
    pack = db.execute(
        select(FinalAssurancePack).where(
            FinalAssurancePack.project_id == context.tenant_id,
            FinalAssurancePack.environment == graph.environment,
            FinalAssurancePack.workflow_key == snapshot.get("workflow_key"),
            FinalAssurancePack.version == snapshot.get("pack_version"),
            FinalAssurancePack.status == "active",
        )
    ).scalar_one_or_none()
    if pack is None:
        raise HTTPException(status_code=404, detail="Recovery playbook not found.")
    playbook = _find_playbook(pack, body.playbook_key)
    if playbook is None:
        raise HTTPException(status_code=404, detail="Recovery playbook not found.")

    effects = [item for item in snapshot.get("actual_effects", []) if isinstance(item, dict)]
    matched = {str(item.get("effect_key")) for item in effects if item.get("matched") is True and item.get("effect_key")}
    unresolved = {str(item.get("effect_key")) for item in effects if item.get("matched") is not True and item.get("effect_key")}
    steps = [item for item in playbook.get("steps", []) if isinstance(item, dict)]
    compiled_steps: list[dict[str, Any]] = []
    skipped_effects: set[str] = set()
    for step in steps:
        step_keys = _effect_keys(step)
        if step_keys and step_keys <= matched:
            skipped_effects.update(step_keys)
            continue
        compiled_steps.append(step)
    plan = {
        "schema_version": "zroky.recovery_plan.v1",
        "incident_id": incident.id,
        "outcome_graph_id": graph.id,
        "playbook_id": f"{pack.workflow_key}:{pack.version}:{body.playbook_key}",
        "target_effects": sorted(unresolved),
        "steps": compiled_steps,
    }
    return RecoveryPlanCompileResponse(
        incident_id=incident.id,
        playbook_id=plan["playbook_id"],
        plan_digest=sha256_digest(canonical_json(plan)),
        plan=plan,
        included_effects=sorted(unresolved),
        skipped_effects=sorted(skipped_effects),
    )


@router.post("/dispatch/claim", response_model=RecoveryDispatchClaimResponse)
@limiter.limit("120/minute")
def claim_recovery_dispatch(
    request: Request,
    body: RecoveryDispatchClaimRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RecoveryDispatchClaimResponse:
    executor_ref = _normalize_executor_ref(body.executor_ref)
    now = datetime.now(UTC)
    candidates = list(
        db.execute(
            select(FinalDomainOutboxJob)
            .where(
                FinalDomainOutboxJob.project_id == context.tenant_id,
                FinalDomainOutboxJob.job_type == "execute_recovery",
                or_(
                    FinalDomainOutboxJob.status == "pending",
                    (FinalDomainOutboxJob.status == "claimed") & (FinalDomainOutboxJob.lease_expires_at <= now),
                ),
            )
            .order_by(FinalDomainOutboxJob.available_at.asc(), FinalDomainOutboxJob.created_at.asc())
            .limit(20)
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    row: FinalDomainOutboxJob | None = None
    for candidate in candidates:
        payload = json.loads(candidate.payload_json or "{}")
        if payload.get("executor_ref") == executor_ref:
            row = candidate
            break
    if row is None:
        raise HTTPException(status_code=404, detail="No recovery dispatch is available for this executor.")

    row.status = "claimed"
    row.claimed_by = executor_ref[:128]
    row.claimed_at = now
    row.lease_expires_at = now + timedelta(seconds=body.lease_seconds)
    row.attempt_count = int(row.attempt_count or 0) + 1

    nonce = secrets.token_urlsafe(16)
    fencing_token = f"{row.id}:{row.attempt_count}"
    signed_payload = {
        "schema_version": "zroky.recovery_dispatch.v1",
        "outbox_job_id": row.id,
        "recovery_plan_id": row.aggregate_id,
        "executor_ref": executor_ref,
        "nonce": nonce,
        "fencing_token": fencing_token,
        "lease_expires_at": row.lease_expires_at.isoformat(),
    }
    signature = _sign_dispatch(signed_payload)
    row.result_json = canonical_json({"dispatch": signed_payload, "signature": signature})
    db.add(row)
    db.commit()
    db.refresh(row)
    return RecoveryDispatchClaimResponse(
        outbox_job_id=row.id,
        recovery_plan_id=row.aggregate_id,
        executor_ref=executor_ref,
        nonce=nonce,
        fencing_token=fencing_token,
        lease_expires_at=row.lease_expires_at,
        signed_payload=signed_payload,
        signature=signature,
    )


@router.post("/dispatch/reconstruct-unknown", response_model=RecoveryResultReconstructResponse)
@limiter.limit("60/minute")
def reconstruct_unknown_recovery_result(
    request: Request,
    body: RecoveryResultReconstructRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RecoveryResultReconstructResponse:
    now = datetime.now(UTC)
    job = db.execute(
        select(FinalDomainOutboxJob)
        .where(
            FinalDomainOutboxJob.id == body.outbox_job_id,
            FinalDomainOutboxJob.project_id == context.tenant_id,
            FinalDomainOutboxJob.job_type == "execute_recovery",
            FinalDomainOutboxJob.aggregate_type == "recovery_plan",
        )
        .with_for_update()
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Recovery dispatch not found.")
    if job.status not in {"claimed", "running"} or job.lease_expires_at is None or job.lease_expires_at > now:
        raise HTTPException(status_code=409, detail="Recovery dispatch is not result-unknown yet.")

    plan = db.execute(
        select(FinalRecoveryPlan).where(
            FinalRecoveryPlan.id == job.aggregate_id,
            FinalRecoveryPlan.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Recovery plan not found.")
    incident = db.execute(
        select(FinalOutcomeIncident).where(
            FinalOutcomeIncident.id == plan.incident_id,
            FinalOutcomeIncident.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    prior_graph = db.execute(
        select(FinalOutcomeGraph).where(
            FinalOutcomeGraph.id == incident.outcome_graph_id,
            FinalOutcomeGraph.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if prior_graph is None:
        raise HTTPException(status_code=404, detail="Outcome graph not found.")
    intent = db.execute(
        select(FinalWorkflowIntent).where(
            FinalWorkflowIntent.id == prior_graph.intent_id,
            FinalWorkflowIntent.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if intent is None:
        raise HTTPException(status_code=404, detail="Trusted intent not found.")

    prior_snapshot = json.loads(prior_graph.graph_json)
    pack_query = select(FinalAssurancePack).where(
        FinalAssurancePack.project_id == context.tenant_id,
        FinalAssurancePack.environment == prior_graph.environment,
        FinalAssurancePack.workflow_key == prior_snapshot.get("workflow_key"),
        FinalAssurancePack.version == prior_snapshot.get("pack_version"),
        FinalAssurancePack.status == "active",
    )
    assurance_pack_id = prior_snapshot.get("assurance_pack_id")
    if isinstance(assurance_pack_id, str) and assurance_pack_id:
        pack_query = pack_query.where(FinalAssurancePack.id == assurance_pack_id)
    pack = db.execute(pack_query).scalar_one_or_none()
    if pack is None:
        raise HTTPException(status_code=404, detail="Active Assurance Pack not found.")

    graph = build_outcome_graph_snapshot(
        intent=json.loads(intent.intent_json),
        assurance_pack=json.loads(pack.pack_json),
        observations=_observation_payloads(
            db,
            project_id=context.tenant_id,
            environment=prior_graph.environment,
            intent_id=intent.id,
        ),
    )
    graph.update(
        {
            "run_id": prior_snapshot.get("run_id"),
            "intent_id": intent.id,
            "assurance_pack_id": pack.id,
            "reconstructed_from_outbox_job_id": job.id,
            "reconstructed_at": now.isoformat(),
        }
    )
    graph_digest = sha256_digest(canonical_json(graph))
    verification_status = "verified" if graph["classification"] == "verified" else "failed"
    reconstructed_graph = FinalOutcomeGraph(
        project_id=context.tenant_id,
        environment=prior_graph.environment,
        intent_id=intent.id,
        graph_digest=graph_digest,
        graph_json=canonical_json(graph),
        verification_status=verification_status,
        verified_at=now if verification_status == "verified" else None,
    )
    db.add(reconstructed_graph)
    db.flush()

    incident_doc = json.loads(incident.incident_json)
    incident_doc["recovery_reconstruction"] = {
        "outbox_job_id": job.id,
        "outcome_graph_id": reconstructed_graph.id,
        "classification": graph["classification"],
        "reconstructed_at": now.isoformat(),
    }
    prior_result = json.loads(job.result_json or "{}")
    prior_result["reconstruction"] = incident_doc["recovery_reconstruction"]
    job.result_json = canonical_json(prior_result)
    job.completed_at = now
    if verification_status == "verified":
        plan.execution_status = "succeeded"
        job.status = "succeeded"
        incident.status = "resolved"
        incident.resolved_at = now
    else:
        plan.execution_status = "ambiguous"
        job.status = "dead"
        incident.status = "unresolved"
    incident.incident_json = canonical_json(incident_doc)
    db.add_all([job, plan, incident])
    db.commit()
    db.refresh(reconstructed_graph)
    db.refresh(plan)
    db.refresh(incident)
    return RecoveryResultReconstructResponse(
        outbox_job_id=job.id,
        recovery_plan_id=plan.id,
        reconstruction_status=graph["classification"],
        outcome_graph_id=reconstructed_graph.id,
        recovery_execution_status=plan.execution_status,
        incident_status=incident.status,
        graph_digest=reconstructed_graph.graph_digest,
    )
