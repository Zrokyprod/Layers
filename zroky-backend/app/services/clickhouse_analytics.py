"""ClickHouse-backed analytics helpers for /cost and /issues.

Each function tries ClickHouse first.  On failure (unavailable, timeout, etc.)
it returns None so the caller can fall back to the Postgres path and set
`data_source="postgres_fallback"` in the response.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def get_cost_daily_from_ch(
    project_id: str,
    *,
    days: int = 14,
) -> list[dict[str, Any]] | None:
    """Return daily cost roll-ups from ClickHouse, or None if unavailable.

    Each row: {day: str, calls: int, total_tokens: int, cost_usd: float}
    """
    from app.services.clickhouse_client import get_clickhouse_client

    ch = get_clickhouse_client()
    if ch is None:
        return None

    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        rows = ch.execute(
            """
            SELECT
                toString(day)  AS day,
                sum(calls)     AS calls,
                sum(total_tokens) AS total_tokens,
                sum(cost_usd)  AS cost_usd
            FROM zroky.cost_daily
            WHERE project_id = %(project_id)s
              AND day >= %(since)s
            GROUP BY day
            ORDER BY day
            """,
            {"project_id": project_id, "since": since},
        )
        return [
            {
                "day": r[0],
                "calls": int(r[1]),
                "total_tokens": int(r[2]),
                "cost_usd": float(r[3]),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("ch cost_daily query failed: %s", exc)
        return None


def get_issues_topk_from_ch(
    project_id: str,
    *,
    days: int = 7,
    limit: int = 20,
) -> list[dict[str, Any]] | None:
    """Return top-K issues by failure_code from ClickHouse, or None if unavailable.

    Each row: {failure_code: str, occurrences: int, day: str}
    """
    from app.services.clickhouse_client import get_clickhouse_client

    ch = get_clickhouse_client()
    if ch is None:
        return None

    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        rows = ch.execute(
            """
            SELECT
                failure_code,
                sum(occurrences) AS total_occurrences,
                toString(max(day)) AS latest_day
            FROM zroky.issues_topk
            WHERE project_id = %(project_id)s
              AND day >= %(since)s
              AND failure_code != ''
            GROUP BY failure_code
            ORDER BY total_occurrences DESC
            LIMIT %(limit)s
            """,
            {"project_id": project_id, "since": since, "limit": limit},
        )
        return [
            {
                "failure_code": r[0],
                "occurrences": int(r[1]),
                "latest_day": r[2],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("ch issues_topk query failed: %s", exc)
        return None
