from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import FinalAgentRun, FinalWorkflowIntent
from app.db.session import get_db_session


RunStatus = Literal["declared", "running", "succeeded", "failed", "cancelled", "unknown"]

router = APIRouter(prefix="/v1/runs")


class AgentRunDeclareRequest(BaseModel):
    environment: str = Field(default="production", min_length=1, max_length=64)
    external_run_id: str | None = Field(default=None, max_length=255)
    intent_id: str | None = Field(default=None, max_length=36)
    workflow_key: str | None = Field(default=None, max_length=160)
    agent_ref: str | None = Field(default=None, max_length=255)
    status: RunStatus = "declared"
    run: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @field_validator("environment")
    @classmethod
    def _clean_environment(cls, value: str) -> str:
        return value.strip().lower()


class AgentRunResponse(BaseModel):
    id: str
    project_id: str
    environment: str
    idempotency_key: str
    external_run_id: str | None
    intent_id: str | None
    workflow_key: str | None
    agent_ref: str | None
    status: str
    run_digest: str
    run: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class AgentRunListResponse(BaseModel):
    items: list[AgentRunResponse]


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _response(row: FinalAgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=row.id,
        project_id=row.project_id,
        environment=row.environment,
        idempotency_key=row.idempotency_key,
        external_run_id=row.external_run_id,
        intent_id=row.intent_id,
        workflow_key=row.workflow_key,
        agent_ref=row.agent_ref,
        status=row.status,
        run_digest=row.run_digest,
        run=json.loads(row.run_json),
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
    )


@router.post("", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("120/minute")
def declare_run(
    request: Request,
    body: AgentRunDeclareRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> AgentRunResponse:
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key header is required.")

    if body.intent_id:
        intent = db.execute(
            select(FinalWorkflowIntent).where(
                FinalWorkflowIntent.id == body.intent_id,
                FinalWorkflowIntent.project_id == context.tenant_id,
            )
        ).scalar_one_or_none()
        if intent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trusted intent not found.")

    key = idempotency_key.strip()
    run_digest = _digest(body.run)
    existing = db.execute(
        select(FinalAgentRun).where(
            FinalAgentRun.project_id == context.tenant_id,
            FinalAgentRun.environment == body.environment,
            FinalAgentRun.idempotency_key == key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.run_digest != run_digest:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key conflicts with an existing run.")
        return _response(existing)

    row = FinalAgentRun(
        project_id=context.tenant_id,
        environment=body.environment,
        idempotency_key=key,
        external_run_id=body.external_run_id,
        intent_id=body.intent_id,
        workflow_key=body.workflow_key,
        agent_ref=body.agent_ref,
        status=body.status,
        run_digest=run_digest,
        run_json=json.dumps(body.run, sort_keys=True, separators=(",", ":")),
        started_at=body.started_at,
        finished_at=body.finished_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _response(row)


@router.get("", response_model=AgentRunListResponse)
@limiter.limit("120/minute")
def list_runs(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> AgentRunListResponse:
    rows = db.execute(
        select(FinalAgentRun)
        .where(FinalAgentRun.project_id == context.tenant_id)
        .order_by(FinalAgentRun.created_at.desc())
        .limit(50)
    ).scalars().all()
    return AgentRunListResponse(items=[_response(row) for row in rows])


@router.get("/{run_id}", response_model=AgentRunResponse)
@limiter.limit("120/minute")
def get_run(
    request: Request,
    run_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> AgentRunResponse:
    row = db.execute(
        select(FinalAgentRun).where(
            FinalAgentRun.id == run_id,
            FinalAgentRun.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return _response(row)
