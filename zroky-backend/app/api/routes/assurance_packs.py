from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import FinalAssurancePack
from app.db.session import get_db_session
from app.domain.assurance_pack.predicate import PredicateError, evaluate_predicate
from app.domain.assurance_pack.schema import SCHEMA_VERSION, validate_assurance_pack
from app.domain.assurance_pack.simulation import simulate_pack


router = APIRouter(prefix="/v1/assurance-packs")


class AssurancePackUpsertRequest(BaseModel):
    environment: str = Field(default="production", min_length=1, max_length=64)
    pack: dict[str, Any]


class AssurancePackResponse(BaseModel):
    id: str
    project_id: str
    environment: str
    workflow_key: str
    version: str
    pack_digest: str
    status: str
    pack: dict[str, Any]


class PredicateEvaluateRequest(BaseModel):
    predicate: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class PackSimulationRequest(BaseModel):
    pack: dict[str, Any]
    cases: dict[str, dict[str, Any]]


def _require_admin(context: TenantContext) -> None:
    if ROLE_RANK[context.role] < ROLE_RANK["admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role is required.")


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _response(row: FinalAssurancePack) -> AssurancePackResponse:
    return AssurancePackResponse(
        id=row.id,
        project_id=row.project_id,
        environment=row.environment,
        workflow_key=row.workflow_key,
        version=row.version,
        pack_digest=row.pack_digest,
        status=row.status,
        pack=json.loads(row.pack_json),
    )


@router.post("/validate")
@limiter.limit("120/minute")
def validate_pack(request: Request, body: AssurancePackUpsertRequest) -> dict[str, Any]:
    pack = validate_assurance_pack(body.pack)
    return {"valid": True, "schema_version": SCHEMA_VERSION, "workflow_key": pack.workflow_key, "version": pack.version}


@router.post("/predicates/evaluate")
@limiter.limit("120/minute")
def evaluate_pack_predicate(request: Request, body: PredicateEvaluateRequest) -> dict[str, Any]:
    try:
        return {"result": evaluate_predicate(body.predicate, body.context)}
    except PredicateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/simulate")
@limiter.limit("60/minute")
def simulate_assurance_pack(request: Request, body: PackSimulationRequest) -> dict[str, Any]:
    return simulate_pack(body.pack, body.cases)


@router.post("", response_model=AssurancePackResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def create_pack(
    request: Request,
    body: AssurancePackUpsertRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> AssurancePackResponse:
    _require_admin(context)
    pack = validate_assurance_pack(body.pack)
    payload = pack.model_dump(by_alias=True)
    digest = _digest(payload)
    environment = body.environment.strip().lower()
    existing = db.execute(
        select(FinalAssurancePack).where(
            FinalAssurancePack.project_id == context.tenant_id,
            FinalAssurancePack.environment == environment,
            FinalAssurancePack.workflow_key == pack.workflow_key,
            FinalAssurancePack.version == pack.version,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.pack_digest != digest:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Assurance Pack version is immutable.")
        return _response(existing)

    row = FinalAssurancePack(
        project_id=context.tenant_id,
        environment=environment,
        workflow_key=pack.workflow_key,
        version=pack.version,
        pack_digest=digest,
        pack_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _response(row)


@router.get("/{pack_id}", response_model=AssurancePackResponse)
@limiter.limit("120/minute")
def get_pack(
    request: Request,
    pack_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> AssurancePackResponse:
    row = db.execute(
        select(FinalAssurancePack).where(
            FinalAssurancePack.id == pack_id,
            FinalAssurancePack.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assurance Pack not found.")
    return _response(row)
