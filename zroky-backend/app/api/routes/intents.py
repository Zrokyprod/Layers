from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import FinalWorkflowIntent
from app.db.session import get_db_session


router = APIRouter(prefix="/v1/intents")


class TrustedIntentCreateRequest(BaseModel):
    environment: str = Field(default="production", min_length=1, max_length=64)
    agent_ref: str | None = Field(default=None, max_length=255)
    intent: dict[str, Any]

    @field_validator("environment")
    @classmethod
    def _clean_environment(cls, value: str) -> str:
        return value.strip().lower()


class TrustedIntentResponse(BaseModel):
    id: str
    project_id: str
    environment: str
    idempotency_key: str
    agent_ref: str | None
    intent_digest: str
    intent: dict[str, Any]
    status: str
    created_at: datetime


def _digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _response(row: FinalWorkflowIntent) -> TrustedIntentResponse:
    return TrustedIntentResponse(
        id=row.id,
        project_id=row.project_id,
        environment=row.environment,
        idempotency_key=row.idempotency_key,
        agent_ref=row.agent_ref,
        intent_digest=row.intent_digest,
        intent=json.loads(row.intent_json),
        status=row.status,
        created_at=row.created_at,
    )


@router.post("", response_model=TrustedIntentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("120/minute")
def create_trusted_intent(
    request: Request,
    body: TrustedIntentCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> TrustedIntentResponse:
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key header is required.")

    key = idempotency_key.strip()
    intent_digest = _digest(body.intent)
    existing = db.execute(
        select(FinalWorkflowIntent).where(
            FinalWorkflowIntent.project_id == context.tenant_id,
            FinalWorkflowIntent.environment == body.environment,
            FinalWorkflowIntent.idempotency_key == key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.intent_digest != intent_digest:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key conflicts with an existing trusted intent.")
        return _response(existing)

    row = FinalWorkflowIntent(
        project_id=context.tenant_id,
        environment=body.environment,
        idempotency_key=key,
        agent_ref=body.agent_ref.strip() if body.agent_ref else None,
        intent_digest=intent_digest,
        intent_json=json.dumps(body.intent, sort_keys=True, separators=(",", ":")),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _response(row)


@router.get("/{intent_id}", response_model=TrustedIntentResponse)
@limiter.limit("120/minute")
def get_trusted_intent(
    request: Request,
    intent_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> TrustedIntentResponse:
    row = db.execute(
        select(FinalWorkflowIntent).where(
            FinalWorkflowIntent.id == intent_id,
            FinalWorkflowIntent.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trusted intent not found.")
    return _response(row)
