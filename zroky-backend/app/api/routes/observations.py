from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import FinalAgentRun, FinalObservation, FinalWorkflowIntent
from app.db.session import get_db_session


router = APIRouter(prefix="/v1/observations")


class ObservationCreateRequest(BaseModel):
    environment: str = Field(default="production", min_length=1, max_length=64)
    run_id: str | None = Field(default=None, max_length=36)
    intent_id: str | None = Field(default=None, max_length=36)
    source_kind: str = Field(min_length=1, max_length=64)
    observed_object_ref: str = Field(min_length=1, max_length=255)
    observed_state: dict[str, Any]
    provenance: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime
    read_at: datetime | None = None
    max_freshness_seconds: int = Field(default=300, ge=1, le=86_400)

    @field_validator("environment", "source_kind")
    @classmethod
    def _clean_lower(cls, value: str) -> str:
        return value.strip().lower()


class ObservationResponse(BaseModel):
    id: str
    project_id: str
    environment: str
    intent_id: str | None
    run_id: str | None
    source_kind: str
    observed_object_ref: str
    observation_digest: str
    observation: dict[str, Any]
    observed_at: datetime
    created_at: datetime


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")).hexdigest()


def _freshness(observed_at: datetime, read_at: datetime, max_seconds: int) -> dict[str, Any]:
    observed = observed_at.astimezone(UTC)
    read = read_at.astimezone(UTC)
    age = max(0, int((read - observed).total_seconds()))
    return {"age_seconds": age, "max_freshness_seconds": max_seconds, "fresh": age <= max_seconds}


def _payload(body: ObservationCreateRequest) -> dict[str, Any]:
    read_at = body.read_at or datetime.now(UTC)
    return {
        "schema_version": "zroky.observation.v1",
        "run_id": body.run_id,
        "intent_id": body.intent_id,
        "source_kind": body.source_kind,
        "observed_object_ref": body.observed_object_ref,
        "observed_state": body.observed_state,
        "provenance": body.provenance,
        "observed_at": body.observed_at,
        "read_at": read_at,
        "freshness": _freshness(body.observed_at, read_at, body.max_freshness_seconds),
    }


def _response(row: FinalObservation) -> ObservationResponse:
    observation = json.loads(row.observation_json)
    return ObservationResponse(
        id=row.id,
        project_id=row.project_id,
        environment=row.environment,
        intent_id=row.intent_id,
        run_id=observation.get("run_id"),
        source_kind=row.source_kind,
        observed_object_ref=row.observed_object_ref,
        observation_digest=row.observation_digest,
        observation=observation,
        observed_at=row.observed_at,
        created_at=row.created_at,
    )


@router.post("", response_model=ObservationResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("120/minute")
def create_observation(
    request: Request,
    body: ObservationCreateRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ObservationResponse:
    if body.intent_id:
        intent = db.execute(
            select(FinalWorkflowIntent).where(
                FinalWorkflowIntent.id == body.intent_id,
                FinalWorkflowIntent.project_id == context.tenant_id,
            )
        ).scalar_one_or_none()
        if intent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trusted intent not found.")
    if body.run_id:
        run = db.execute(
            select(FinalAgentRun).where(
                FinalAgentRun.id == body.run_id,
                FinalAgentRun.project_id == context.tenant_id,
            )
        ).scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")

    payload = _payload(body)
    digest = _digest(payload)
    existing = db.execute(
        select(FinalObservation).where(
            FinalObservation.project_id == context.tenant_id,
            FinalObservation.environment == body.environment,
            FinalObservation.observation_digest == digest,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _response(existing)

    row = FinalObservation(
        project_id=context.tenant_id,
        environment=body.environment,
        intent_id=body.intent_id,
        source_kind=body.source_kind,
        observed_object_ref=body.observed_object_ref,
        observation_digest=digest,
        observation_json=json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default),
        observed_at=body.observed_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _response(row)


@router.get("/{observation_id}", response_model=ObservationResponse)
@limiter.limit("120/minute")
def get_observation(
    request: Request,
    observation_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ObservationResponse:
    row = db.execute(
        select(FinalObservation).where(
            FinalObservation.id == observation_id,
            FinalObservation.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found.")
    return _response(row)
