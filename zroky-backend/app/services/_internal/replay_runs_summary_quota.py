from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ReplayRun

logger = logging.getLogger(__name__)

# ── summary helper for response payloads ─────────────────────────────────────


def parse_summary(summary_json: str | None) -> dict[str, Any]:
    """Defensive parser for the `summary_json` blob on a ReplayRun row."""
    if not summary_json:
        return {}
    try:
        decoded = json.loads(summary_json)
        return decoded if isinstance(decoded, dict) else {}
    except Exception:
        return {}


# ── summary URL builder (Module 9) ───────────────────────────────────────────


def build_summary_url(run: ReplayRun) -> str:
    """Return the dashboard URL for a replay run.

    Used as `details_url` on PR checks and as the response field on the
    Module-9 dispatch endpoints. Read at call time so test settings
    overrides (`monkeypatch.setattr(settings, "FRONTEND_URL", ...)`) take
    effect without import-time caching.
    """
    # Local import to avoid creating a circular dependency at the top of
    # this module — `app.core.config` itself imports nothing from
    # `services` but the cached settings instance can be patched in
    # tests, so we re-resolve every call.
    from app.core.config import get_settings

    settings = get_settings()
    base = (settings.FRONTEND_URL or "https://zroky.com").rstrip("/")
    return f"{base}/evidence?replay_run_id={run.id}"


# ── monthly quota ─────────────────────────────────────────────────────────────


@dataclass
class ReplayQuotaResult:
    """Monthly replay quota state for a tenant.

    ``limit == -1`` means unlimited (Enterprise). Callers must treat
    -1 as "no cap" rather than a literal number; the quota is never
    considered exceeded when limit is -1.
    """

    enabled: bool    # pilot.autopilot_enabled — basic feature gate
    used: int        # ReplayRun + ReplayJob rows created this calendar month
    limit: int       # replay.monthly_runs; -1 = unlimited
    resets_at: str   # ISO date of first day of next calendar month
    plan_code: str   # e.g. "pro", "plus", "enterprise"
    real_comparison_enabled: bool


def check_replay_monthly_quota(db: Session, tenant_id: str) -> ReplayQuotaResult:
    """Return the monthly replay quota state for ``tenant_id``.

    Counts both :class:`ReplayRun` (batch golden-set runs) and the
    legacy :class:`ReplayJob` rows (single-call worker jobs) against
    the plan's ``replay.monthly_runs`` entitlement. The combined total
    is what the dashboard quota banner displays.

    Never raises — returns ``allowed=False / limit=0`` on any DB or
    resolver error so a transient failure never opens a quota bypass.
    """
    from app.db.models import ReplayJob  # local: intentionally separate service
    from app.services import entitlements_resolver

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        resets_dt = month_start.replace(year=now.year + 1, month=1)
    else:
        resets_dt = month_start.replace(month=now.month + 1)

    resets_at = resets_dt.date().isoformat()

    try:
        enabled: bool = entitlements_resolver.has(db, tenant_id, "pilot.autopilot_enabled")
        raw_limit = entitlements_resolver.get(
            db, tenant_id, "replay.monthly_runs", default=0
        )
        limit: int = int(raw_limit) if raw_limit is not None else 0
        plan_code: str = entitlements_resolver.get_plan_code(db, tenant_id)

        run_count: int = (
            db.execute(
                select(func.count(ReplayRun.id)).where(
                    ReplayRun.project_id == tenant_id,
                    ReplayRun.created_at >= month_start,
                )
            ).scalar_one()
            or 0
        )
        job_count: int = (
            db.execute(
                select(func.count(ReplayJob.id)).where(
                    ReplayJob.tenant_id == tenant_id,
                    ReplayJob.created_at >= month_start,
                )
            ).scalar_one()
            or 0
        )
        used = run_count + job_count

    except Exception:  # noqa: BLE001
        logger.exception(
            "check_replay_monthly_quota failed for tenant=%s — denying", tenant_id
        )
        return ReplayQuotaResult(
            enabled=False,
            used=0,
            limit=0,
            resets_at=resets_at,
            plan_code="unknown",
            real_comparison_enabled=False,
        )

    from app.core.config import get_settings

    return ReplayQuotaResult(
        enabled=enabled,
        used=used,
        limit=limit,
        resets_at=resets_at,
        plan_code=plan_code,
        real_comparison_enabled=bool(get_settings().REPLAY_REAL_LLM_ENABLED),
    )
