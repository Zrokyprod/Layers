from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_project_role
from app.db.models import Call, SubscriptionPlan, TenantSubscription
from app.db.session import get_db_session
from app.schemas.billing import (
    BillingUsageSummaryResponse,
    SubscriptionPlanListResponse,
    SubscriptionPlanResponse,
    TenantSubscriptionResponse,
    TenantSubscriptionUpdateRequest,
)

router = APIRouter(prefix="/v1/billing")


def _get_or_create_subscription(
    db: Session, tenant_id: str
) -> TenantSubscription:
    """Return existing tenant subscription or create a free-tier one."""
    existing = db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if existing:
        return existing

    free_plan = db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.slug == "free").where(SubscriptionPlan.is_active.is_(True))
    ).scalar_one_or_none()
    if free_plan is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default free plan is not configured.",
        )

    now = datetime.now(timezone.utc)
    sub = TenantSubscription(
        tenant_id=tenant_id,
        plan_id=free_plan.id,
        billing_interval="monthly",
        status="active",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
        seats=1,
    )
    db.add(sub)
    try:
        db.commit()
        db.refresh(sub)
    except IntegrityError:
        db.rollback()
        sub = db.execute(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
        ).scalar_one()
    return sub


@router.get("/plans", response_model=SubscriptionPlanListResponse)
def list_plans(
    db: Session = Depends(get_db_session),
) -> SubscriptionPlanListResponse:
    rows = db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.is_active.is_(True))
        .order_by(SubscriptionPlan.sort_order.asc())
    ).scalars().all()
    return SubscriptionPlanListResponse(
        plans=[SubscriptionPlanResponse.model_validate(r) for r in rows]
    )


@router.get("/subscription", response_model=TenantSubscriptionResponse)
def get_subscription(
    tenant_id: str = Depends(require_project_role("viewer")),
    db: Session = Depends(get_db_session),
) -> TenantSubscriptionResponse:
    sub = _get_or_create_subscription(db, tenant_id)
    return TenantSubscriptionResponse.model_validate(sub)


@router.put("/subscription", response_model=TenantSubscriptionResponse)
def update_subscription(
    body: TenantSubscriptionUpdateRequest,
    tenant_id: str = Depends(require_project_role("admin")),
    db: Session = Depends(get_db_session),
) -> TenantSubscriptionResponse:
    sub = _get_or_create_subscription(db, tenant_id)

    if body.plan_id is not None:
        plan = db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == body.plan_id).where(SubscriptionPlan.is_active.is_(True))
        ).scalar_one_or_none()
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or inactive plan selected.",
            )
        sub.plan_id = plan.id

    if body.billing_interval is not None:
        if body.billing_interval not in {"monthly", "annual"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="billing_interval must be 'monthly' or 'annual'.",
            )
        sub.billing_interval = body.billing_interval

    if body.status is not None:
        if body.status not in {"active", "canceled", "past_due", "trialing"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status value.",
            )
        sub.status = body.status
        if body.status == "canceled" and sub.canceled_at is None:
            sub.canceled_at = datetime.now(timezone.utc)

    if body.seats is not None:
        if body.seats < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="seats must be at least 1.",
            )
        sub.seats = body.seats

    db.commit()
    db.refresh(sub)
    return TenantSubscriptionResponse.model_validate(sub)


@router.get("/usage", response_model=BillingUsageSummaryResponse)
def get_usage_summary(
    tenant_id: str = Depends(require_project_role("viewer")),
    db: Session = Depends(get_db_session),
) -> BillingUsageSummaryResponse:
    sub = _get_or_create_subscription(db, tenant_id)
    period_start = sub.current_period_start
    period_end = sub.current_period_end

    result = db.execute(
        select(
            func.count(Call.id).label("total_calls"),
            func.coalesce(func.sum(Call.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(Call.cost_total), 0).label("total_cost"),
        )
        .where(Call.project_id == tenant_id)
        .where(Call.created_at >= period_start)
        .where(Call.created_at < period_end)
    ).one()

    total_calls = int(result.total_calls or 0)
    total_tokens = int(result.total_tokens or 0)
    total_cost = float(result.total_cost or 0)

    plan_limit_calls = sub.plan.max_calls_per_month
    plan_limit_tokens = sub.plan.max_tokens_per_month

    overage_calls = None
    overage_tokens = None
    if plan_limit_calls is not None and total_calls > plan_limit_calls:
        overage_calls = total_calls - plan_limit_calls
    if plan_limit_tokens is not None and total_tokens > plan_limit_tokens:
        overage_tokens = total_tokens - plan_limit_tokens

    return BillingUsageSummaryResponse(
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=period_end,
        total_calls=total_calls,
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        plan_limit_calls=plan_limit_calls,
        plan_limit_tokens=plan_limit_tokens,
        overage_calls=overage_calls,
        overage_tokens=overage_tokens,
    )
