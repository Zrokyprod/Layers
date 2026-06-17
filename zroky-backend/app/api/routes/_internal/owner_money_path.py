from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.routes._internal.owner_common import (
    get_db_session,
    require_provisioning_access,
    router,
)
from app.api.routes._internal.owner_money_path_schemas import (
    OwnerBillingProviderVerification,
    OwnerBillingStatus,
    OwnerCaptureDurabilityStatus,
    OwnerEventMeteringStatus,
    OwnerLastDeployedSmoke,
    OwnerLaunchReadinessResponse,
    OwnerMoneyPathHealthResponse,
    OwnerMoneyPathTenantRow,
    OwnerPricingCostStatus,
    OwnerProviderKeyStatus,
    OwnerReplayQuotaStatus,
    OwnerSupportStatus,
)
from app.api.routes._internal.owner_pricing_audit import _pricing_contract_drift
from app.db.models import (
    Call,
    BillingEvent,
    GatewayCaptureHealth,
    GoldenTrace,
    ReplayRun,
    Subscription,
)
from app.services.entitlement_catalog import (
    DEFAULT_PLAN_CODE,
    UNLIMITED,
    InvalidPlanCodeError,
    get_catalog_entry,
    load_pricing_contract,
)


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
            BillingEvent.provider == "razorpay",
            BillingEvent.event_type.in_(("payment.succeeded", "payment_request.created")),
        )
        .order_by(func.coalesce(BillingEvent.processed_at, BillingEvent.received_at).desc())
        .limit(1)
    )
    if latest is None:
        return OwnerBillingProviderVerification(
            state="unverified",
            detail="No Razorpay billing event has been recorded.",
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


def _build_launch_readiness(
    db: Session,
    *,
    money_path: OwnerMoneyPathHealthResponse,
) -> OwnerLaunchReadinessResponse:
    from app.api.routes._internal.owner_launch_readiness_builder import (
        build_launch_readiness,
    )

    return build_launch_readiness(db, money_path=money_path)

@router.get("/money-path-health", response_model=OwnerMoneyPathHealthResponse)
def owner_money_path_health(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> OwnerMoneyPathHealthResponse:
    from app.api.routes._internal.owner_money_path_health_builder import (
        build_money_path_health,
    )

    return build_money_path_health(db)

@router.get("/launch-readiness", response_model=OwnerLaunchReadinessResponse)
def owner_launch_readiness(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> OwnerLaunchReadinessResponse:
    money_path = owner_money_path_health(None, db)
    return _build_launch_readiness(db, money_path=money_path)


__all__ = [name for name in globals() if not name.startswith("__")]
