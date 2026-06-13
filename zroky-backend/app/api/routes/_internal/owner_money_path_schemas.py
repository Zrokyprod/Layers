from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OwnerReplayQuotaStatus(BaseModel):
    state: str
    enabled: bool
    used: int
    limit: int
    resets_at: str


class OwnerProviderKeyStatus(BaseModel):
    state: str
    active_provider_count: int


class OwnerCaptureDurabilityStatus(BaseModel):
    state: str
    gateway_count: int
    unhealthy_gateway_count: int
    spool_backlog: int
    spool_oldest_age_seconds: float
    loss_count: int
    backpressure_rejections: int


class OwnerPricingCostStatus(BaseModel):
    state: str
    pricing_version: str | None = None
    pricing_source: str | None = None
    pricing_age_days: int | None = None
    cost_confidence: str | None = None
    detail: str | None = None


class OwnerBillingStatus(BaseModel):
    state: str
    plan_code: str
    subscription_status: str | None = None
    current_period_end: datetime | None = None


class OwnerEventMeteringStatus(BaseModel):
    state: str
    used: int
    limit: int | None = None
    overage: int | None = None
    failure_count: int = 0
    last_failure_at: datetime | None = None


class OwnerBillingProviderVerification(BaseModel):
    state: str
    provider: str | None = None
    mode: str = "provider_event"
    checked_at: datetime | None = None
    provider_event_id: str | None = None
    detail: str | None = None


class OwnerSupportStatus(BaseModel):
    state: str
    open_count: int
    urgent_count: int


class OwnerLastDeployedSmoke(BaseModel):
    status: str
    checked_at: datetime | None = None
    project_id: str | None = None
    call_id: str | None = None
    golden_trace_id: str | None = None
    ci_run_id: str | None = None
    detail: str | None = None


class OwnerMoneyPathPlatformSummary(BaseModel):
    captures_24h: int
    issues_open: int
    replay_runs_7d: int
    verified_replay_runs_7d: int
    golden_traces_active: int
    ci_runs_7d: int
    ci_blocks_7d: int
    replay_jobs_pending: int = 0
    replay_jobs_stale: int = 0
    gateway_unhealthy_tenants: int = 0
    gateway_loss_tenants: int = 0
    gateway_backpressure_tenants: int = 0
    tenants_missing_provider_key: int
    tenants_near_replay_quota: int
    tenants_without_recent_capture: int
    tenants_without_goldens: int = 0
    tenants_with_failed_ci: int = 0
    tenants_with_stale_replay_workers: int = 0
    tenants_with_stale_pricing: int = 0
    tenants_with_quota_risk: int = 0
    tenants_with_billing_risk: int = 0
    metering_failure_tenants: int = 0
    event_counter_failure_count: int = 0
    billing_launch_blockers: list[str] = Field(default_factory=list)
    billing_provider_verification: OwnerBillingProviderVerification = Field(
        default_factory=lambda: OwnerBillingProviderVerification(
            state="unverified",
            detail="No applied billing provider event has been recorded.",
        )
    )
    support_tickets_open: int = 0
    support_tickets_urgent: int = 0
    blocked_regressions_7d: int = 0
    verified_fixes_7d: int = 0
    pricing_contract_drift: list[str] = Field(default_factory=list)
    launch_blockers: list[str] = Field(default_factory=list)
    last_deployed_smoke: OwnerLastDeployedSmoke


class OwnerMoneyPathTenantRow(BaseModel):
    project_id: str
    project_name: str
    plan_code: str
    last_capture_at: datetime | None
    captures_24h: int
    open_issue_count: int
    replay_run_count_7d: int
    verified_replay_count_7d: int
    golden_trace_count: int
    ci_run_count_7d: int
    blocking_ci_failures_7d: int
    replay_jobs_pending: int = 0
    replay_jobs_stale: int = 0
    capture_durability_status: OwnerCaptureDurabilityStatus
    provider_key_status: OwnerProviderKeyStatus
    replay_quota_status: OwnerReplayQuotaStatus
    event_metering_status: OwnerEventMeteringStatus
    pricing_cost_status: OwnerPricingCostStatus
    billing_status: OwnerBillingStatus
    support_status: OwnerSupportStatus
    blocked_regressions_7d: int = 0
    verified_fixes_7d: int = 0
    value_status: str
    money_path_breaks: list[str] = Field(default_factory=list)
    tenant_priority_score: int = 0
    launch_blockers: list[str] = Field(default_factory=list)
    next_owner_action: str


class OwnerMoneyPathHealthResponse(BaseModel):
    generated_at: datetime
    windows: dict[str, int]
    platform: OwnerMoneyPathPlatformSummary
    tenants: list[OwnerMoneyPathTenantRow]


class OwnerLaunchGateEvidence(BaseModel):
    label: str
    value: str | int | float | bool | None
    status: str | None = None
    detail: str | None = None


class OwnerLaunchReadinessGate(BaseModel):
    code: str
    title: str
    status: str
    summary: str
    blockers: list[str] = Field(default_factory=list)
    evidence: list[OwnerLaunchGateEvidence] = Field(default_factory=list)
    verification_commands: list[str] = Field(default_factory=list)


class OwnerLaunchReadinessResponse(BaseModel):
    generated_at: datetime
    product_standard: str
    overall_status: str
    paid_launch_allowed: bool
    gates: list[OwnerLaunchReadinessGate]
    hard_blockers: list[str] = Field(default_factory=list)
    verification_commands: list[str] = Field(default_factory=list)


__all__ = [
    "OwnerBillingProviderVerification",
    "OwnerBillingStatus",
    "OwnerCaptureDurabilityStatus",
    "OwnerEventMeteringStatus",
    "OwnerLastDeployedSmoke",
    "OwnerLaunchGateEvidence",
    "OwnerLaunchReadinessGate",
    "OwnerLaunchReadinessResponse",
    "OwnerMoneyPathHealthResponse",
    "OwnerMoneyPathPlatformSummary",
    "OwnerMoneyPathTenantRow",
    "OwnerPricingCostStatus",
    "OwnerProviderKeyStatus",
    "OwnerReplayQuotaStatus",
    "OwnerSupportStatus",
]
