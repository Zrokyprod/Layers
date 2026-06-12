from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SubscriptionPlanResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None = None
    monthly_cost_usd: float
    annual_cost_usd: float
    max_projects: int
    max_members_per_project: int
    max_calls_per_month: int | None = None
    max_tokens_per_month: int | None = None
    features: list[str] = Field(default_factory=list)
    is_active: bool
    sort_order: int
    created_at: datetime

    @classmethod
    def from_orm(cls, obj: Any) -> "SubscriptionPlanResponse":
        import json

        features = []
        try:
            features = json.loads(obj.features_json or "[]")
        except Exception:
            pass
        return cls(
            id=obj.id,
            slug=obj.slug,
            name=obj.name,
            description=obj.description,
            monthly_cost_usd=float(obj.monthly_cost_usd),
            annual_cost_usd=float(obj.annual_cost_usd),
            max_projects=obj.max_projects,
            max_members_per_project=obj.max_members_per_project,
            max_calls_per_month=obj.max_calls_per_month,
            max_tokens_per_month=obj.max_tokens_per_month,
            features=features,
            is_active=obj.is_active,
            sort_order=obj.sort_order,
            created_at=obj.created_at,
        )


class SubscriptionPlanListResponse(BaseModel):
    plans: list[SubscriptionPlanResponse]


class TenantSubscriptionResponse(BaseModel):
    id: str
    tenant_id: str
    plan: SubscriptionPlanResponse
    billing_interval: str
    status: str
    trial_ends_at: datetime | None = None
    current_period_start: datetime
    current_period_end: datetime
    canceled_at: datetime | None = None
    seats: int
    metadata: dict[str, Any] | None = None
    created_at: datetime

    @classmethod
    def from_orm(cls, obj: Any) -> "TenantSubscriptionResponse":
        import json

        metadata = None
        try:
            metadata = json.loads(obj.metadata_json) if obj.metadata_json else None
        except Exception:
            pass
        plan = SubscriptionPlanResponse.from_orm(obj.plan)
        return cls(
            id=obj.id,
            tenant_id=obj.tenant_id,
            plan=plan,
            billing_interval=obj.billing_interval,
            status=obj.status,
            trial_ends_at=obj.trial_ends_at,
            current_period_start=obj.current_period_start,
            current_period_end=obj.current_period_end,
            canceled_at=obj.canceled_at,
            seats=obj.seats,
            metadata=metadata,
            created_at=obj.created_at,
        )


class TenantSubscriptionUpdateRequest(BaseModel):
    plan_id: str | None = None
    billing_interval: str | None = None
    status: str | None = None
    seats: int | None = None


class BillingUsageSummaryResponse(BaseModel):
    tenant_id: str
    period_start: datetime
    period_end: datetime
    total_calls: int
    total_tokens: int
    total_cost_usd: float
    plan_limit_calls: int | None = None
    plan_limit_tokens: int | None = None
    overage_calls: int | None = None
    overage_tokens: int | None = None


class BillingUsageMeter(BaseModel):
    used: int
    limit: int | None = None
    unlimited: bool = False
    overage: int | None = None
    state: str
    resets_at: str | None = None


class BillingMeteringHealthResponse(BaseModel):
    state: str
    failure_count: int = 0
    last_failure_at: datetime | None = None
    last_failure_type: str | None = None
    failure_policy: str
    detail: str | None = None


class BillingUsageResponse(BaseModel):
    tenant_id: str
    org_id: str
    period_month: str
    period_start: datetime
    period_end: datetime
    plan_code: str | None = None
    plan_name: str | None = None
    subscription_status: str | None = None
    calls: BillingUsageMeter
    replay: BillingUsageMeter
    goldens: BillingUsageMeter
    golden_sets: BillingUsageMeter
    metering_health: BillingMeteringHealthResponse
