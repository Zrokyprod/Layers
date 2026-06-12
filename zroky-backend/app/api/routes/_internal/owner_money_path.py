from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.routes._internal.owner_common import (
    get_db_session,
    require_provisioning_access,
    router,
)
from app.api.routes._internal.owner_pricing_audit import _pricing_contract_drift
from app.db.models import (
    Anomaly,
    Call,
    BillingEvent,
    EventCount,
    GatewayCaptureHealth,
    GoldenSet,
    GoldenTrace,
    Issue,
    Project,
    ProviderKeyVault,
    ReplayJob,
    ReplayRun,
    RuntimePolicyDecision,
    Subscription,
    SupportTicket,
)
from app.services.entitlement_catalog import (
    DEFAULT_PLAN_CODE,
    UNLIMITED,
    InvalidPlanCodeError,
    get_catalog_entry,
    load_pricing_contract,
)
from app.services.billing_metering import count_open_metering_failures


OPEN_ISSUE_STATUSES = ("open", "acknowledged")
BLOCKING_CI_STATUSES = ("fail", "error")
VERIFIED_REPLAY_STATUSES = {"verified_fix", "real_replay_passed"}
OPEN_SUPPORT_STATUSES = ("open", "pending", "waiting", "in_progress")
URGENT_SUPPORT_PRIORITIES = ("high", "urgent")
BILLING_RISK_STATUSES = {"past_due", "canceled", "unpaid", "incomplete"}
PRICING_STALE_AFTER_DAYS = 30
PRODUCT_STANDARD = "Did Zroky prevent an important AI agent failure from silently repeating?"
FINAL_READINESS_COMMANDS = [
    "powershell -ExecutionPolicy Bypass -File scripts/verify_paid_launch_readiness.ps1",
    "python scripts/run_money_path_demo.py --json",
    "python -m pytest tests/test_tenant_session_project_selection.py tests/test_tenant_project_route_scoping.py tests/test_ingest.py tests/test_failure_intelligence.py tests/test_replay_runs.py tests/test_replay_worker_claiming.py tests/test_goldens.py tests/test_regression_ci_routes.py tests/test_runtime_policy_gate.py tests/test_billing_v2.py tests/test_owner_money_path_health.py",
    "npm test -- --run src/app/owner/launch-readiness/page.test.tsx src/app/owner/page.test.tsx src/app/owner/money-path/page.test.tsx",
    "go test ./...",
    "python -m pytest",
    "npm test",
    "python scripts/check_docs_drift.py",
]
STALE_PRODUCT_DOC_PATHS = (
    ".devin/workflows/replay.md",
    ".kiro/specs/replay-worker-real-llm-execution/bugfix.md",
    ".kiro/specs/unknown-failure-discovery/design.md",
    ".kiro/specs/unknown-failure-discovery/requirements.md",
    ".kiro/specs/unknown-failure-discovery/tasks.md",
)


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


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _count_map(rows: list[tuple[str, int]]) -> dict[str, int]:
    return {project_id: int(count or 0) for project_id, count in rows}


def _month_window(now: datetime) -> tuple[datetime, str]:
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    return month_start, next_month.date().isoformat()


def _plan_contract(plan_code: str | None) -> tuple[str, bool, int]:
    selected = plan_code or DEFAULT_PLAN_CODE
    try:
        entry = get_catalog_entry(selected)
    except InvalidPlanCodeError:
        return selected, False, 0
    enabled = bool(entry.compatibility.get("pilot.autopilot_enabled"))
    limit = int(entry.compatibility.get("replay.monthly_runs") or 0)
    return entry.plan_code, enabled, limit


def _plan_event_limit(plan_code: str | None) -> int | None:
    selected = plan_code or DEFAULT_PLAN_CODE
    try:
        entry = get_catalog_entry(selected)
    except InvalidPlanCodeError:
        return 0
    limit = int(entry.compatibility.get("events.monthly_quota") or 0)
    return None if limit == UNLIMITED else limit


def _quota_status(
    *,
    enabled: bool,
    used: int,
    limit: int,
    resets_at: str,
) -> OwnerReplayQuotaStatus:
    if not enabled:
        state = "disabled"
    elif limit == UNLIMITED:
        state = "unlimited"
    elif limit <= 0:
        state = "blocked"
    elif used >= limit:
        state = "exceeded"
    elif used / limit >= 0.8:
        state = "near_limit"
    else:
        state = "ok"
    return OwnerReplayQuotaStatus(
        state=state,
        enabled=enabled,
        used=used,
        limit=limit,
        resets_at=resets_at,
    )


def _event_metering_status(
    *,
    used: int,
    limit: int | None,
    failure_count: int,
    last_failure_at: datetime | None,
) -> OwnerEventMeteringStatus:
    if failure_count > 0:
        state = "failure"
    elif limit is None or limit == UNLIMITED:
        state = "unlimited"
    elif limit <= 0:
        state = "blocked"
    elif used >= limit:
        state = "exceeded"
    elif used / limit >= 0.8:
        state = "near_limit"
    else:
        state = "ok"
    overage = None
    if limit is not None and limit >= 0 and used > limit:
        overage = used - limit
    return OwnerEventMeteringStatus(
        state=state,
        used=used,
        limit=None if limit == UNLIMITED else limit,
        overage=overage,
        failure_count=failure_count,
        last_failure_at=last_failure_at,
    )


def _billing_provider_verification(db: Session) -> OwnerBillingProviderVerification:
    latest = db.scalar(
        select(BillingEvent)
        .where(
            BillingEvent.provider.in_(("skydo", "razorpay")),
            BillingEvent.event_type.in_(("payment.succeeded", "payment_request.created")),
        )
        .order_by(func.coalesce(BillingEvent.processed_at, BillingEvent.received_at).desc())
        .limit(1)
    )
    if latest is None:
        return OwnerBillingProviderVerification(
            state="unverified",
            detail="No Skydo or Razorpay billing event has been recorded.",
        )
    checked_at = _as_utc(latest.processed_at) or _as_utc(latest.received_at)
    if latest.result == "applied":
        state = "verified"
        detail = f"{latest.provider} {latest.event_type} was applied."
    elif latest.result == "failed":
        state = "failed"
        detail = latest.error_message or f"{latest.provider} {latest.event_type} failed."
    else:
        state = "pending"
        detail = f"{latest.provider} {latest.event_type} is {latest.result}."
    return OwnerBillingProviderVerification(
        state=state,
        provider=latest.provider,
        checked_at=checked_at,
        provider_event_id=latest.provider_event_id,
        detail=detail,
    )


def _capture_durability_status(rows: list[GatewayCaptureHealth], now: datetime) -> OwnerCaptureDurabilityStatus:
    if not rows:
        return OwnerCaptureDurabilityStatus(
            state="unknown",
            gateway_count=0,
            unhealthy_gateway_count=0,
            spool_backlog=0,
            spool_oldest_age_seconds=0,
            loss_count=0,
            backpressure_rejections=0,
        )

    state_rank = {"ok": 0, "unknown": 1, "degraded": 2, "backpressure": 3, "loss_detected": 4}
    worst = "ok"
    unhealthy = 0
    spool_backlog = 0
    oldest_age = 0.0
    loss_count = 0
    backpressure_rejections = 0
    for row in rows:
        status_value = row.capture_status or "unknown"
        heartbeat_at = _as_utc(row.heartbeat_at)
        if heartbeat_at is None or (now - heartbeat_at).total_seconds() > 120:
            status_value = "degraded"
        if status_value != "ok":
            unhealthy += 1
        if state_rank.get(status_value, 1) > state_rank.get(worst, 1):
            worst = status_value
        spool_backlog += int(row.spool_backlog or 0)
        oldest_age = max(oldest_age, float(row.spool_oldest_age_seconds or 0))
        loss_count += int(row.loss_count or 0)
        backpressure_rejections += int(row.backpressure_rejections or 0)

    if loss_count > 0:
        worst = "loss_detected"
    elif backpressure_rejections > 0 and state_rank.get(worst, 0) < state_rank["backpressure"]:
        worst = "backpressure"

    return OwnerCaptureDurabilityStatus(
        state=worst,
        gateway_count=len(rows),
        unhealthy_gateway_count=unhealthy,
        spool_backlog=spool_backlog,
        spool_oldest_age_seconds=oldest_age,
        loss_count=loss_count,
        backpressure_rejections=backpressure_rejections,
    )


def _pricing_age_days(value: datetime | None, *, now: datetime) -> int | None:
    last_updated_at = _as_utc(value)
    if last_updated_at is None:
        return None
    return max(0, int((now - last_updated_at).total_seconds() // (24 * 60 * 60)))


def _pricing_cost_status(
    latest_call: Call | None,
    *,
    pricing_contract_drift: list[str],
    now: datetime,
) -> OwnerPricingCostStatus:
    if pricing_contract_drift:
        return OwnerPricingCostStatus(
            state="drift",
            detail="Pricing plan contract drift was reported by the backend.",
        )
    if latest_call is None:
        return OwnerPricingCostStatus(
            state="missing",
            detail="No captured calls are available to verify pricing metadata.",
        )

    age_days = _pricing_age_days(latest_call.pricing_last_updated_at, now=now)
    version = latest_call.pricing_version
    source = latest_call.pricing_source
    confidence = latest_call.cost_confidence
    base = {
        "pricing_version": version,
        "pricing_source": source,
        "pricing_age_days": age_days,
        "cost_confidence": confidence,
    }

    if not version or latest_call.pricing_last_updated_at is None:
        return OwnerPricingCostStatus(
            state="missing",
            detail="Latest capture is missing pricing version or timestamp.",
            **base,
        )
    if source == "fallback_default":
        return OwnerPricingCostStatus(
            state="fallback",
            detail="Latest capture used fallback pricing defaults.",
            **base,
        )
    if confidence == "stale" or (age_days is not None and age_days > PRICING_STALE_AFTER_DAYS):
        return OwnerPricingCostStatus(
            state="stale",
            detail=f"Latest pricing metadata is older than {PRICING_STALE_AFTER_DAYS} days.",
            **base,
        )
    if confidence == "degraded":
        return OwnerPricingCostStatus(
            state="degraded",
            detail="Latest capture has degraded cost confidence.",
            **base,
        )
    return OwnerPricingCostStatus(
        state="ok",
        detail="Latest capture has current pricing metadata.",
        **base,
    )


def _billing_status(subscription: Subscription | None, *, plan_code: str) -> OwnerBillingStatus:
    if subscription is None:
        state = "free_default" if plan_code == DEFAULT_PLAN_CODE else "missing_paid"
        return OwnerBillingStatus(
            state=state,
            plan_code=plan_code,
            subscription_status=None,
            current_period_end=None,
        )

    subscription_status = subscription.status or "unknown"
    if subscription_status in {"active", "trialing"}:
        state = "ok"
    elif subscription_status in BILLING_RISK_STATUSES:
        state = "risk"
    else:
        state = "unknown"
    return OwnerBillingStatus(
        state=state,
        plan_code=subscription.plan_code or plan_code,
        subscription_status=subscription_status,
        current_period_end=_as_utc(subscription.current_period_end),
    )


def _support_status(*, open_count: int, urgent_count: int) -> OwnerSupportStatus:
    if urgent_count > 0:
        state = "urgent"
    elif open_count > 0:
        state = "open"
    else:
        state = "none"
    return OwnerSupportStatus(state=state, open_count=open_count, urgent_count=urgent_count)


def _is_verified_replay(run: ReplayRun) -> bool:
    if run.status != "pass":
        return False
    summary = _json_object(run.summary_json)
    return (
        summary.get("verified_fix") is True
        or str(summary.get("verification_status") or "") in VERIFIED_REPLAY_STATUSES
    )


def _next_owner_action(
    *,
    last_capture_at: datetime | None,
    since_recent_capture: datetime,
    open_issue_count: int,
    replay_run_count_7d: int,
    verified_replay_count_7d: int,
    golden_trace_count: int,
    ci_run_count_7d: int,
    blocking_ci_failures_7d: int,
    replay_jobs_stale: int,
    capture_durability_status: OwnerCaptureDurabilityStatus,
    provider_key_status: OwnerProviderKeyStatus,
    replay_quota_status: OwnerReplayQuotaStatus,
    event_metering_status: OwnerEventMeteringStatus,
    pricing_cost_status: OwnerPricingCostStatus,
    billing_status: OwnerBillingStatus,
    support_status: OwnerSupportStatus,
) -> str:
    if blocking_ci_failures_7d > 0:
        return "review_blocked_ci"
    if capture_durability_status.state in {"loss_detected", "backpressure", "degraded"}:
        return "restore_capture"
    if last_capture_at is None or last_capture_at < since_recent_capture:
        return "restore_capture"
    if replay_jobs_stale > 0:
        return "restore_replay_worker"
    if billing_status.state in {"risk", "missing_paid", "unknown"}:
        return "fix_billing"
    if event_metering_status.state == "failure":
        return "fix_metering"
    if provider_key_status.state == "missing":
        return "connect_provider_key"
    if event_metering_status.state in {"exceeded", "near_limit", "blocked"}:
        return "review_event_quota"
    if replay_quota_status.state in {"exceeded", "near_limit"}:
        return "review_replay_quota"
    if support_status.state in {"urgent", "open"}:
        return "review_support"
    if open_issue_count > 0 and replay_run_count_7d == 0:
        return "run_replay"
    if golden_trace_count == 0 and verified_replay_count_7d > 0:
        return "promote_golden"
    if golden_trace_count > 0 and ci_run_count_7d == 0:
        return "run_ci_gate"
    if pricing_cost_status.state in {"drift", "missing", "fallback", "stale", "degraded"}:
        return "refresh_pricing"
    if open_issue_count > 0:
        return "continue_triage"
    return "monitor"


def _risk_score(row: OwnerMoneyPathTenantRow) -> int:
    score = 0
    if row.blocking_ci_failures_7d:
        score += 100 + min(row.blocking_ci_failures_7d, 20)
    if row.open_issue_count:
        score += 60 + min(row.open_issue_count, 40)
    if row.provider_key_status.state == "missing":
        score += 30
    if row.last_capture_at is None:
        score += 25
    if row.capture_durability_status.state == "loss_detected":
        score += 80
    elif row.capture_durability_status.state == "backpressure":
        score += 55
    elif row.capture_durability_status.state == "degraded":
        score += 25
    if row.replay_quota_status.state == "exceeded":
        score += 20
    elif row.replay_quota_status.state == "near_limit":
        score += 12
    if row.event_metering_status.state == "failure":
        score += 45 + min(row.event_metering_status.failure_count, 20)
    elif row.event_metering_status.state == "exceeded":
        score += 25
    elif row.event_metering_status.state == "near_limit":
        score += 12
    if row.replay_jobs_stale:
        score += 35 + min(row.replay_jobs_stale, 20)
    if row.golden_trace_count == 0:
        score += 18
    if row.pricing_cost_status.state in {"drift", "missing", "fallback", "stale"}:
        score += 16
    elif row.pricing_cost_status.state == "degraded":
        score += 8
    if row.billing_status.state in {"risk", "missing_paid", "unknown"}:
        score += 25
    if row.support_status.state == "urgent":
        score += 30
    elif row.support_status.state == "open":
        score += 10
    return score


def _pricing_drift() -> list[str]:
    try:
        return _pricing_contract_drift(load_pricing_contract())
    except Exception:  # noqa: BLE001
        return ["pricing_contract_unreadable"]


def _tenant_launch_blockers(
    *,
    last_capture_at: datetime | None,
    since_recent_capture: datetime,
    open_issue_count: int,
    replay_run_count_7d: int,
    verified_replay_count_7d: int,
    golden_trace_count: int,
    ci_run_count_7d: int,
    blocking_ci_failures_7d: int,
    replay_jobs_stale: int,
    capture_durability_status: OwnerCaptureDurabilityStatus,
    provider_key_status: OwnerProviderKeyStatus,
    replay_quota_status: OwnerReplayQuotaStatus,
    event_metering_status: OwnerEventMeteringStatus,
    pricing_cost_status: OwnerPricingCostStatus,
    billing_status: OwnerBillingStatus,
    support_status: OwnerSupportStatus,
) -> list[str]:
    blockers: list[str] = []
    if last_capture_at is None or last_capture_at < since_recent_capture:
        blockers.append("capture_unhealthy")
    if capture_durability_status.state == "loss_detected":
        blockers.append("capture_loss_detected")
    if capture_durability_status.state == "backpressure":
        blockers.append("gateway_backpressure")
    if capture_durability_status.state == "degraded" or capture_durability_status.spool_backlog > 0:
        blockers.append("gateway_spool_stale")
    if provider_key_status.state == "missing":
        blockers.append("provider_key_missing")
    if replay_quota_status.state in {"blocked", "disabled", "exceeded"}:
        blockers.append(f"replay_quota_{replay_quota_status.state}")
    if event_metering_status.state == "failure":
        blockers.append("event_metering_failure")
    if event_metering_status.state in {"blocked", "exceeded"}:
        blockers.append(f"event_quota_{event_metering_status.state}")
    if replay_jobs_stale > 0:
        blockers.append("replay_worker_stale_jobs")
    if pricing_cost_status.state in {"drift", "missing", "fallback", "stale"}:
        blockers.append(f"pricing_cost_{pricing_cost_status.state}")
    if billing_status.state in {"risk", "missing_paid", "unknown"}:
        blockers.append("billing_risk")
    if support_status.state == "urgent":
        blockers.append("urgent_support_ticket")
    if blocking_ci_failures_7d > 0:
        blockers.append("ci_gate_blocking_failures")
    if open_issue_count > 0 and replay_run_count_7d == 0:
        blockers.append("open_failures_without_replay")
    if replay_run_count_7d > 0 and verified_replay_count_7d == 0:
        blockers.append("verified_replay_missing")
    if verified_replay_count_7d > 0 and golden_trace_count == 0:
        blockers.append("golden_coverage_missing")
    if golden_trace_count > 0 and ci_run_count_7d == 0:
        blockers.append("ci_gate_missing")
    return blockers


def _money_path_breaks(
    *,
    launch_blockers: list[str],
    golden_trace_count: int,
    blocking_ci_failures_7d: int,
    replay_jobs_pending: int,
    replay_jobs_stale: int,
    event_metering_status: OwnerEventMeteringStatus,
    pricing_cost_status: OwnerPricingCostStatus,
    billing_status: OwnerBillingStatus,
    support_status: OwnerSupportStatus,
) -> list[str]:
    breaks: list[str] = []
    for blocker in launch_blockers:
        if blocker not in breaks:
            breaks.append(blocker)
    if golden_trace_count == 0 and "goldens_missing" not in breaks:
        breaks.append("goldens_missing")
    if blocking_ci_failures_7d > 0 and "failed_ci" not in breaks:
        breaks.append("failed_ci")
    if replay_jobs_pending > 0 and "replay_worker_backlog" not in breaks:
        breaks.append("replay_worker_backlog")
    if replay_jobs_stale > 0 and "replay_worker_stale" not in breaks:
        breaks.append("replay_worker_stale")
    if event_metering_status.state == "failure" and "event_metering_failure" not in breaks:
        breaks.append("event_metering_failure")
    if event_metering_status.state in {"blocked", "exceeded"}:
        code = f"event_quota_{event_metering_status.state}"
        if code not in breaks:
            breaks.append(code)
    if pricing_cost_status.state in {"drift", "missing", "fallback", "stale", "degraded"}:
        code = f"pricing_cost_{pricing_cost_status.state}"
        if code not in breaks:
            breaks.append(code)
    if billing_status.state in {"risk", "missing_paid", "unknown"} and "billing_risk" not in breaks:
        breaks.append("billing_risk")
    if support_status.state in {"urgent", "open"}:
        code = f"support_{support_status.state}"
        if code not in breaks:
            breaks.append(code)
    return breaks


def _value_status(
    *,
    money_path_breaks: list[str],
    captures_24h: int,
    open_issue_count: int,
    replay_run_count_7d: int,
    verified_replay_count_7d: int,
    golden_trace_count: int,
    ci_run_count_7d: int,
) -> str:
    blocking_codes = {
        "capture_loss_detected",
        "gateway_backpressure",
        "replay_worker_stale_jobs",
        "replay_worker_stale",
        "event_metering_failure",
        "ci_gate_blocking_failures",
        "failed_ci",
        "billing_risk",
        "replay_quota_exceeded",
        "replay_quota_blocked",
        "event_quota_exceeded",
        "event_quota_blocked",
    }
    setup_codes = {
        "capture_unhealthy",
        "provider_key_missing",
        "goldens_missing",
        "ci_gate_missing",
    }
    if any(code in blocking_codes for code in money_path_breaks):
        return "blocked"
    if captures_24h > 0 and verified_replay_count_7d > 0 and golden_trace_count > 0 and ci_run_count_7d > 0:
        return "getting_value"
    if any(code in setup_codes for code in money_path_breaks):
        return "setup_missing"
    if captures_24h == 0 and open_issue_count == 0 and replay_run_count_7d == 0 and golden_trace_count == 0 and ci_run_count_7d == 0:
        return "inactive"
    if money_path_breaks:
        return "at_risk"
    return "getting_value"


def _last_deployed_smoke(db: Session) -> OwnerLastDeployedSmoke:
    smoke_call = db.scalar(
        select(Call)
        .where(
            or_(
                Call.agent_name == "deployment-smoke-agent",
                Call.metadata_json.like("%phase_8_deployment_smoke%"),
            )
        )
        .order_by(Call.created_at.desc())
        .limit(1)
    )
    if smoke_call is None:
        return OwnerLastDeployedSmoke(
            status="not_configured",
            detail="No deployed money-path smoke evidence was found in calls.",
        )

    golden_trace = db.scalar(
        select(GoldenTrace)
        .where(
            GoldenTrace.project_id == smoke_call.project_id,
            GoldenTrace.source_evidence_json.like("%deployment-smoke%"),
        )
        .order_by(GoldenTrace.created_at.desc())
        .limit(1)
    )
    ci_run = db.scalar(
        select(ReplayRun)
        .where(
            ReplayRun.project_id == smoke_call.project_id,
            ReplayRun.trigger == "github",
            ReplayRun.git_sha.like("deploy-smoke%"),
        )
        .order_by(ReplayRun.created_at.desc())
        .limit(1)
    )

    if ci_run is None:
        status = "partial"
        detail = "Deployment smoke call exists, but no deployed CI gate run was found."
    elif ci_run.status == "pass":
        status = "passed"
        detail = "Latest deployed smoke has a passing CI gate run."
    elif ci_run.status in {"pending", "running"}:
        status = "running"
        detail = "Latest deployed smoke CI gate run has not completed."
    else:
        status = "failed"
        detail = f"Latest deployed smoke CI gate run ended with status={ci_run.status}."

    return OwnerLastDeployedSmoke(
        status=status,
        checked_at=_as_utc(smoke_call.created_at),
        project_id=smoke_call.project_id,
        call_id=smoke_call.id,
        golden_trace_id=golden_trace.id if golden_trace is not None else None,
        ci_run_id=ci_run.id if ci_run is not None else None,
        detail=detail,
    )


def _evidence(
    label: str,
    value: str | int | float | bool | None,
    *,
    status: str | None = None,
    detail: str | None = None,
) -> OwnerLaunchGateEvidence:
    return OwnerLaunchGateEvidence(
        label=label,
        value=value,
        status=status,
        detail=detail,
    )


def _gate(
    *,
    code: str,
    title: str,
    status: str,
    summary: str,
    blockers: list[str] | None = None,
    evidence: list[OwnerLaunchGateEvidence] | None = None,
    verification_commands: list[str] | None = None,
) -> OwnerLaunchReadinessGate:
    return OwnerLaunchReadinessGate(
        code=code,
        title=title,
        status=status,
        summary=summary,
        blockers=blockers or [],
        evidence=evidence or [],
        verification_commands=verification_commands or [],
    )


def _status_for(*, blockers: list[str], missing: list[str]) -> str:
    if blockers:
        return "fail"
    if missing:
        return "not_verified"
    return "pass"


def _replay_trust_counts(
    db: Session,
    *,
    project_ids: list[str],
    since: datetime,
) -> dict[str, int]:
    counts = {
        "trusted_verified": 0,
        "stub_marked_verified": 0,
        "not_verified": 0,
        "errors": 0,
    }
    if not project_ids:
        return counts

    runs = db.execute(
        select(ReplayRun).where(
            ReplayRun.project_id.in_(project_ids),
            ReplayRun.created_at >= since,
        )
    ).scalars().all()
    for run in runs:
        summary = _json_object(run.summary_json)
        replay_mode = str(
            summary.get("requested_replay_mode")
            or summary.get("executor_replay_mode")
            or summary.get("replay_mode")
            or ""
        )
        verified = (
            summary.get("verified_fix") is True
            or str(summary.get("verification_status") or "") in VERIFIED_REPLAY_STATUSES
        )
        if run.status == "not_verified":
            counts["not_verified"] += 1
        if run.status == "error":
            counts["errors"] += 1
        if verified and replay_mode == "stub":
            counts["stub_marked_verified"] += 1
        elif verified:
            counts["trusted_verified"] += 1
    return counts


def _ci_run_counts(
    db: Session,
    *,
    project_ids: list[str],
    since: datetime,
) -> dict[str, int]:
    counts = {
        "total": 0,
        "pass": 0,
        "warn": 0,
        "fail": 0,
        "not_verified": 0,
        "error": 0,
    }
    if not project_ids:
        return counts
    rows = db.execute(
        select(ReplayRun.status, func.count(ReplayRun.id))
        .where(
            ReplayRun.project_id.in_(project_ids),
            ReplayRun.trigger == "github",
            ReplayRun.created_at >= since,
        )
        .group_by(ReplayRun.status)
    ).all()
    for status, count in rows:
        key = str(status or "unknown")
        if key in counts:
            counts[key] = int(count or 0)
        counts["total"] += int(count or 0)
    return counts


def _behavioral_golden_counts(
    db: Session,
    *,
    project_ids: list[str],
) -> dict[str, int]:
    counts = {
        "active": 0,
        "blocking": 0,
        "blocking_behavioral": 0,
        "blocking_text_only": 0,
    }
    if not project_ids:
        return counts
    rows = db.execute(
        select(GoldenTrace, GoldenSet)
        .join(GoldenSet, GoldenTrace.golden_set_id == GoldenSet.id)
        .where(
            GoldenTrace.project_id.in_(project_ids),
            GoldenTrace.status == "active",
        )
    ).all()
    for trace, golden_set in rows:
        counts["active"] += 1
        if not bool(golden_set.blocks_ci) or bool(golden_set.is_flaky):
            continue
        counts["blocking"] += 1
        criteria = _json_object(trace.criteria_json)
        contract = criteria.get("golden_contract_v1")
        if isinstance(contract, dict) and contract:
            counts["blocking_behavioral"] += 1
        else:
            counts["blocking_text_only"] += 1
    return counts


def _runtime_policy_counts(
    db: Session,
    *,
    project_ids: list[str],
    since: datetime,
) -> dict[str, int]:
    counts = {
        "blocked": 0,
        "pending_approval": 0,
        "approved": 0,
        "rejected": 0,
        "risk_stopped": 0,
    }
    if not project_ids:
        return counts
    rows = db.execute(
        select(RuntimePolicyDecision).where(
            RuntimePolicyDecision.project_id.in_(project_ids),
            RuntimePolicyDecision.created_at >= since,
        )
    ).scalars().all()
    for row in rows:
        if row.status in counts:
            counts[row.status] += 1
        if row.decision in {"block", "requires_approval"} or row.status in {
            "blocked",
            "pending_approval",
            "approved",
            "rejected",
        }:
            counts["risk_stopped"] += 1
    return counts


def _repo_root_for_source_truth() -> Path | None:
    candidates = [
        Path.cwd(),
        Path.cwd().parent,
        Path(__file__).resolve().parents[5],
    ]
    for candidate in candidates:
        if (candidate / "README.md").exists() and (candidate / "zroky-backend").exists():
            return candidate
    return None


def _source_truth_status() -> tuple[str, list[str], list[OwnerLaunchGateEvidence]]:
    root = _repo_root_for_source_truth()
    if root is None:
        return (
            "not_verified",
            ["repo_root_not_found"],
            [
                _evidence(
                    "README marker",
                    "missing",
                    status="not_verified",
                    detail="Backend could not locate the repository root to verify product source of truth.",
                )
            ],
        )

    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8", errors="replace")
    has_marker = "single product and implementation source of truth" in text
    stale_docs = [
        rel
        for rel in STALE_PRODUCT_DOC_PATHS
        if (root / rel).exists()
    ]
    evidence = [
        _evidence("README.md", "present", status="pass" if has_marker else "not_verified"),
        _evidence("stale planning docs", len(stale_docs), status="fail" if stale_docs else "pass"),
    ]
    if stale_docs:
        return "fail", [f"stale_doc:{rel}" for rel in stale_docs], evidence
    if not has_marker:
        return "not_verified", ["readme_source_marker_missing"], evidence
    return "pass", [], evidence


def _build_launch_readiness(
    db: Session,
    *,
    money_path: OwnerMoneyPathHealthResponse,
) -> OwnerLaunchReadinessResponse:
    now = datetime.now(UTC)
    since_7d = now - timedelta(days=7)
    platform = money_path.platform
    tenants = money_path.tenants
    project_ids = [row.project_id for row in tenants]

    replay_counts = _replay_trust_counts(db, project_ids=project_ids, since=since_7d)
    ci_counts = _ci_run_counts(db, project_ids=project_ids, since=since_7d)
    golden_counts = _behavioral_golden_counts(db, project_ids=project_ids)
    runtime_counts = _runtime_policy_counts(db, project_ids=project_ids, since=since_7d)
    source_status, source_blockers, source_evidence = _source_truth_status()

    gates: list[OwnerLaunchReadinessGate] = []

    capture_blockers = [
        code
        for code in platform.launch_blockers
        if code
        in {
            "capture_loss_detected",
            "gateway_backpressure",
            "gateway_spool_stale",
        }
    ]
    capture_missing = []
    if platform.captures_24h <= 0:
        capture_missing.append("no_capture_24h")
    if platform.tenants_without_recent_capture > 0:
        capture_missing.append("tenant_capture_gap")
    gates.append(
        _gate(
            code="durable_capture",
            title="Durable Capture",
            status=_status_for(blockers=capture_blockers, missing=capture_missing),
            summary="SDK, gateway, and direct ingest must preserve masked production events with visible loss/backpressure.",
            blockers=capture_blockers + capture_missing,
            evidence=[
                _evidence("captures_24h", platform.captures_24h),
                _evidence("tenants_without_recent_capture", platform.tenants_without_recent_capture),
                _evidence("gateway_unhealthy_tenants", platform.gateway_unhealthy_tenants),
                _evidence("gateway_loss_tenants", platform.gateway_loss_tenants),
                _evidence("gateway_backpressure_tenants", platform.gateway_backpressure_tenants),
            ],
            verification_commands=[
                "python -m pytest tests/test_ingest.py tests/test_capture_health.py",
                "go test ./...",
            ],
        )
    )

    duplicate_project_ids = len(set(project_ids)) != len(project_ids)
    tenant_missing = [] if tenants else ["no_active_tenants"]
    tenant_blockers = ["duplicate_tenant_rows"] if duplicate_project_ids else []
    gates.append(
        _gate(
            code="tenant_isolation",
            title="Tenant Isolation",
            status=_status_for(blockers=tenant_blockers, missing=tenant_missing),
            summary="Every tenant-scoped flow must use the selected project and reject cross-project access.",
            blockers=tenant_blockers + tenant_missing,
            evidence=[
                _evidence("tenant_rows", len(tenants)),
                _evidence("unique_project_rows", len(set(project_ids))),
                _evidence("money_path_scoped_rows", bool(tenants)),
            ],
            verification_commands=[
                "python -m pytest tests/test_tenant_session_project_selection.py tests/test_tenant_project_route_scoping.py",
            ],
        )
    )

    failure_missing = []
    if platform.issues_open <= 0:
        failure_missing.append("no_grouped_failures")
    gates.append(
        _gate(
            code="failure_intelligence",
            title="Failure Intelligence",
            status=_status_for(blockers=[], missing=failure_missing),
            summary="Production failures must group into actionable issues with root cause, blast radius, next action, and proof status.",
            blockers=failure_missing,
            evidence=[
                _evidence("open_grouped_failures", platform.issues_open),
                _evidence("tenants_with_failures", sum(1 for row in tenants if row.open_issue_count > 0)),
            ],
            verification_commands=[
                "python -m pytest tests/test_failure_intelligence.py tests/test_issues.py",
            ],
        )
    )

    replay_blockers: list[str] = []
    if replay_counts["stub_marked_verified"] > 0:
        replay_blockers.append("stub_replay_marked_verified")
    if platform.replay_jobs_stale > 0:
        replay_blockers.append("replay_worker_stale_jobs")
    if replay_counts["errors"] > 0:
        replay_blockers.append("replay_executor_errors")
    replay_missing = []
    if replay_counts["trusted_verified"] <= 0:
        replay_missing.append("trusted_replay_proof_missing")
    if replay_counts["not_verified"] > 0:
        replay_missing.append("recent_replay_not_verified")
    gates.append(
        _gate(
            code="honest_replay_proof",
            title="Honest Replay Proof",
            status=_status_for(blockers=replay_blockers, missing=replay_missing),
            summary="Replay must report pass/fail/not_verified/error honestly; stub replay can never be trusted proof.",
            blockers=replay_blockers + replay_missing,
            evidence=[
                _evidence("trusted_verified_replays_7d", replay_counts["trusted_verified"]),
                _evidence("stub_marked_verified", replay_counts["stub_marked_verified"]),
                _evidence("not_verified_replays_7d", replay_counts["not_verified"]),
                _evidence("replay_errors_7d", replay_counts["errors"]),
                _evidence("stale_replay_jobs", platform.replay_jobs_stale),
            ],
            verification_commands=[
                "python -m pytest tests/test_replay_runs.py tests/test_replay_executor.py tests/test_replay_worker_claiming.py",
                "python -m pytest",
            ],
        )
    )

    golden_blockers = []
    if golden_counts["blocking_text_only"] > 0:
        golden_blockers.append("blocking_text_only_goldens")
    golden_missing = []
    if golden_counts["blocking_behavioral"] <= 0:
        golden_missing.append("behavioral_blocking_goldens_missing")
    gates.append(
        _gate(
            code="behavioral_goldens",
            title="Behavioral Goldens",
            status=_status_for(blockers=golden_blockers, missing=golden_missing),
            summary="Blocking Goldens must verify behavior contracts, not only final text.",
            blockers=golden_blockers + golden_missing,
            evidence=[
                _evidence("active_goldens", golden_counts["active"]),
                _evidence("blocking_goldens", golden_counts["blocking"]),
                _evidence("blocking_behavioral_goldens", golden_counts["blocking_behavioral"]),
                _evidence("blocking_text_only_goldens", golden_counts["blocking_text_only"]),
            ],
            verification_commands=[
                "python -m pytest tests/test_goldens.py",
            ],
        )
    )

    ci_blockers = []
    if ci_counts["fail"] > 0:
        ci_blockers.append("blocking_ci_failures")
    if ci_counts["error"] > 0:
        ci_blockers.append("ci_executor_errors")
    ci_missing = []
    if ci_counts["total"] <= 0:
        ci_missing.append("ci_gate_run_missing")
    if ci_counts["not_verified"] > 0:
        ci_missing.append("ci_not_verified")
    gates.append(
        _gate(
            code="durable_ci_gate",
            title="Durable CI Gate",
            status=_status_for(blockers=ci_blockers, missing=ci_missing),
            summary="CI must run durable Golden gates and fail repeat regressions or not_verified safety checks.",
            blockers=ci_blockers + ci_missing,
            evidence=[
                _evidence("ci_runs_7d", ci_counts["total"]),
                _evidence("ci_pass_7d", ci_counts["pass"]),
                _evidence("ci_warn_7d", ci_counts["warn"]),
                _evidence("ci_fail_7d", ci_counts["fail"]),
                _evidence("ci_not_verified_7d", ci_counts["not_verified"]),
                _evidence("ci_error_7d", ci_counts["error"]),
            ],
            verification_commands=[
                "python -m pytest tests/test_regression_ci_routes.py tests/test_regression_ci_orchestrator.py",
                "npm test",
            ],
        )
    )

    runtime_missing = []
    if runtime_counts["risk_stopped"] <= 0:
        runtime_missing.append("runtime_risk_stop_evidence_missing")
    gates.append(
        _gate(
            code="runtime_risk_stop",
            title="Runtime Risk Stop",
            status=_status_for(blockers=[], missing=runtime_missing),
            summary="Risky autonomous actions must be blocked or paused before side effects execute.",
            blockers=runtime_missing,
            evidence=[
                _evidence("risk_stopped_7d", runtime_counts["risk_stopped"]),
                _evidence("blocked_7d", runtime_counts["blocked"]),
                _evidence("pending_approvals_7d", runtime_counts["pending_approval"]),
                _evidence("approved_7d", runtime_counts["approved"]),
                _evidence("rejected_7d", runtime_counts["rejected"]),
            ],
            verification_commands=[
                "python -m pytest tests/test_runtime_policy_gate.py",
            ],
        )
    )

    billing_blockers = list(platform.billing_launch_blockers or [])
    gates.append(
        _gate(
            code="billing_quota",
            title="Billing + Quota",
            status=_status_for(blockers=billing_blockers, missing=[]),
            summary="Plan entitlements, usage, metering, payment lifecycle, and provider proof must be reliable and owner-visible.",
            blockers=billing_blockers,
            evidence=[
                _evidence("billing_launch_blockers", len(billing_blockers)),
                _evidence("metering_failure_tenants", platform.metering_failure_tenants),
                _evidence("event_counter_failure_count", platform.event_counter_failure_count),
                _evidence(
                    "billing_provider_verification",
                    platform.billing_provider_verification.state,
                    detail=platform.billing_provider_verification.detail,
                ),
                _evidence("tenants_with_quota_risk", platform.tenants_with_quota_risk),
                _evidence("tenants_with_billing_risk", platform.tenants_with_billing_risk),
            ],
            verification_commands=[
                "python -m pytest tests/test_billing_v2.py tests/test_owner_money_path_health.py",
            ],
        )
    )

    getting_value_tenants = sum(1 for row in tenants if row.value_status == "getting_value")
    owner_value_blockers = [
        code
        for code in platform.launch_blockers
        if code
        in {
            "deployment_smoke_not_passing",
            "billing_provider_unverified",
            "pricing_contract_drift",
        }
    ]
    owner_value_missing = []
    if getting_value_tenants <= 0:
        owner_value_missing.append("no_tenant_getting_value")
    gates.append(
        _gate(
            code="owner_value_proof",
            title="Owner Value Proof",
            status=_status_for(blockers=owner_value_blockers, missing=owner_value_missing),
            summary="Owner must see who is getting reliability value and where money path is blocked.",
            blockers=owner_value_blockers + owner_value_missing,
            evidence=[
                _evidence("getting_value_tenants", getting_value_tenants),
                _evidence("blocked_regressions_7d", platform.blocked_regressions_7d),
                _evidence("verified_fixes_7d", platform.verified_fixes_7d),
                _evidence("deployment_smoke", platform.last_deployed_smoke.status, detail=platform.last_deployed_smoke.detail),
                _evidence("launch_blockers", len(platform.launch_blockers)),
            ],
            verification_commands=[
                "python -m pytest tests/test_owner_money_path_health.py",
                "python scripts/run_money_path_demo.py --json",
                "npm test -- --run src/app/owner/page.test.tsx src/app/owner/money-path/page.test.tsx",
            ],
        )
    )

    gates.append(
        _gate(
            code="single_source_of_truth",
            title="Single Source Of Truth",
            status=source_status,
            summary="Only root README.md may guide product direction; stale planning Markdown must not steer implementation.",
            blockers=source_blockers,
            evidence=source_evidence,
            verification_commands=[
                "git ls-files \"*.md\"",
                "python scripts/check_docs_drift.py",
            ],
        )
    )

    paid_launch_allowed = all(gate.status == "pass" for gate in gates)
    hard_blockers = [
        f"{gate.code}:{blocker}"
        for gate in gates
        for blocker in gate.blockers
        if gate.status != "pass"
    ]
    if paid_launch_allowed:
        overall_status = "pass"
    elif any(gate.status == "fail" for gate in gates):
        overall_status = "blocked"
    else:
        overall_status = "not_verified"

    return OwnerLaunchReadinessResponse(
        generated_at=now,
        product_standard=PRODUCT_STANDARD,
        overall_status=overall_status,
        paid_launch_allowed=paid_launch_allowed,
        gates=gates,
        hard_blockers=hard_blockers,
        verification_commands=FINAL_READINESS_COMMANDS,
    )


@router.get("/money-path-health", response_model=OwnerMoneyPathHealthResponse)
def owner_money_path_health(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> OwnerMoneyPathHealthResponse:
    now = datetime.now(UTC)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)
    month_start, resets_at = _month_window(now)

    projects = db.execute(
        select(Project)
        .where(Project.is_active.is_(True))
        .order_by(Project.created_at.desc(), Project.name.asc())
    ).scalars().all()
    project_ids = [project.id for project in projects]

    if not project_ids:
        return OwnerMoneyPathHealthResponse(
            generated_at=now,
            windows={"captures_hours": 24, "replays_days": 7},
            platform=OwnerMoneyPathPlatformSummary(
                captures_24h=0,
                issues_open=0,
                replay_runs_7d=0,
                verified_replay_runs_7d=0,
                golden_traces_active=0,
                ci_runs_7d=0,
                ci_blocks_7d=0,
                replay_jobs_pending=0,
                replay_jobs_stale=0,
                gateway_unhealthy_tenants=0,
                gateway_loss_tenants=0,
                gateway_backpressure_tenants=0,
                tenants_missing_provider_key=0,
                tenants_near_replay_quota=0,
                tenants_without_recent_capture=0,
                pricing_contract_drift=_pricing_drift(),
                launch_blockers=["no_active_projects"],
                last_deployed_smoke=_last_deployed_smoke(db),
            ),
            tenants=[],
        )

    subscription_rows = db.execute(
        select(Subscription).where(Subscription.org_id.in_(project_ids))
    ).scalars().all()
    subscriptions = {subscription.org_id: subscription for subscription in subscription_rows}
    event_counts = _count_map(
        db.execute(
            select(EventCount.tenant_id, func.coalesce(func.sum(EventCount.event_count), 0))
            .where(
                EventCount.tenant_id.in_(project_ids),
                EventCount.month == month_start.strftime("%Y-%m"),
            )
            .group_by(EventCount.tenant_id)
        ).all()
    )
    metering_failure_counts, metering_last_failure = count_open_metering_failures(
        db, project_ids
    )

    last_capture_rows = db.execute(
        select(Call.project_id, func.max(Call.created_at))
        .where(Call.project_id.in_(project_ids))
        .group_by(Call.project_id)
    ).all()
    last_capture_by_project = {
        project_id: _as_utc(last_capture_at)
        for project_id, last_capture_at in last_capture_rows
    }
    latest_call_subquery = (
        select(Call.project_id, func.max(Call.created_at).label("latest_created_at"))
        .where(Call.project_id.in_(project_ids))
        .group_by(Call.project_id)
        .subquery()
    )
    latest_call_rows = db.execute(
        select(Call)
        .join(
            latest_call_subquery,
            (Call.project_id == latest_call_subquery.c.project_id)
            & (Call.created_at == latest_call_subquery.c.latest_created_at),
        )
        .order_by(Call.project_id, Call.id.desc())
    ).scalars().all()
    latest_call_by_project: dict[str, Call] = {}
    for call in latest_call_rows:
        latest_call_by_project.setdefault(call.project_id, call)

    captures_24h = _count_map(
        db.execute(
            select(Call.project_id, func.count(Call.id))
            .where(Call.project_id.in_(project_ids), Call.created_at >= since_24h)
            .group_by(Call.project_id)
        ).all()
    )

    issue_total_counts = _count_map(
        db.execute(
            select(Issue.project_id, func.count(Issue.id))
            .where(Issue.project_id.in_(project_ids))
            .group_by(Issue.project_id)
        ).all()
    )
    issue_open_counts = _count_map(
        db.execute(
            select(Issue.project_id, func.count(Issue.id))
            .where(
                Issue.project_id.in_(project_ids),
                Issue.status.in_(OPEN_ISSUE_STATUSES),
            )
            .group_by(Issue.project_id)
        ).all()
    )
    anomaly_open_counts = _count_map(
        db.execute(
            select(Anomaly.project_id, func.count(Anomaly.id))
            .where(
                Anomaly.project_id.in_(project_ids),
                Anomaly.status.in_(OPEN_ISSUE_STATUSES),
            )
            .group_by(Anomaly.project_id)
        ).all()
    )

    golden_trace_counts = _count_map(
        db.execute(
            select(GoldenTrace.project_id, func.count(GoldenTrace.id))
            .where(
                GoldenTrace.project_id.in_(project_ids),
                GoldenTrace.status == "active",
            )
            .group_by(GoldenTrace.project_id)
        ).all()
    )

    active_provider_counts = _count_map(
        db.execute(
            select(ProviderKeyVault.project_id, func.count(ProviderKeyVault.id))
            .where(
                ProviderKeyVault.project_id.in_(project_ids),
                ProviderKeyVault.is_active.is_(True),
                ProviderKeyVault.revoked_at.is_(None),
            )
            .group_by(ProviderKeyVault.project_id)
        ).all()
    )

    support_open_counts = _count_map(
        db.execute(
            select(SupportTicket.tenant_id, func.count(SupportTicket.id))
            .where(
                SupportTicket.tenant_id.in_(project_ids),
                SupportTicket.status.in_(OPEN_SUPPORT_STATUSES),
            )
            .group_by(SupportTicket.tenant_id)
        ).all()
    )
    support_urgent_counts = _count_map(
        db.execute(
            select(SupportTicket.tenant_id, func.count(SupportTicket.id))
            .where(
                SupportTicket.tenant_id.in_(project_ids),
                SupportTicket.status.in_(OPEN_SUPPORT_STATUSES),
                SupportTicket.priority.in_(URGENT_SUPPORT_PRIORITIES),
            )
            .group_by(SupportTicket.tenant_id)
        ).all()
    )

    replay_runs_7d = db.execute(
        select(ReplayRun).where(
            ReplayRun.project_id.in_(project_ids),
            ReplayRun.created_at >= since_7d,
        )
    ).scalars().all()
    replay_run_counts: dict[str, int] = defaultdict(int)
    verified_replay_counts: dict[str, int] = defaultdict(int)
    ci_run_counts: dict[str, int] = defaultdict(int)
    ci_block_counts: dict[str, int] = defaultdict(int)
    for run in replay_runs_7d:
        replay_run_counts[run.project_id] += 1
        if _is_verified_replay(run):
            verified_replay_counts[run.project_id] += 1
        if run.trigger == "github":
            ci_run_counts[run.project_id] += 1
            if run.status in BLOCKING_CI_STATUSES:
                ci_block_counts[run.project_id] += 1

    replay_run_month_counts = _count_map(
        db.execute(
            select(ReplayRun.project_id, func.count(ReplayRun.id))
            .where(
                ReplayRun.project_id.in_(project_ids),
                ReplayRun.created_at >= month_start,
            )
            .group_by(ReplayRun.project_id)
        ).all()
    )
    replay_job_month_counts = _count_map(
        db.execute(
            select(ReplayJob.tenant_id, func.count(ReplayJob.id))
            .where(
                ReplayJob.tenant_id.in_(project_ids),
                ReplayJob.created_at >= month_start,
            )
            .group_by(ReplayJob.tenant_id)
        ).all()
    )
    replay_job_pending_counts = _count_map(
        db.execute(
            select(ReplayJob.tenant_id, func.count(ReplayJob.id))
            .where(
                ReplayJob.tenant_id.in_(project_ids),
                ReplayJob.status == "pending",
            )
            .group_by(ReplayJob.tenant_id)
        ).all()
    )
    replay_job_stale_counts = _count_map(
        db.execute(
            select(ReplayJob.tenant_id, func.count(ReplayJob.id))
            .where(
                ReplayJob.tenant_id.in_(project_ids),
                ReplayJob.status == "running",
                ReplayJob.lease_expires_at.is_not(None),
                ReplayJob.lease_expires_at <= now,
            )
            .group_by(ReplayJob.tenant_id)
        ).all()
    )

    gateway_rows = db.execute(
        select(GatewayCaptureHealth).where(GatewayCaptureHealth.project_id.in_(project_ids))
    ).scalars().all()
    gateway_rows_by_project: dict[str, list[GatewayCaptureHealth]] = defaultdict(list)
    for row in gateway_rows:
        gateway_rows_by_project[row.project_id].append(row)

    pricing_drift = _pricing_drift()
    tenants: list[OwnerMoneyPathTenantRow] = []
    for project in projects:
        subscription = subscriptions.get(project.id)
        plan_code, replay_enabled, replay_limit = _plan_contract(
            subscription.plan_code if subscription is not None else None
        )
        active_provider_count = active_provider_counts.get(project.id, 0)
        provider_status = OwnerProviderKeyStatus(
            state="configured" if active_provider_count > 0 else "missing",
            active_provider_count=active_provider_count,
        )
        quota_status = _quota_status(
            enabled=replay_enabled,
            used=(
                replay_run_month_counts.get(project.id, 0)
                + replay_job_month_counts.get(project.id, 0)
            ),
            limit=replay_limit,
            resets_at=resets_at,
        )
        event_metering = _event_metering_status(
            used=event_counts.get(project.id, 0),
            limit=_plan_event_limit(plan_code),
            failure_count=metering_failure_counts.get(project.id, 0),
            last_failure_at=metering_last_failure.get(project.id),
        )
        issue_count = (
            issue_open_counts.get(project.id, 0)
            if issue_total_counts.get(project.id, 0) > 0
            else anomaly_open_counts.get(project.id, 0)
        )
        last_capture_at = last_capture_by_project.get(project.id)
        replay_jobs_pending = replay_job_pending_counts.get(project.id, 0)
        replay_jobs_stale = replay_job_stale_counts.get(project.id, 0)
        capture_durability = _capture_durability_status(gateway_rows_by_project.get(project.id, []), now)
        pricing_cost = _pricing_cost_status(
            latest_call_by_project.get(project.id),
            pricing_contract_drift=pricing_drift,
            now=now,
        )
        billing = _billing_status(subscription, plan_code=plan_code)
        support = _support_status(
            open_count=support_open_counts.get(project.id, 0),
            urgent_count=support_urgent_counts.get(project.id, 0),
        )
        launch_blockers = _tenant_launch_blockers(
            last_capture_at=last_capture_at,
            since_recent_capture=since_24h,
            open_issue_count=issue_count,
            replay_run_count_7d=replay_run_counts.get(project.id, 0),
            verified_replay_count_7d=verified_replay_counts.get(project.id, 0),
            golden_trace_count=golden_trace_counts.get(project.id, 0),
            ci_run_count_7d=ci_run_counts.get(project.id, 0),
            blocking_ci_failures_7d=ci_block_counts.get(project.id, 0),
            replay_jobs_stale=replay_jobs_stale,
            capture_durability_status=capture_durability,
            provider_key_status=provider_status,
            replay_quota_status=quota_status,
            event_metering_status=event_metering,
            pricing_cost_status=pricing_cost,
            billing_status=billing,
            support_status=support,
        )
        money_path_breaks = _money_path_breaks(
            launch_blockers=launch_blockers,
            golden_trace_count=golden_trace_counts.get(project.id, 0),
            blocking_ci_failures_7d=ci_block_counts.get(project.id, 0),
            replay_jobs_pending=replay_jobs_pending,
            replay_jobs_stale=replay_jobs_stale,
            event_metering_status=event_metering,
            pricing_cost_status=pricing_cost,
            billing_status=billing,
            support_status=support,
        )
        value_status = _value_status(
            money_path_breaks=money_path_breaks,
            captures_24h=captures_24h.get(project.id, 0),
            open_issue_count=issue_count,
            replay_run_count_7d=replay_run_counts.get(project.id, 0),
            verified_replay_count_7d=verified_replay_counts.get(project.id, 0),
            golden_trace_count=golden_trace_counts.get(project.id, 0),
            ci_run_count_7d=ci_run_counts.get(project.id, 0),
        )
        row = OwnerMoneyPathTenantRow(
            project_id=project.id,
            project_name=project.name,
            plan_code=plan_code,
            last_capture_at=last_capture_at,
            captures_24h=captures_24h.get(project.id, 0),
            open_issue_count=issue_count,
            replay_run_count_7d=replay_run_counts.get(project.id, 0),
            verified_replay_count_7d=verified_replay_counts.get(project.id, 0),
            golden_trace_count=golden_trace_counts.get(project.id, 0),
            ci_run_count_7d=ci_run_counts.get(project.id, 0),
            blocking_ci_failures_7d=ci_block_counts.get(project.id, 0),
            replay_jobs_pending=replay_jobs_pending,
            replay_jobs_stale=replay_jobs_stale,
            capture_durability_status=capture_durability,
            provider_key_status=provider_status,
            replay_quota_status=quota_status,
            event_metering_status=event_metering,
            pricing_cost_status=pricing_cost,
            billing_status=billing,
            support_status=support,
            blocked_regressions_7d=ci_block_counts.get(project.id, 0),
            verified_fixes_7d=verified_replay_counts.get(project.id, 0),
            value_status=value_status,
            money_path_breaks=money_path_breaks,
            tenant_priority_score=0,
            launch_blockers=launch_blockers,
            next_owner_action=_next_owner_action(
                last_capture_at=last_capture_at,
                since_recent_capture=since_24h,
                open_issue_count=issue_count,
                replay_run_count_7d=replay_run_counts.get(project.id, 0),
                verified_replay_count_7d=verified_replay_counts.get(project.id, 0),
                golden_trace_count=golden_trace_counts.get(project.id, 0),
                ci_run_count_7d=ci_run_counts.get(project.id, 0),
                blocking_ci_failures_7d=ci_block_counts.get(project.id, 0),
                replay_jobs_stale=replay_jobs_stale,
                capture_durability_status=capture_durability,
                provider_key_status=provider_status,
                replay_quota_status=quota_status,
                event_metering_status=event_metering,
                pricing_cost_status=pricing_cost,
                billing_status=billing,
                support_status=support,
            ),
        )
        row.tenant_priority_score = _risk_score(row)
        tenants.append(row)

    tenants.sort(key=lambda row: (-row.tenant_priority_score, row.project_name.lower()))

    last_deployed_smoke = _last_deployed_smoke(db)
    platform_launch_blockers: list[str] = []
    if sum(row.captures_24h for row in tenants) == 0:
        platform_launch_blockers.append("capture_unhealthy")
    if any(row.golden_trace_count == 0 for row in tenants):
        platform_launch_blockers.append("goldens_missing")
    if any(row.provider_key_status.state == "missing" for row in tenants):
        platform_launch_blockers.append("provider_key_missing")
    if any(row.replay_quota_status.state in {"blocked", "disabled", "exceeded"} for row in tenants):
        platform_launch_blockers.append("replay_quota_blocking")
    if any(row.event_metering_status.state == "failure" for row in tenants):
        platform_launch_blockers.append("event_metering_failure")
    if any(row.event_metering_status.state in {"blocked", "exceeded"} for row in tenants):
        platform_launch_blockers.append("event_quota_blocking")
    if sum(row.replay_jobs_stale for row in tenants) > 0:
        platform_launch_blockers.append("replay_worker_stale_jobs")
    if any(row.capture_durability_status.state == "loss_detected" for row in tenants):
        platform_launch_blockers.append("capture_loss_detected")
    if any(row.capture_durability_status.state == "backpressure" for row in tenants):
        platform_launch_blockers.append("gateway_backpressure")
    if any(
        row.capture_durability_status.state == "degraded"
        or row.capture_durability_status.spool_backlog > 0
        for row in tenants
    ):
        platform_launch_blockers.append("gateway_spool_stale")
    if sum(row.blocking_ci_failures_7d for row in tenants) > 0:
        platform_launch_blockers.append("ci_gate_blocking_failures")
    if any(row.pricing_cost_status.state in {"drift", "missing", "fallback", "stale"} for row in tenants):
        platform_launch_blockers.append("pricing_cost_risk")
    if any(row.billing_status.state in {"risk", "missing_paid", "unknown"} for row in tenants):
        platform_launch_blockers.append("billing_risk")
    if any(row.support_status.state == "urgent" for row in tenants):
        platform_launch_blockers.append("urgent_support_ticket")
    if last_deployed_smoke.status != "passed":
        platform_launch_blockers.append("deployment_smoke_not_passing")
    if pricing_drift:
        platform_launch_blockers.append("pricing_contract_drift")
    provider_verification = _billing_provider_verification(db)
    if provider_verification.state != "verified":
        platform_launch_blockers.append("billing_provider_unverified")
    billing_launch_blockers = [
        blocker
        for blocker in platform_launch_blockers
        if blocker.startswith("billing")
        or blocker.startswith("pricing")
        or blocker.startswith("event_")
        or blocker.endswith("_quota_blocking")
    ]

    platform = OwnerMoneyPathPlatformSummary(
        captures_24h=sum(row.captures_24h for row in tenants),
        issues_open=sum(row.open_issue_count for row in tenants),
        replay_runs_7d=sum(row.replay_run_count_7d for row in tenants),
        verified_replay_runs_7d=sum(row.verified_replay_count_7d for row in tenants),
        golden_traces_active=sum(row.golden_trace_count for row in tenants),
        ci_runs_7d=sum(row.ci_run_count_7d for row in tenants),
        ci_blocks_7d=sum(row.blocking_ci_failures_7d for row in tenants),
        replay_jobs_pending=sum(row.replay_jobs_pending for row in tenants),
        replay_jobs_stale=sum(row.replay_jobs_stale for row in tenants),
        gateway_unhealthy_tenants=sum(
            1 for row in tenants if row.capture_durability_status.unhealthy_gateway_count > 0
        ),
        gateway_loss_tenants=sum(
            1 for row in tenants if row.capture_durability_status.loss_count > 0
        ),
        gateway_backpressure_tenants=sum(
            1
            for row in tenants
            if row.capture_durability_status.backpressure_rejections > 0
            or row.capture_durability_status.state == "backpressure"
        ),
        tenants_missing_provider_key=sum(
            1 for row in tenants if row.provider_key_status.state == "missing"
        ),
        tenants_near_replay_quota=sum(
            1
            for row in tenants
            if row.replay_quota_status.state in {"near_limit", "exceeded"}
        ),
        tenants_without_recent_capture=sum(
            1
            for row in tenants
            if row.last_capture_at is None or row.last_capture_at < since_24h
        ),
        tenants_without_goldens=sum(1 for row in tenants if row.golden_trace_count == 0),
        tenants_with_failed_ci=sum(1 for row in tenants if row.blocking_ci_failures_7d > 0),
        tenants_with_stale_replay_workers=sum(1 for row in tenants if row.replay_jobs_stale > 0),
        tenants_with_stale_pricing=sum(
            1
            for row in tenants
            if row.pricing_cost_status.state in {"drift", "missing", "fallback", "stale", "degraded"}
        ),
        tenants_with_quota_risk=sum(
            1
            for row in tenants
            if row.replay_quota_status.state in {"near_limit", "exceeded", "blocked"}
            or row.event_metering_status.state in {"near_limit", "exceeded", "blocked", "failure"}
        ),
        tenants_with_billing_risk=sum(
            1
            for row in tenants
            if row.billing_status.state in {"risk", "missing_paid", "unknown"}
        ),
        metering_failure_tenants=sum(
            1 for row in tenants if row.event_metering_status.state == "failure"
        ),
        event_counter_failure_count=sum(
            row.event_metering_status.failure_count for row in tenants
        ),
        billing_launch_blockers=billing_launch_blockers,
        billing_provider_verification=provider_verification,
        support_tickets_open=sum(row.support_status.open_count for row in tenants),
        support_tickets_urgent=sum(row.support_status.urgent_count for row in tenants),
        blocked_regressions_7d=sum(row.blocked_regressions_7d for row in tenants),
        verified_fixes_7d=sum(row.verified_fixes_7d for row in tenants),
        pricing_contract_drift=pricing_drift,
        launch_blockers=platform_launch_blockers,
        last_deployed_smoke=last_deployed_smoke,
    )

    return OwnerMoneyPathHealthResponse(
        generated_at=now,
        windows={"captures_hours": 24, "replays_days": 7},
        platform=platform,
        tenants=tenants,
    )


@router.get("/launch-readiness", response_model=OwnerLaunchReadinessResponse)
def owner_launch_readiness(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> OwnerLaunchReadinessResponse:
    money_path = owner_money_path_health(None, db)
    return _build_launch_readiness(db, money_path=money_path)


__all__ = [name for name in globals() if not name.startswith("__")]
