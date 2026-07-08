"""Always-on budget limit routes used by the billing UI."""

import calendar as _cal
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.db.models import Call, ProjectDashboardConfig
from app.db.session import get_db_session, get_db_session_read
from app.schemas.dashboard import (
    BudgetConfigResponse,
    BudgetConfigUpdateRequest,
    BudgetStatusResponse,
)
from app.services.dashboard_config import ensure_project_exists, get_or_create_dashboard_config
from app.services.dashboard_data import to_float, utc_now
from app.services.privacy import mask_error_message

router = APIRouter(prefix="/v1/analytics")


def _budget_config_response(config: ProjectDashboardConfig) -> BudgetConfigResponse:
    return BudgetConfigResponse(
        monthly_limit_usd=to_float(config.monthly_budget_usd, fallback=0.0)
        if config.monthly_budget_usd is not None
        else None,
        threshold_percentage=round(to_float(config.budget_threshold_percentage, fallback=80.0), 2),
        updated_at=config.updated_at,
    )


@router.get("/budget", response_model=BudgetConfigResponse)
def get_budget_config(
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> BudgetConfigResponse:
    try:
        ensure_project_exists(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=mask_error_message(exc),
        ) from exc

    config = get_or_create_dashboard_config(db, tenant_id)
    return _budget_config_response(config)


@router.put("/budget", response_model=BudgetConfigResponse)
def update_budget_config(
    body: BudgetConfigUpdateRequest,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> BudgetConfigResponse:
    try:
        ensure_project_exists(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=mask_error_message(exc),
        ) from exc

    config = get_or_create_dashboard_config(db, tenant_id)
    config.monthly_budget_usd = body.monthly_limit_usd
    config.budget_threshold_percentage = body.threshold_percentage
    db.add(config)
    db.commit()
    db.refresh(config)

    return _budget_config_response(config)


@router.get("/budget/status", response_model=BudgetStatusResponse)
def get_budget_status(
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> BudgetStatusResponse:
    now = utc_now()
    period_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    spent_usd = round(
        float(
            db.execute(
                select(func.coalesce(func.sum(Call.cost_total), 0.0)).where(
                    Call.project_id == tenant_id,
                    Call.created_at >= period_start,
                )
            ).scalar()
            or 0.0
        ),
        6,
    )

    config_row = db.execute(
        select(ProjectDashboardConfig).where(ProjectDashboardConfig.tenant_id == tenant_id)
    ).scalar_one_or_none()
    limit_usd: float | None = None
    threshold_pct = 80.0
    if config_row is not None:
        if config_row.monthly_budget_usd is not None:
            limit_usd = float(config_row.monthly_budget_usd)
        if config_row.budget_threshold_percentage is not None:
            threshold_pct = float(config_row.budget_threshold_percentage)

    days_in_month = _cal.monthrange(now.year, now.month)[1]
    days_remaining = max(0, days_in_month - now.day)

    percent_used: float | None = None
    budget_status: Literal["ok", "warning", "critical", "no_limit"]
    if limit_usd is not None and limit_usd > 0:
        percent_used = round((spent_usd / limit_usd) * 100.0, 2)
        if percent_used >= 100.0:
            budget_status = "critical"
        elif percent_used >= threshold_pct:
            budget_status = "warning"
        else:
            budget_status = "ok"
    else:
        budget_status = "no_limit"

    return BudgetStatusResponse(
        spent_usd=spent_usd,
        limit_usd=limit_usd,
        percent_used=percent_used,
        days_remaining_in_period=days_remaining,
        forecast_exhaust_in_days=None,
        status=budget_status,
        forecast_risk_level="normal",
        forecast_recommendation="Cost is within expected range.",
    )
