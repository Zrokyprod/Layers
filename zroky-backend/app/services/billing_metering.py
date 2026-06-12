"""Billing metering helpers for quota checks, event counters, and owner alerts."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import EventCount, ProjectAlert

logger = logging.getLogger(__name__)

METERING_ALERT_CATEGORY = "BILLING_METERING_FAILURE"
METERING_ALERT_DIAGNOSIS_ID = "billing-metering"
_OPEN_ALERT_STATUSES = {"OPEN", "ACKNOWLEDGED"}
_ALLOWED_FAILURE_POLICIES = {"strict", "alert_only"}


@dataclass(frozen=True)
class MeteringHealth:
    state: str
    failure_count: int
    last_failure_at: datetime | None
    last_failure_type: str | None
    failure_policy: str
    detail: str | None = None


def quota_failure_policy() -> str:
    raw = str(get_settings().BILLING_QUOTA_FAILURE_POLICY or "strict").strip().lower()
    return raw if raw in _ALLOWED_FAILURE_POLICIES else "strict"


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def record_metering_failure(
    db: Session,
    tenant_id: str,
    *,
    failure_type: str,
    source: str,
    error: BaseException | str | None = None,
    detail: dict | None = None,
) -> None:
    """Create or update the owner-visible metering failure alert.

    This is intentionally best-effort: a broken database cannot also persist
    the alert, but every recoverable resolver/upsert failure becomes visible in
    project alerts and owner money-path health.
    """
    now = datetime.now(timezone.utc)
    error_text = str(error)[:1000] if error is not None else None
    try:
        row = db.execute(
            select(ProjectAlert).where(
                ProjectAlert.tenant_id == tenant_id,
                ProjectAlert.diagnosis_id == METERING_ALERT_DIAGNOSIS_ID,
                ProjectAlert.category == METERING_ALERT_CATEGORY,
            )
        ).scalar_one_or_none()

        failure_count = 1
        evidence: dict = {}
        if row is not None:
            try:
                evidence = json.loads(row.evidence_json or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                evidence = {}
            failure_count = int(evidence.get("failure_count") or 0) + 1

        evidence = {
            "failure_type": failure_type,
            "source": source,
            "error": error_text,
            "detail": detail or {},
            "failure_count": failure_count,
            "last_failure_at": now.isoformat(),
            "failure_policy": quota_failure_policy(),
        }
        title = "Billing metering failed; quota or usage evidence is degraded."
        if row is None:
            row = ProjectAlert(
                tenant_id=tenant_id,
                diagnosis_id=METERING_ALERT_DIAGNOSIS_ID,
                category=METERING_ALERT_CATEGORY,
                severity="high",
                status="OPEN",
                source=source,
                title=title,
                evidence_json=json.dumps(evidence, separators=(",", ":"), sort_keys=True),
            )
        else:
            row.status = "OPEN"
            row.resolved_at = None
            row.updated_at = now
            row.source = source
            row.title = title
            row.evidence_json = json.dumps(evidence, separators=(",", ":"), sort_keys=True)
        db.add(row)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception(
            "billing_metering.record_failure_failed tenant=%s type=%s",
            tenant_id,
            failure_type,
        )


def increment_event_count(db: Session, tenant_id: str, *, amount: int = 1) -> bool:
    """Atomically increment the current-month event ledger where supported."""
    if amount <= 0:
        return True
    month = current_month()
    now = datetime.now(timezone.utc)
    try:
        bind = db.get_bind()
        dialect = bind.dialect.name if bind is not None else ""
        if dialect == "postgresql":
            stmt = (
                pg_insert(EventCount)
                .values(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    month=month,
                    event_count=amount,
                    last_event_at=now,
                )
                .on_conflict_do_update(
                    constraint="ux_event_counts_tenant_month",
                    set_={
                        "event_count": EventCount.event_count + amount,
                        "last_event_at": now,
                    },
                )
            )
            db.execute(stmt)
        elif dialect == "sqlite":
            stmt = (
                sqlite_insert(EventCount)
                .values(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    month=month,
                    event_count=amount,
                    last_event_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["tenant_id", "month"],
                    set_={
                        "event_count": EventCount.event_count + amount,
                        "last_event_at": now,
                    },
                )
            )
            db.execute(stmt)
        else:
            _increment_event_count_generic(db, tenant_id=tenant_id, month=month, amount=amount, now=now)
        db.commit()
        return True
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception("billing_metering.event_count_increment_failed tenant=%s", tenant_id)
        record_metering_failure(
            db,
            tenant_id,
            failure_type="event_counter_increment_failed",
            source="billing_metering",
            error=exc,
            detail={"month": month, "amount": amount},
        )
        return False


def get_metering_health(db: Session, tenant_id: str) -> MeteringHealth:
    policy = quota_failure_policy()
    alert = db.execute(
        select(ProjectAlert)
        .where(
            ProjectAlert.tenant_id == tenant_id,
            ProjectAlert.category == METERING_ALERT_CATEGORY,
            ProjectAlert.status.in_(_OPEN_ALERT_STATUSES),
        )
        .order_by(ProjectAlert.updated_at.desc(), ProjectAlert.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if alert is None:
        return MeteringHealth(
            state="ok",
            failure_count=0,
            last_failure_at=None,
            last_failure_type=None,
            failure_policy=policy,
            detail="Event metering is healthy.",
        )
    evidence: dict = {}
    try:
        evidence = json.loads(alert.evidence_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        evidence = {}
    last_failure_at = None
    raw_last = evidence.get("last_failure_at")
    if isinstance(raw_last, str) and raw_last:
        try:
            last_failure_at = datetime.fromisoformat(raw_last.replace("Z", "+00:00"))
        except ValueError:
            last_failure_at = None
    return MeteringHealth(
        state="failure",
        failure_count=int(evidence.get("failure_count") or 1),
        last_failure_at=last_failure_at,
        last_failure_type=str(evidence.get("failure_type") or alert.category),
        failure_policy=policy,
        detail=alert.title,
    )


def count_open_metering_failures(db: Session, tenant_ids: list[str]) -> tuple[dict[str, int], dict[str, datetime | None]]:
    if not tenant_ids:
        return {}, {}
    rows = db.execute(
        select(ProjectAlert)
        .where(
            ProjectAlert.tenant_id.in_(tenant_ids),
            ProjectAlert.category == METERING_ALERT_CATEGORY,
            ProjectAlert.status.in_(_OPEN_ALERT_STATUSES),
        )
        .order_by(ProjectAlert.updated_at.desc(), ProjectAlert.created_at.desc())
    ).scalars().all()
    counts: dict[str, int] = {}
    last_seen: dict[str, datetime | None] = {}
    for row in rows:
        evidence: dict = {}
        try:
            evidence = json.loads(row.evidence_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            evidence = {}
        counts[row.tenant_id] = counts.get(row.tenant_id, 0) + int(evidence.get("failure_count") or 1)
        current_last = _aware(row.updated_at) or _aware(row.created_at)
        if row.tenant_id not in last_seen:
            last_seen[row.tenant_id] = current_last
    return counts, last_seen


def _increment_event_count_generic(
    db: Session,
    *,
    tenant_id: str,
    month: str,
    amount: int,
    now: datetime,
) -> None:
    row = db.execute(
        select(EventCount).where(
            EventCount.tenant_id == tenant_id,
            EventCount.month == month,
        )
    ).scalar_one_or_none()
    if row is None:
        row = EventCount(
            id=str(uuid4()),
            tenant_id=tenant_id,
            month=month,
            event_count=amount,
            last_event_at=now,
        )
    else:
        row.event_count = int(row.event_count or 0) + amount
        row.last_event_at = now
    db.add(row)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "METERING_ALERT_CATEGORY",
    "MeteringHealth",
    "count_open_metering_failures",
    "current_month",
    "get_metering_health",
    "increment_event_count",
    "quota_failure_policy",
    "record_metering_failure",
]
