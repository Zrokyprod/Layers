from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_project_role
from app.api.dependencies.provisioning import require_provisioning_access
from app.db.models import FeatureFlag
from app.db.session import get_db_session
from app.schemas.feature_flags import (
    FeatureFlagCreateRequest,
    FeatureFlagListResponse,
    FeatureFlagResponse,
    FeatureFlagUpdateRequest,
    TenantFeatureFlagsResponse,
)

router = APIRouter(prefix="/v1/feature-flags")


@router.get("/tenant", response_model=TenantFeatureFlagsResponse)
def get_tenant_feature_flags(
    tenant_id: str = Depends(require_project_role("viewer")),
    db: Session = Depends(get_db_session),
) -> TenantFeatureFlagsResponse:
    rows = db.execute(select(FeatureFlag)).scalars().all()
    flags: dict[str, bool] = {}
    for row in rows:
        enabled = row.enabled_globally
        try:
            enabled_tenants = json.loads(row.enabled_tenants_json or "[]")
            disabled_tenants = json.loads(row.disabled_tenants_json or "[]")
        except Exception:
            enabled_tenants = []
            disabled_tenants = []
        if tenant_id in enabled_tenants:
            enabled = True
        if tenant_id in disabled_tenants:
            enabled = False
        flags[row.key] = enabled
    return TenantFeatureFlagsResponse(flags=flags)


@router.get("/admin", response_model=FeatureFlagListResponse)
def list_feature_flags(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> FeatureFlagListResponse:
    rows = db.execute(select(FeatureFlag).order_by(FeatureFlag.key.asc())).scalars().all()
    return FeatureFlagListResponse(items=[FeatureFlagResponse.from_orm(r) for r in rows])


@router.post("/admin", response_model=FeatureFlagResponse, status_code=status.HTTP_201_CREATED)
def create_feature_flag(
    body: FeatureFlagCreateRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> FeatureFlagResponse:
    existing = db.execute(select(FeatureFlag).where(FeatureFlag.key == body.key)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Feature flag with key '{body.key}' already exists.",
        )
    flag = FeatureFlag(
        key=body.key,
        description=body.description,
        enabled_globally=body.enabled_globally,
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)
    return FeatureFlagResponse.from_orm(flag)


@router.put("/admin/{flag_id}", response_model=FeatureFlagResponse)
def update_feature_flag(
    flag_id: str,
    body: FeatureFlagUpdateRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> FeatureFlagResponse:
    flag = db.execute(select(FeatureFlag).where(FeatureFlag.id == flag_id)).scalar_one_or_none()
    if flag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature flag not found.")

    if body.description is not None:
        flag.description = body.description
    if body.enabled_globally is not None:
        flag.enabled_globally = body.enabled_globally

    def _modify_list(current_json: str, add: list[str], remove: list[str]) -> str:
        try:
            current = set(json.loads(current_json or "[]"))
        except Exception:
            current = set()
        current.update(add)
        current.difference_update(remove)
        return json.dumps(list(current))

    flag.enabled_tenants_json = _modify_list(
        flag.enabled_tenants_json, body.add_enabled_tenants, body.remove_enabled_tenants
    )
    flag.disabled_tenants_json = _modify_list(
        flag.disabled_tenants_json, body.add_disabled_tenants, body.remove_disabled_tenants
    )

    db.commit()
    db.refresh(flag)
    return FeatureFlagResponse.from_orm(flag)


@router.delete("/admin/{flag_id}", status_code=status.HTTP_200_OK)
def delete_feature_flag(
    flag_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> None:
    flag = db.execute(select(FeatureFlag).where(FeatureFlag.id == flag_id)).scalar_one_or_none()
    if flag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature flag not found.")
    db.delete(flag)
    db.commit()
