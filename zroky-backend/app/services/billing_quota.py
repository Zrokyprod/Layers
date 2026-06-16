"""Billing quota service — fast event-count checks against plan limits.

Uses the ``event_counts`` metering ledger (upserted on every accepted ingest)
for O(1) current-month lookups instead of scanning the ``calls`` table.
Plan limits come from the active entitlement matrix, not legacy plan rows.

Public API
----------
check_quota(db, tenant_id) -> QuotaDecision
    Call this in the ingest path (best-effort, never raises).

get_usage(db, tenant_id) -> UsageSummary
    Full summary for GET /v1/billing/usage.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EventCount
from app.services.billing_metering import (
    quota_failure_policy,
    record_metering_failure,
)
from app.services import entitlements_resolver

logger = logging.getLogger(__name__)


# ── public types ──────────────────────────────────────────────────────────────


@dataclass
class QuotaDecision:
    allowed: bool
    current_count: int
    plan_limit: int | None
    overage: int | None
    reason: str


@dataclass
class UsageSummary:
    tenant_id: str
    month: str
    current_count: int
    plan_limit_calls: int | None
    overage_calls: int | None
    plan_slug: str | None
    plan_name: str | None


# ── public functions ──────────────────────────────────────────────────────────


def check_quota(db: Session, tenant_id: str) -> QuotaDecision:
    """Fast quota check — reads event_counts ledger (one index seek).

    Resolver/check errors fail closed by default so quota bypasses cannot
    happen silently. Local/dev may set BILLING_QUOTA_FAILURE_POLICY=alert_only.
    """
    try:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        current = _current_month_count(db, tenant_id, month)
        limit = _plan_call_limit(db, tenant_id)

        if limit is None:
            return QuotaDecision(
                allowed=True,
                current_count=current,
                plan_limit=None,
                overage=None,
                reason="no_limit",
            )

        if current >= limit:
            return QuotaDecision(
                allowed=False,
                current_count=current,
                plan_limit=limit,
                overage=current - limit,
                reason="monthly_quota_exceeded",
            )

        return QuotaDecision(
            allowed=True,
            current_count=current,
            plan_limit=limit,
            overage=None,
            reason="within_quota",
        )
    except Exception as exc:
        logger.exception("billing_quota.check_quota failed tenant=%s", tenant_id)
        record_metering_failure(
            db,
            tenant_id,
            failure_type="quota_check_failed",
            source="billing_quota",
            error=exc,
        )
        if quota_failure_policy() == "alert_only":
            return QuotaDecision(
                allowed=True,
                current_count=0,
                plan_limit=None,
                overage=None,
                reason="check_error_alert_only",
            )
        return QuotaDecision(
            allowed=False,
            current_count=0,
            plan_limit=None,
            overage=None,
            reason="check_error",
        )


def get_usage(db: Session, tenant_id: str) -> UsageSummary:
    """Full usage summary for the current billing month."""
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    current = _current_month_count(db, tenant_id, month)
    limit = _plan_call_limit(db, tenant_id)
    plan_slug, plan_name = _plan_meta(db, tenant_id)

    overage: int | None = None
    if limit is not None and current > limit:
        overage = current - limit

    return UsageSummary(
        tenant_id=tenant_id,
        month=month,
        current_count=current,
        plan_limit_calls=limit,
        overage_calls=overage,
        plan_slug=plan_slug,
        plan_name=plan_name,
    )


# ── helpers ───────────────────────────────────────────────────────────────────


def _current_month_count(db: Session, tenant_id: str, month: str) -> int:
    row = db.execute(
        select(EventCount.event_count).where(
            EventCount.tenant_id == tenant_id,
            EventCount.month == month,
        )
    ).scalar_one_or_none()
    return int(row or 0)


def _plan_call_limit(db: Session, tenant_id: str) -> int | None:
    raw = entitlements_resolver.get(
        db, tenant_id, "events.monthly_quota", default=None
    )
    if raw is None:
        return None
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        return None
    return None if limit < 0 else limit


def _plan_meta(db: Session, tenant_id: str) -> tuple[str | None, str | None]:
    plan_code = entitlements_resolver.get_plan_code(db, tenant_id)
    names = {
        "free": "Free",
        "pilot": "Starter",
        "starter": "Starter",
        "pro": "Pro",
        "plus": "Plus",
        "enterprise": "Enterprise",
    }
    return plan_code, names.get(plan_code, plan_code.title())
