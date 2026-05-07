"""
UTC-aware DateTime SQLAlchemy type.

Fixes the SQLite timezone bug where ``DateTime(timezone=True)`` is a no-op:
SQLite stores datetimes as naive ISO strings and returns naive ``datetime``
objects, while PostgreSQL returns timezone-aware ones. This inconsistency
forces every consumer to defensively check ``dt.tzinfo`` before comparing
or arithmetic-ing two datetimes — easy to forget and a frequent source of
``TypeError: can't compare offset-naive and offset-aware datetimes``.

``UTCDateTime`` normalizes both directions:

* On bind (write): any incoming naive datetime is assumed UTC; aware
  datetimes are converted to UTC. SQLite is given a naive UTC datetime
  (it can't store offsets); PostgreSQL gets the aware UTC datetime.
* On result (read): naive datetimes coming back are tagged as UTC,
  aware ones are converted to UTC. The application **always** sees an
  aware UTC ``datetime``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """SQLAlchemy column type that always reads/writes UTC-aware datetimes."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"UTCDateTime expected datetime, got {type(value).__name__}")

        if value.tzinfo is None:
            # Treat naive input as UTC (legacy code may pass naive datetimes)
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)

        # SQLite cannot store tz offsets — strip tzinfo (it's already UTC)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)

        return value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value  # pragma: no cover — driver should always return datetime

        if value.tzinfo is None:
            # SQLite returns naive datetimes; we stored them as UTC
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
