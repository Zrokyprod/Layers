from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes._internal.owner_money_path_schemas import (
    OwnerMoneyPathHealthResponse,
    OwnerMoneyPathPlatformSummary,
    OwnerMoneyPathTenantRow,
    OwnerProviderKeyStatus,
)
from app.api.routes._internal.owner_money_path import (
    BLOCKING_CI_STATUSES,
    OPEN_ISSUE_STATUSES,
    OPEN_SUPPORT_STATUSES,
    URGENT_SUPPORT_PRIORITIES,
    _as_utc,
    _billing_provider_verification,
    _billing_status,
    _capture_durability_status,
    _count_map,
    _event_metering_status,
    _is_verified_replay,
    _last_deployed_smoke,
    _money_path_breaks,
    _month_window,
    _next_owner_action,
    _plan_contract,
    _plan_event_limit,
    _pricing_cost_status,
    _pricing_drift,
    _quota_status,
    _risk_score,
    _support_status,
    _tenant_launch_blockers,
    _value_status,
)
from app.db.models import (
    Anomaly,
    Call,
    EventCount,
    GatewayCaptureHealth,
    GoldenTrace,
    Issue,
    Project,
    ProviderKeyVault,
    ReplayJob,
    ReplayRun,
    Subscription,
    SupportTicket,
)
from app.services.billing_metering import count_open_metering_failures

def build_money_path_health(db: Session) -> OwnerMoneyPathHealthResponse:
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
