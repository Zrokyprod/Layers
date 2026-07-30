from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import FinalSourceConnector
from app.db.session import get_db_session


router = APIRouter(prefix="/v1/source-connectors")


class SourceConnectorUpsertRequest(BaseModel):
    environment: str = Field(default="production", min_length=1, max_length=64)
    capability: str = Field(min_length=1, max_length=255)
    connector_kind: str = Field(min_length=1, max_length=32)
    secret_ref: str = Field(min_length=1, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="active")

    @field_validator("environment", "connector_kind", "status")
    @classmethod
    def _clean_lower(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("capability", "secret_ref")
    @classmethod
    def _clean(cls, value: str) -> str:
        return value.strip()


class SourceConnectorResponse(BaseModel):
    id: str
    project_id: str
    environment: str
    capability: str
    connector_kind: str
    secret_ref: str
    config: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class SourceConnectorListResponse(BaseModel):
    items: list[SourceConnectorResponse]


def _require_admin(context: TenantContext) -> None:
    if ROLE_RANK[context.role] < ROLE_RANK["admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required.")


def _response(row: FinalSourceConnector) -> SourceConnectorResponse:
    return SourceConnectorResponse(
        id=row.id,
        project_id=row.project_id,
        environment=row.environment,
        capability=row.capability,
        connector_kind=row.connector_kind,
        secret_ref=row.secret_ref,
        config=json.loads(row.config_json),
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=SourceConnectorResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def upsert_source_connector(
    request: Request,
    body: SourceConnectorUpsertRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> SourceConnectorResponse:
    _require_admin(context)
    if body.connector_kind != "stripe":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported connector kind.")
    if body.status not in {"active", "disabled"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported connector status.")
    existing = db.execute(
        select(FinalSourceConnector).where(
            FinalSourceConnector.project_id == context.tenant_id,
            FinalSourceConnector.environment == body.environment,
            FinalSourceConnector.capability == body.capability,
        )
    ).scalar_one_or_none()
    row = existing or FinalSourceConnector(
        project_id=context.tenant_id,
        environment=body.environment,
        capability=body.capability,
    )
    row.connector_kind = body.connector_kind
    row.secret_ref = body.secret_ref
    row.config_json = json.dumps(body.config, sort_keys=True, separators=(",", ":"))
    row.status = body.status
    db.add(row)
    db.commit()
    db.refresh(row)
    return _response(row)


@router.get("", response_model=SourceConnectorListResponse)
@limiter.limit("120/minute")
def list_source_connectors(
    request: Request,
    environment: str | None = None,
    capability: str | None = None,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> SourceConnectorListResponse:
    _require_admin(context)
    query = select(FinalSourceConnector).where(FinalSourceConnector.project_id == context.tenant_id)
    if environment:
        query = query.where(FinalSourceConnector.environment == environment.strip().lower())
    if capability:
        query = query.where(FinalSourceConnector.capability == capability.strip())
    rows = db.execute(query.order_by(FinalSourceConnector.created_at.desc())).scalars()
    return SourceConnectorListResponse(items=[_response(row) for row in rows])
