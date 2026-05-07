"""Monthly partition maintenance for high-volume time-series tables.

Run periodically (e.g. once per day from a Celery beat schedule) to:

1. Create the next month's partition before it is needed (so writes never spill
   into the default partition).
2. Optionally detach and drop partitions older than the retention window.

PostgreSQL only — silently no-ops on other dialects (SQLite tests).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

PARTITIONED_TABLES = ("diagnosis_jobs", "calls", "fix_events")
"""Tables managed by this maintenance job."""

DEFAULT_RETENTION_MONTHS = 12
"""How many months of historical partitions to keep around."""

LOOKAHEAD_MONTHS = 2
"""How many future monthly partitions to pre-create."""


def _is_postgres(session: Session) -> bool:
    return session.bind.dialect.name == "postgresql"


def _month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, months: int) -> date:
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def ensure_future_partitions(
    session: Session,
    *,
    lookahead_months: int = LOOKAHEAD_MONTHS,
    now: datetime | None = None,
) -> list[str]:
    """Create monthly partitions for the next ``lookahead_months`` months.

    Returns the list of partition names that were created or already existed.
    """
    if not _is_postgres(session):
        logger.debug("partition_maintenance: skipping (non-postgres backend)")
        return []

    effective_now = (now or datetime.now(timezone.utc)).date()
    created: list[str] = []

    for offset in range(0, lookahead_months + 1):
        m_start = _add_months(_month_floor(effective_now), offset)
        m_end = _add_months(m_start, 1)
        for table in PARTITIONED_TABLES:
            part_name = f"{table}_{m_start.strftime('%Y_%m')}"
            session.execute(
                text(
                    f'CREATE TABLE IF NOT EXISTS "{part_name}" '
                    f'PARTITION OF "{table}" '
                    f"FOR VALUES FROM ('{m_start.isoformat()}') TO ('{m_end.isoformat()}')"
                )
            )
            created.append(part_name)

    session.commit()
    return created


def drop_expired_partitions(
    session: Session,
    *,
    retention_months: int = DEFAULT_RETENTION_MONTHS,
    now: datetime | None = None,
) -> list[str]:
    """Drop partitions whose upper bound is older than the retention window.

    Returns the names of dropped partitions.
    """
    if not _is_postgres(session):
        return []

    effective_now = (now or datetime.now(timezone.utc)).date()
    cutoff = _add_months(_month_floor(effective_now), -retention_months)
    dropped: list[str] = []

    for table in PARTITIONED_TABLES:
        rows = session.execute(
            text(
                """
                SELECT child.relname AS partition_name,
                       pg_get_expr(child.relpartbound, child.oid) AS bound
                FROM pg_inherits
                JOIN pg_class parent ON parent.oid = pg_inherits.inhparent
                JOIN pg_class child ON child.oid = pg_inherits.inhrelid
                WHERE parent.relname = :table
                """
            ),
            {"table": table},
        ).all()

        for partition_name, bound in rows:
            if bound is None or "DEFAULT" in bound.upper():
                continue
            # bound looks like: FOR VALUES FROM ('2025-01-01') TO ('2025-02-01')
            try:
                upper_str = bound.split("TO (")[-1].split(")")[0].strip("'")
                upper_date = date.fromisoformat(upper_str)
            except (ValueError, IndexError):
                continue
            if upper_date <= cutoff:
                session.execute(text(f'DROP TABLE IF EXISTS "{partition_name}"'))
                dropped.append(partition_name)

    session.commit()
    return dropped


def run_partition_maintenance(
    session: Session,
    *,
    retention_months: int = DEFAULT_RETENTION_MONTHS,
    lookahead_months: int = LOOKAHEAD_MONTHS,
) -> dict[str, list[str]]:
    """Convenience: ensure future partitions and drop expired ones in one call."""
    return {
        "created": ensure_future_partitions(session, lookahead_months=lookahead_months),
        "dropped": drop_expired_partitions(session, retention_months=retention_months),
    }
