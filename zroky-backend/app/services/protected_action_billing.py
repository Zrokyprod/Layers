from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import SystemOfRecordConnectorConfig, UsageMeterCount
from app.services import entitlements_resolver
from app.services.billing_metering import (
    current_month,
    quota_failure_policy,
    record_metering_failure,
)

logger = logging.getLogger(__name__)

METER_PROTECTED_ACTIONS = "protected_actions"
METER_POLICY_CHECKS = "policy_checks"
METER_RUNNER_EXECUTIONS = "runner_executions"
METER_ACTION_RECEIPTS = "action_receipts"
METER_VERIFICATION_CHECKS = "verification_checks"
METER_SOURCE_MUTATIONS = "source_mutations"
METER_ACTIVE_CONNECTORS = "active_connectors"

METER_ENTITLEMENTS: dict[str, str] = {
    METER_PROTECTED_ACTIONS: "actions.protected.monthly_quota",
    METER_POLICY_CHECKS: "actions.policy_checks.monthly_quota",
    METER_RUNNER_EXECUTIONS: "actions.runner_executions.monthly_quota",
    METER_ACTION_RECEIPTS: "actions.receipts.monthly_quota",
    METER_VERIFICATION_CHECKS: "actions.verifications.monthly_quota",
    METER_SOURCE_MUTATIONS: "actions.source_mutations.monthly_quota",
}

CONNECTOR_LIMIT_ENTITLEMENT = "connectors.system_of_record.max"

PROTECTED_ACTION_USAGE_METERS: tuple[str, ...] = (
    METER_PROTECTED_ACTIONS,
    METER_POLICY_CHECKS,
    METER_RUNNER_EXECUTIONS,
    METER_ACTION_RECEIPTS,
    METER_VERIFICATION_CHECKS,
    METER_SOURCE_MUTATIONS,
)


@dataclass(frozen=True)
class UsageMeterDecision:
    meter_key: str
    entitlement_key: str
    allowed: bool
    current_count: int
    requested: int
    projected_count: int
    plan_limit: int | None
    overage: int | None
    reason: str
    plan_code: str | None
    resets_at: str | None


class ProtectedActionBillingError(ValueError):
    pass


class ProtectedActionQuotaExceeded(ProtectedActionBillingError):
    def __init__(self, decision: UsageMeterDecision):
        self.decision = decision
        super().__init__(
            f"Usage meter {decision.meter_key!r} exceeded "
            f"({decision.current_count}/{decision.plan_limit})."
        )


class ProtectedActionMeteringUnavailable(ProtectedActionBillingError):
    def __init__(self, meter_key: str):
        self.meter_key = meter_key
        super().__init__(
            "Billing quota metering is unavailable, so protected action execution is blocked."
        )


def quota_error_detail(exc: ProtectedActionQuotaExceeded) -> dict[str, object]:
    decision = exc.decision
    return {
        "code": "protected_action_quota_exceeded",
        "reason": decision.reason,
        "meter_key": decision.meter_key,
        "entitlement_key": decision.entitlement_key,
        "current_plan": decision.plan_code,
        "used": decision.current_count,
        "requested": decision.requested,
        "projected": decision.projected_count,
        "limit": decision.plan_limit,
        "overage": decision.overage,
        "resets_at": decision.resets_at,
    }


def reserve_usage_meter(
    db: Session,
    tenant_id: str,
    meter_key: str,
    *,
    amount: int = 1,
) -> UsageMeterDecision:
    if amount <= 0:
        return _decision(
            db,
            tenant_id,
            meter_key,
            current=0,
            amount=0,
            limit=None,
            reason="no_usage",
            allowed=True,
        )
    decision = check_usage_meter_quota(db, tenant_id, meter_key, amount=amount)
    settings = get_settings()
    if settings.BILLING_ENFORCE_QUOTA and not decision.allowed:
        raise ProtectedActionQuotaExceeded(decision)

    if not increment_usage_meter(db, tenant_id, meter_key, amount=amount):
        if settings.BILLING_ENFORCE_QUOTA and quota_failure_policy() == "strict":
            raise ProtectedActionMeteringUnavailable(meter_key)
    return decision


def check_usage_meter_quota(
    db: Session,
    tenant_id: str,
    meter_key: str,
    *,
    amount: int = 1,
) -> UsageMeterDecision:
    _require_usage_meter(meter_key)
    try:
        month = current_month()
        current = current_usage_count(db, tenant_id, meter_key, month=month)
        limit = meter_limit(db, tenant_id, meter_key)
        if limit is None or limit < 0:
            return _decision(
                db,
                tenant_id,
                meter_key,
                current=current,
                amount=amount,
                limit=limit,
                allowed=True,
                reason="no_limit" if limit is None else "unlimited",
            )
        projected = current + amount
        if projected > limit:
            allow_overage = _plan_allows_meter_overage(db, tenant_id)
            return _decision(
                db,
                tenant_id,
                meter_key,
                current=current,
                amount=amount,
                limit=limit,
                allowed=allow_overage,
                reason=(
                    "monthly_quota_overage"
                    if allow_overage
                    else "monthly_quota_exceeded"
                ),
            )
        return _decision(
            db,
            tenant_id,
            meter_key,
            current=current,
            amount=amount,
            limit=limit,
            allowed=True,
            reason="within_quota",
        )
    except Exception as exc:
        logger.exception(
            "protected_action_billing.check_usage_meter_quota failed tenant=%s meter=%s",
            tenant_id,
            meter_key,
        )
        record_metering_failure(
            db,
            tenant_id,
            failure_type="protected_action_quota_check_failed",
            source="protected_action_billing",
            error=exc,
            detail={"meter_key": meter_key, "amount": amount},
        )
        allowed = quota_failure_policy() == "alert_only" or not get_settings().BILLING_ENFORCE_QUOTA
        return _decision(
            db,
            tenant_id,
            meter_key,
            current=0,
            amount=amount,
            limit=None,
            allowed=allowed,
            reason="check_error_alert_only" if allowed else "check_error",
        )


def increment_usage_meter(
    db: Session,
    tenant_id: str,
    meter_key: str,
    *,
    amount: int = 1,
) -> bool:
    _require_usage_meter(meter_key)
    if amount <= 0:
        return True
    month = current_month()
    now = datetime.now(timezone.utc)
    try:
        bind = db.get_bind()
        dialect = bind.dialect.name if bind is not None else ""
        if dialect == "postgresql":
            pg_stmt = (
                pg_insert(UsageMeterCount)
                .values(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    month=month,
                    meter_key=meter_key,
                    usage_count=amount,
                    last_usage_at=now,
                )
                .on_conflict_do_update(
                    constraint="ux_usage_meter_counts_tenant_month_meter",
                    set_={
                        "usage_count": UsageMeterCount.usage_count + amount,
                        "last_usage_at": now,
                    },
                )
            )
            db.execute(pg_stmt)
        elif dialect == "sqlite":
            sqlite_stmt = (
                sqlite_insert(UsageMeterCount)
                .values(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    month=month,
                    meter_key=meter_key,
                    usage_count=amount,
                    last_usage_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["tenant_id", "month", "meter_key"],
                    set_={
                        "usage_count": UsageMeterCount.usage_count + amount,
                        "last_usage_at": now,
                    },
                )
            )
            db.execute(sqlite_stmt)
        else:
            row = db.execute(
                select(UsageMeterCount).where(
                    UsageMeterCount.tenant_id == tenant_id,
                    UsageMeterCount.month == month,
                    UsageMeterCount.meter_key == meter_key,
                )
            ).scalar_one_or_none()
            if row is None:
                row = UsageMeterCount(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    month=month,
                    meter_key=meter_key,
                    usage_count=amount,
                    last_usage_at=now,
                )
            else:
                row.usage_count = int(row.usage_count or 0) + amount
                row.last_usage_at = now
            db.add(row)
        db.flush()
        return True
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception(
            "protected_action_billing.increment_usage_meter failed tenant=%s meter=%s",
            tenant_id,
            meter_key,
        )
        record_metering_failure(
            db,
            tenant_id,
            failure_type="protected_action_meter_increment_failed",
            source="protected_action_billing",
            error=exc,
            detail={"meter_key": meter_key, "month": month, "amount": amount},
        )
        return False


def current_usage_count(
    db: Session,
    tenant_id: str,
    meter_key: str,
    *,
    month: str | None = None,
) -> int:
    _require_usage_meter(meter_key)
    row = db.execute(
        select(UsageMeterCount.usage_count).where(
            UsageMeterCount.tenant_id == tenant_id,
            UsageMeterCount.month == (month or current_month()),
            UsageMeterCount.meter_key == meter_key,
        )
    ).scalar_one_or_none()
    return int(row or 0)


def meter_limit(db: Session, tenant_id: str, meter_key: str) -> int | None:
    key = _require_usage_meter(meter_key)
    raw = entitlements_resolver.get(db, tenant_id, key, default=None)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def usage_meter_decisions(db: Session, tenant_id: str) -> dict[str, UsageMeterDecision]:
    return {
        meter_key: check_usage_meter_quota(db, tenant_id, meter_key, amount=0)
        for meter_key in PROTECTED_ACTION_USAGE_METERS
    }


def active_system_of_record_connector_count(db: Session, tenant_id: str) -> int:
    return int(
        db.execute(
            select(func.count(SystemOfRecordConnectorConfig.id)).where(
                SystemOfRecordConnectorConfig.project_id == tenant_id,
                SystemOfRecordConnectorConfig.is_active.is_(True),
            )
        ).scalar_one()
        or 0
    )


def system_of_record_connector_limit(db: Session, tenant_id: str) -> int | None:
    raw = entitlements_resolver.get(
        db, tenant_id, CONNECTOR_LIMIT_ENTITLEMENT, default=None
    )
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def enforce_system_of_record_connector_limit(
    db: Session,
    tenant_id: str,
    *,
    connector_type: str,
) -> UsageMeterDecision:
    limit = system_of_record_connector_limit(db, tenant_id)
    current = active_system_of_record_connector_count(db, tenant_id)
    existing = db.execute(
        select(SystemOfRecordConnectorConfig).where(
            SystemOfRecordConnectorConfig.project_id == tenant_id,
            SystemOfRecordConnectorConfig.connector_type == connector_type,
        )
    ).scalar_one_or_none()
    adds_connector = existing is None or not bool(existing.is_active)
    projected = current + (1 if adds_connector else 0)
    allowed = limit is None or limit < 0 or projected <= limit
    decision = _connector_decision(
        db,
        tenant_id,
        current=current,
        projected=projected,
        limit=limit,
        allowed=allowed,
        reason="within_quota" if allowed else "connector_quota_exceeded",
    )
    if get_settings().BILLING_ENFORCE_QUOTA and not allowed:
        raise ProtectedActionQuotaExceeded(decision)
    return decision


def active_connector_decision(db: Session, tenant_id: str) -> UsageMeterDecision:
    current = active_system_of_record_connector_count(db, tenant_id)
    limit = system_of_record_connector_limit(db, tenant_id)
    return _connector_decision(
        db,
        tenant_id,
        current=current,
        projected=current,
        limit=limit,
        allowed=limit is None or limit < 0 or current <= limit,
        reason="no_limit" if limit is None else "unlimited" if limit < 0 else "within_quota",
    )


def _require_usage_meter(meter_key: str) -> str:
    if meter_key not in METER_ENTITLEMENTS:
        raise ValueError(
            "meter_key must be one of: " + ", ".join(sorted(METER_ENTITLEMENTS))
        )
    return METER_ENTITLEMENTS[meter_key]


def _decision(
    db: Session,
    tenant_id: str,
    meter_key: str,
    *,
    current: int,
    amount: int,
    limit: int | None,
    allowed: bool,
    reason: str,
) -> UsageMeterDecision:
    projected = current + amount
    overage = None
    if limit is not None and limit >= 0 and projected > limit:
        overage = projected - limit
    return UsageMeterDecision(
        meter_key=meter_key,
        entitlement_key=METER_ENTITLEMENTS[meter_key],
        allowed=allowed,
        current_count=current,
        requested=amount,
        projected_count=projected,
        plan_limit=limit,
        overage=overage,
        reason=reason,
        plan_code=_plan_code(db, tenant_id),
        resets_at=_month_reset_date(),
    )


def _connector_decision(
    db: Session,
    tenant_id: str,
    *,
    current: int,
    projected: int,
    limit: int | None,
    allowed: bool,
    reason: str,
) -> UsageMeterDecision:
    overage = None
    if limit is not None and limit >= 0 and projected > limit:
        overage = projected - limit
    return UsageMeterDecision(
        meter_key=METER_ACTIVE_CONNECTORS,
        entitlement_key=CONNECTOR_LIMIT_ENTITLEMENT,
        allowed=allowed,
        current_count=current,
        requested=max(0, projected - current),
        projected_count=projected,
        plan_limit=limit,
        overage=overage,
        reason=reason,
        plan_code=_plan_code(db, tenant_id),
        resets_at=None,
    )


def _plan_code(db: Session, tenant_id: str) -> str | None:
    try:
        return entitlements_resolver.get_plan_code(db, tenant_id)
    except Exception:
        return None


def _plan_allows_meter_overage(db: Session, tenant_id: str) -> bool:
    plan_code = (_plan_code(db, tenant_id) or "").strip().lower()
    return bool(plan_code and plan_code != "free")


def _month_reset_date() -> str:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return end.date().isoformat()
