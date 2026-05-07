from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditLog,
    Call,
    DiagnosisFeedback,
    DiagnosisFixWatch,
    DiagnosisJob,
    DiagnosisPullRequest,
    DiagnosisShareToken,
    FixEvent,
    ProjectAlert,
)

DEFAULT_RETENTION_DAYS = 30
MAX_RETENTION_DAYS = 3650
DEFAULT_PURGE_BATCH_SIZE = 500


@dataclass(frozen=True)
class RetentionTableSpec:
    name: str
    model: type[Any]
    tenant_column: str
    timestamp_column: str


RETENTION_TABLE_SPECS: tuple[RetentionTableSpec, ...] = (
    RetentionTableSpec(
        name="diagnosis_feedback",
        model=DiagnosisFeedback,
        tenant_column="tenant_id",
        timestamp_column="created_at",
    ),
    RetentionTableSpec(
        name="diagnosis_share_tokens",
        model=DiagnosisShareToken,
        tenant_column="tenant_id",
        timestamp_column="expires_at",
    ),
    RetentionTableSpec(
        name="project_alerts",
        model=ProjectAlert,
        tenant_column="tenant_id",
        timestamp_column="created_at",
    ),
    RetentionTableSpec(
        name="diagnosis_pull_requests",
        model=DiagnosisPullRequest,
        tenant_column="tenant_id",
        timestamp_column="created_at",
    ),
    RetentionTableSpec(
        name="diagnosis_fix_watches",
        model=DiagnosisFixWatch,
        tenant_column="tenant_id",
        timestamp_column="watch_expires_at",
    ),
    RetentionTableSpec(
        name="fix_events",
        model=FixEvent,
        tenant_column="project_id",
        timestamp_column="timestamp",
    ),
    RetentionTableSpec(
        name="audit_logs",
        model=AuditLog,
        tenant_column="tenant_id",
        timestamp_column="created_at",
    ),
    RetentionTableSpec(
        name="diagnosis_jobs",
        model=DiagnosisJob,
        tenant_column="tenant_id",
        timestamp_column="created_at",
    ),
    RetentionTableSpec(
        name="calls",
        model=Call,
        tenant_column="project_id",
        timestamp_column="created_at",
    ),
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_retention_days(value: int | None, *, default_days: int = DEFAULT_RETENTION_DAYS) -> int:
    try:
        parsed = int(value) if value is not None else int(default_days)
    except (TypeError, ValueError):
        parsed = int(default_days)

    if parsed < 1:
        parsed = int(default_days)

    return min(parsed, MAX_RETENTION_DAYS)


def _count_matching_rows(
    *,
    session: Session,
    model: type[Any],
    tenant_column: str,
    timestamp_column: str,
    tenant_id: str,
    cutoff: datetime,
) -> int:
    tenant_expr = getattr(model, tenant_column)
    timestamp_expr = getattr(model, timestamp_column)
    count_value = session.execute(
        select(func.count())
        .select_from(model)
        .where(tenant_expr == tenant_id, timestamp_expr < cutoff)
    ).scalar_one()
    return int(count_value or 0)


def _count_tenant_rows(
    *,
    session: Session,
    model: type[Any],
    tenant_column: str,
    tenant_id: str,
) -> int:
    tenant_expr = getattr(model, tenant_column)
    count_value = session.execute(
        select(func.count())
        .select_from(model)
        .where(tenant_expr == tenant_id)
    ).scalar_one()
    return int(count_value or 0)


def _purge_table_rows(
    *,
    session: Session,
    spec: RetentionTableSpec,
    tenant_id: str,
    cutoff: datetime,
    batch_size: int,
    dry_run: bool,
) -> int:
    if dry_run:
        return _count_matching_rows(
            session=session,
            model=spec.model,
            tenant_column=spec.tenant_column,
            timestamp_column=spec.timestamp_column,
            tenant_id=tenant_id,
            cutoff=cutoff,
        )

    tenant_expr = getattr(spec.model, spec.tenant_column)
    timestamp_expr = getattr(spec.model, spec.timestamp_column)
    total_deleted = 0

    while True:
        batch_ids = list(
            session.execute(
                select(spec.model.id)
                .where(tenant_expr == tenant_id, timestamp_expr < cutoff)
                .order_by(timestamp_expr.asc(), spec.model.id.asc())
                .limit(batch_size)
            )
            .scalars()
            .all()
        )
        if not batch_ids:
            break

        session.execute(delete(spec.model).where(spec.model.id.in_(batch_ids)))
        session.commit()
        total_deleted += len(batch_ids)

        if len(batch_ids) < batch_size:
            break

    return total_deleted


def _purge_table_all_rows(
    *,
    session: Session,
    spec: RetentionTableSpec,
    tenant_id: str,
    batch_size: int,
    dry_run: bool,
) -> int:
    if dry_run:
        return _count_tenant_rows(
            session=session,
            model=spec.model,
            tenant_column=spec.tenant_column,
            tenant_id=tenant_id,
        )

    tenant_expr = getattr(spec.model, spec.tenant_column)
    total_deleted = 0

    while True:
        batch_ids = list(
            session.execute(
                select(spec.model.id)
                .where(tenant_expr == tenant_id)
                .order_by(spec.model.id.asc())
                .limit(batch_size)
            )
            .scalars()
            .all()
        )
        if not batch_ids:
            break

        session.execute(delete(spec.model).where(spec.model.id.in_(batch_ids)))
        session.commit()
        total_deleted += len(batch_ids)

        if len(batch_ids) < batch_size:
            break

    return total_deleted


def purge_project_retention_data(
    *,
    session: Session,
    tenant_id: str,
    retention_days: int,
    now: datetime | None = None,
    batch_size: int = DEFAULT_PURGE_BATCH_SIZE,
    dry_run: bool = False,
) -> dict[str, Any]:
    effective_days = normalize_retention_days(retention_days)
    effective_batch_size = max(1, int(batch_size))
    effective_now = _as_utc(now or datetime.now(timezone.utc))
    cutoff = effective_now - timedelta(days=effective_days)

    deleted_by_table: dict[str, int] = {}
    total_deleted = 0

    for spec in RETENTION_TABLE_SPECS:
        deleted_count = _purge_table_rows(
            session=session,
            spec=spec,
            tenant_id=tenant_id,
            cutoff=cutoff,
            batch_size=effective_batch_size,
            dry_run=dry_run,
        )
        deleted_by_table[spec.name] = deleted_count
        total_deleted += deleted_count

    return {
        "tenant_id": tenant_id,
        "retention_days": effective_days,
        "cutoff_at": cutoff.isoformat(),
        "dry_run": dry_run,
        "batch_size": effective_batch_size,
        "deleted_by_table": deleted_by_table,
        "total_deleted": total_deleted,
    }


def purge_project_all_data(
    *,
    session: Session,
    tenant_id: str,
    batch_size: int = DEFAULT_PURGE_BATCH_SIZE,
    dry_run: bool = False,
) -> dict[str, Any]:
    effective_batch_size = max(1, int(batch_size))

    deleted_by_table: dict[str, int] = {}
    total_deleted = 0

    for spec in RETENTION_TABLE_SPECS:
        deleted_count = _purge_table_all_rows(
            session=session,
            spec=spec,
            tenant_id=tenant_id,
            batch_size=effective_batch_size,
            dry_run=dry_run,
        )
        deleted_by_table[spec.name] = deleted_count
        total_deleted += deleted_count

    return {
        "tenant_id": tenant_id,
        "dry_run": dry_run,
        "batch_size": effective_batch_size,
        "deleted_by_table": deleted_by_table,
        "total_deleted": total_deleted,
    }
