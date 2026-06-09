from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.routes._internal.owner_common import (
    get_db_session,
    require_provisioning_access,
    router,
)
from app.db.models import (
    Anomaly,
    Call,
    GoldenTrace,
    Issue,
    Project,
    ProviderKeyVault,
    ReplayJob,
    ReplayRun,
    Subscription,
)
from app.services.entitlement_catalog import (
    DEFAULT_PLAN_CODE,
    UNLIMITED,
    InvalidPlanCodeError,
    get_catalog_entry,
)


OPEN_ISSUE_STATUSES = ("open", "acknowledged")
BLOCKING_CI_STATUSES = ("fail", "error")
VERIFIED_REPLAY_STATUSES = {"verified_fix", "real_replay_passed"}


class OwnerReplayQuotaStatus(BaseModel):
    state: str
    enabled: bool
    used: int
    limit: int
    resets_at: str


class OwnerProviderKeyStatus(BaseModel):
    state: str
    active_provider_count: int


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
    tenants_missing_provider_key: int
    tenants_near_replay_quota: int
    tenants_without_recent_capture: int
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
    provider_key_status: OwnerProviderKeyStatus
    replay_quota_status: OwnerReplayQuotaStatus
    next_owner_action: str


class OwnerMoneyPathHealthResponse(BaseModel):
    generated_at: datetime
    windows: dict[str, int]
    platform: OwnerMoneyPathPlatformSummary
    tenants: list[OwnerMoneyPathTenantRow]


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
    provider_key_status: OwnerProviderKeyStatus,
    replay_quota_status: OwnerReplayQuotaStatus,
) -> str:
    if blocking_ci_failures_7d > 0:
        return "review_blocked_ci"
    if last_capture_at is None or last_capture_at < since_recent_capture:
        return "restore_capture"
    if provider_key_status.state == "missing":
        return "connect_provider_key"
    if replay_quota_status.state in {"exceeded", "near_limit"}:
        return "review_replay_quota"
    if open_issue_count > 0 and replay_run_count_7d == 0:
        return "run_replay"
    if golden_trace_count == 0 and verified_replay_count_7d > 0:
        return "promote_golden"
    if golden_trace_count > 0 and ci_run_count_7d == 0:
        return "run_ci_gate"
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
    if row.replay_quota_status.state == "exceeded":
        score += 20
    elif row.replay_quota_status.state == "near_limit":
        score += 12
    return score


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
                tenants_missing_provider_key=0,
                tenants_near_replay_quota=0,
                tenants_without_recent_capture=0,
                last_deployed_smoke=_last_deployed_smoke(db),
            ),
            tenants=[],
        )

    subscription_rows = db.execute(
        select(Subscription).where(Subscription.org_id.in_(project_ids))
    ).scalars().all()
    subscriptions = {subscription.org_id: subscription for subscription in subscription_rows}

    last_capture_rows = db.execute(
        select(Call.project_id, func.max(Call.created_at))
        .where(Call.project_id.in_(project_ids))
        .group_by(Call.project_id)
    ).all()
    last_capture_by_project = {
        project_id: _as_utc(last_capture_at)
        for project_id, last_capture_at in last_capture_rows
    }

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
        issue_count = (
            issue_open_counts.get(project.id, 0)
            if issue_total_counts.get(project.id, 0) > 0
            else anomaly_open_counts.get(project.id, 0)
        )
        last_capture_at = last_capture_by_project.get(project.id)
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
            provider_key_status=provider_status,
            replay_quota_status=quota_status,
            next_owner_action=_next_owner_action(
                last_capture_at=last_capture_at,
                since_recent_capture=since_24h,
                open_issue_count=issue_count,
                replay_run_count_7d=replay_run_counts.get(project.id, 0),
                verified_replay_count_7d=verified_replay_counts.get(project.id, 0),
                golden_trace_count=golden_trace_counts.get(project.id, 0),
                ci_run_count_7d=ci_run_counts.get(project.id, 0),
                blocking_ci_failures_7d=ci_block_counts.get(project.id, 0),
                provider_key_status=provider_status,
                replay_quota_status=quota_status,
            ),
        )
        tenants.append(row)

    tenants.sort(key=lambda row: (-_risk_score(row), row.project_name.lower()))

    platform = OwnerMoneyPathPlatformSummary(
        captures_24h=sum(row.captures_24h for row in tenants),
        issues_open=sum(row.open_issue_count for row in tenants),
        replay_runs_7d=sum(row.replay_run_count_7d for row in tenants),
        verified_replay_runs_7d=sum(row.verified_replay_count_7d for row in tenants),
        golden_traces_active=sum(row.golden_trace_count for row in tenants),
        ci_runs_7d=sum(row.ci_run_count_7d for row in tenants),
        ci_blocks_7d=sum(row.blocking_ci_failures_7d for row in tenants),
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
        last_deployed_smoke=_last_deployed_smoke(db),
    )

    return OwnerMoneyPathHealthResponse(
        generated_at=now,
        windows={"captures_hours": 24, "replays_days": 7},
        platform=platform,
        tenants=tenants,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
