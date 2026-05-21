"""ClickHouse client with availability check and Postgres fallback signalling.

Usage:
    from app.services.clickhouse_client import get_clickhouse_client, ClickHouseUnavailable

    ch = get_clickhouse_client()
    if ch is None:
        raise ClickHouseUnavailable()
    rows = ch.query("SELECT ...")
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ClickHouseUnavailable(Exception):
    """Raised when ClickHouse is not configured or unreachable."""


_client: Any = None
_checked: bool = False


def get_clickhouse_client() -> Any | None:
    """Return a connected clickhouse-driver Client, or None if unavailable.

    The first call probes the connection; subsequent calls return the cached
    instance (or None if the probe failed).
    """
    global _client, _checked
    if _checked:
        return _client
    _checked = True

    settings = get_settings()
    if not settings.CLICKHOUSE_ENABLED or not settings.CLICKHOUSE_URL:
        return None

    try:
        from clickhouse_driver import Client  # type: ignore[import]

        host = settings.CLICKHOUSE_URL.rstrip("/").removeprefix("http://").removeprefix("https://")
        client = Client(
            host=host,
            database=settings.CLICKHOUSE_DATABASE,
            user=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
            connect_timeout=3,
            send_receive_timeout=10,
        )
        client.execute("SELECT 1")
        _client = client
        logger.info("ClickHouse connected: %s/%s", host, settings.CLICKHOUSE_DATABASE)
    except Exception as exc:
        logger.warning("ClickHouse unavailable (%s) — falling back to Postgres", exc)
        _client = None

    return _client


def reset_client() -> None:
    """Force re-probe on next call (used in tests)."""
    global _client, _checked
    _client = None
    _checked = False
