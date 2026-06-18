from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.entitlements import require_entitlement
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import RegressionContractVersion
from app.db.session import get_db_session
from app.services.regression_contracts import (
    RegressionContractActivationError,
    RegressionContractConflict,
    activate_contract_version,
    create_contract,
    create_contract_version,
    get_contract,
    import_golden_contracts,
    json_object,
    list_contracts,
)


router = APIRouter(
    prefix="/v1/contracts",
    dependencies=[Depends(require_entitlement("pilot.goldens_basic"))],
)


class ContractCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    source_issue_id: str | None = Field(default=None, max_length=64)


class ContractVersionCreateRequest(BaseModel):
    spec_json: dict[str, Any]
    spec_version: str = Field(default="regression_contract_v1", max_length=64)
    fixture_set_id: str | None = Field(default=None, max_length=36)
    baseline_release_id: str | None = Field(default=None, max_length=36)
    trial_policy: dict[str, Any] | None = None
    evaluator_bundle_version: str = Field(default="default-v1", max_length=64)


class ContractVersionResponse(BaseModel):
    id: str
    contract_id: str
    version_number: int
    spec_version: str
    spec_json: dict[str, Any]
    fixture_set_id: str | None
    baseline_release_id: str | None
    trial_policy: dict[str, Any]
    evaluator_bundle_version: str
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime


class ContractResponse(BaseModel):
    id: str
    project_id: str
    source_issue_id: str | None
    name: str
    description: str | None
    severity: str
    status: str
    active_version_id: str | None
    owner_id: str | None
    created_at: datetime
    updated_at: datetime
    versions: list[ContractVersionResponse] = Field(default_factory=list)


class ImportGoldensResponse(BaseModel):
    imported_count: int
    versions: list[ContractVersionResponse]


def _version_response(row: RegressionContractVersion) -> ContractVersionResponse:
    return ContractVersionResponse(
        id=row.id,
        contract_id=row.contract_id,
        version_number=row.version_number,
        spec_version=row.spec_version,
        spec_json=json_object(row.spec_json),
        fixture_set_id=row.fixture_set_id,
        baseline_release_id=row.baseline_release_id,
        trial_policy=json_object(row.trial_policy_json),
        evaluator_bundle_version=row.evaluator_bundle_version,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
        created_at=row.created_at,
    )


def _contract_response(row, versions: list[RegressionContractVersion] | None = None) -> ContractResponse:
    return ContractResponse(
        id=row.id,
        project_id=row.project_id,
        source_issue_id=row.source_issue_id,
        name=row.name,
        description=row.description,
        severity=row.severity,
        status=row.status,
        active_version_id=row.active_version_id,
        owner_id=row.owner_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        versions=[_version_response(version) for version in versions or []],
    )


@router.get("", response_model=list[ContractResponse])
@limiter.limit("120/minute")
def list_contracts_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> list[ContractResponse]:
    rows = list_contracts(db, project_id=context.tenant_id, status=status_filter, limit=limit)
    version_rows = db.execute(
        select(RegressionContractVersion).where(
            RegressionContractVersion.project_id == context.tenant_id,
            RegressionContractVersion.contract_id.in_([row.id for row in rows] or [""]),
        )
    ).scalars().all()
    by_contract: dict[str, list[RegressionContractVersion]] = {}
    for version in version_rows:
        by_contract.setdefault(version.contract_id, []).append(version)
    return [_contract_response(row, by_contract.get(row.id)) for row in rows]


@router.post("", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def create_contract_route(
    request: Request,
    body: ContractCreateRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ContractResponse:
    try:
        row = create_contract(
            db,
            project_id=context.tenant_id,
            name=body.name,
            description=body.description,
            severity=body.severity,
            source_issue_id=body.source_issue_id,
            owner_id=context.subject,
        )
    except RegressionContractConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _contract_response(row)


@router.get("/{contract_id}", response_model=ContractResponse)
@limiter.limit("120/minute")
def get_contract_route(
    request: Request,
    contract_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ContractResponse:
    row = get_contract(db, project_id=context.tenant_id, contract_id=contract_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    versions = list(
        db.execute(
            select(RegressionContractVersion)
            .where(
                RegressionContractVersion.project_id == context.tenant_id,
                RegressionContractVersion.contract_id == contract_id,
            )
            .order_by(RegressionContractVersion.version_number.desc())
        ).scalars()
    )
    return _contract_response(row, versions)


@router.post("/{contract_id}/versions", response_model=ContractVersionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def create_version_route(
    request: Request,
    contract_id: str,
    body: ContractVersionCreateRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ContractVersionResponse:
    try:
        row = create_contract_version(
            db,
            project_id=context.tenant_id,
            contract_id=contract_id,
            spec_json=body.spec_json,
            spec_version=body.spec_version,
            fixture_set_id=body.fixture_set_id,
            baseline_release_id=body.baseline_release_id,
            trial_policy=body.trial_policy,
            evaluator_bundle_version=body.evaluator_bundle_version,
            created_by=context.subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return _version_response(row)


@router.post("/{contract_id}/versions/{version_id}/activate", response_model=ContractVersionResponse)
@limiter.limit("30/minute")
def activate_version_route(
    request: Request,
    contract_id: str,
    version_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ContractVersionResponse:
    if ROLE_RANK[context.role] < ROLE_RANK["admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin role is required.")
    try:
        row = activate_contract_version(
            db,
            project_id=context.tenant_id,
            contract_id=contract_id,
            version_id=version_id,
            approved_by=context.subject,
        )
    except RegressionContractActivationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "contract_activation_blocked", "blockers": exc.blockers},
        ) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract version not found")
    return _version_response(row)


@router.post("/import-goldens", response_model=ImportGoldensResponse)
@limiter.limit("30/minute")
def import_goldens_route(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ImportGoldensResponse:
    rows = import_golden_contracts(db, project_id=context.tenant_id, created_by=context.subject)
    return ImportGoldensResponse(imported_count=len(rows), versions=[_version_response(row) for row in rows])
