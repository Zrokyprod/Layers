import json
from collections.abc import Iterable

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.provisioning import (
    require_owner_provisioning_access as require_provisioning_access,
)
from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.models import FeatureFlag
from app.db.session import get_db_session
from app.schemas.feature_flags import (
    FeatureFlagCreateRequest,
    FeatureFlagListResponse,
    FeatureFlagResponse,
    FeatureFlagUpdateRequest,
    TenantFeatureFlagsResponse,
)
from app.services.owner_audit import create_owner_audit_event, resolve_owner_actor

router = APIRouter(prefix="/v1/feature-flags")


def _loads_list(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return sorted({str(item).strip() for item in data if str(item).strip()})


def _dumps_list(values: Iterable[str]) -> str:
    clean = sorted({str(item).strip() for item in values if str(item).strip()})
    return json.dumps(clean, separators=(",", ":"))


def _get_flag_or_404(db: Session, flag_id: str) -> FeatureFlag:
    flag = db.get(FeatureFlag, flag_id)
    if flag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature flag not found.")
    return flag


def _response(flag: FeatureFlag) -> FeatureFlagResponse:
    return FeatureFlagResponse.from_orm(flag)


@router.get("/admin", response_model=FeatureFlagListResponse)
def list_feature_flags(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> FeatureFlagListResponse:
    rows = db.execute(select(FeatureFlag).order_by(FeatureFlag.key.asc())).scalars().all()
    return FeatureFlagListResponse(items=[_response(row) for row in rows])


@router.post("/admin", response_model=FeatureFlagResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def create_feature_flag(
    request: Request,
    body: FeatureFlagCreateRequest = Body(...),
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> FeatureFlagResponse:
    key = body.key.strip()
    existing = db.scalar(select(FeatureFlag).where(FeatureFlag.key == key))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Feature flag key already exists.")

    flag = FeatureFlag(
        key=key,
        description=body.description.strip() if body.description else None,
        enabled_globally=body.enabled_globally,
        enabled_tenants_json="[]",
        disabled_tenants_json="[]",
    )
    db.add(flag)
    db.flush()
    create_owner_audit_event(
        db,
        action="owner.feature_flag.create",
        actor=resolve_owner_actor(request),
        target_id=flag.id,
        metadata={"key": flag.key, "enabled_globally": flag.enabled_globally},
    )
    db.commit()
    db.refresh(flag)
    return _response(flag)


@router.put("/admin/{flag_id}", response_model=FeatureFlagResponse)
@limiter.limit("20/minute")
def update_feature_flag(
    request: Request,
    flag_id: str,
    body: FeatureFlagUpdateRequest = Body(...),
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> FeatureFlagResponse:
    flag = _get_flag_or_404(db, flag_id)
    before = {
        "description": flag.description,
        "enabled_globally": flag.enabled_globally,
        "enabled_tenants": _loads_list(flag.enabled_tenants_json),
        "disabled_tenants": _loads_list(flag.disabled_tenants_json),
    }

    if body.description is not None:
        flag.description = body.description.strip() or None
    if body.enabled_globally is not None:
        flag.enabled_globally = body.enabled_globally

    enabled = set(_loads_list(flag.enabled_tenants_json))
    disabled = set(_loads_list(flag.disabled_tenants_json))
    enabled.update(body.add_enabled_tenants)
    enabled.difference_update(body.remove_enabled_tenants)
    disabled.update(body.add_disabled_tenants)
    disabled.difference_update(body.remove_disabled_tenants)
    enabled.difference_update(enabled & disabled)

    flag.enabled_tenants_json = _dumps_list(enabled)
    flag.disabled_tenants_json = _dumps_list(disabled)

    db.add(flag)
    create_owner_audit_event(
        db,
        action="owner.feature_flag.update",
        actor=resolve_owner_actor(request),
        target_id=flag.id,
        metadata={
            "key": flag.key,
            "before": before,
            "after": {
                "description": flag.description,
                "enabled_globally": flag.enabled_globally,
                "enabled_tenants": _loads_list(flag.enabled_tenants_json),
                "disabled_tenants": _loads_list(flag.disabled_tenants_json),
            },
        },
    )
    db.commit()
    db.refresh(flag)
    return _response(flag)


@router.delete("/admin/{flag_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
@limiter.limit("10/minute")
def delete_feature_flag(
    request: Request,
    flag_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> Response:
    flag = _get_flag_or_404(db, flag_id)
    create_owner_audit_event(
        db,
        action="owner.feature_flag.delete",
        actor=resolve_owner_actor(request),
        target_id=flag.id,
        metadata={"key": flag.key},
    )
    db.delete(flag)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tenant", response_model=TenantFeatureFlagsResponse)
def get_tenant_feature_flags(
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> TenantFeatureFlagsResponse:
    rows = db.execute(select(FeatureFlag).order_by(FeatureFlag.key.asc())).scalars().all()
    flags: dict[str, bool] = {}
    for row in rows:
        enabled_tenants = set(_loads_list(row.enabled_tenants_json))
        disabled_tenants = set(_loads_list(row.disabled_tenants_json))
        enabled = bool(row.enabled_globally or tenant_id in enabled_tenants)
        if tenant_id in disabled_tenants:
            enabled = False
        flags[row.key] = enabled
    return TenantFeatureFlagsResponse(flags=flags)
