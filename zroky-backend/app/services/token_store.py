"""Thin token store backed by CacheService (Redis in production, in-process memory otherwise).

Used for short-lived tokens that must survive a single process restart:
  - Password-reset tokens  (key prefix: pw_reset:)
  - JWT blacklist entries   (key prefix: jwt_blacklisted:)

In tests (TESTING=true) or when Redis is unreachable, falls back to an
in-process dict so the test suite never needs a live Redis server.
"""
import os
import time
from typing import Optional

from app.services.cache_service import CacheService

# ---------------------------------------------------------------------------
# In-process fallback (legacy — kept for direct internal use)
# ---------------------------------------------------------------------------

_mem_store: dict[str, tuple[str, float]] = {}


def _mem_set(key: str, value: str, ttl_seconds: int) -> None:
    _mem_store[key] = (value, time.monotonic() + ttl_seconds)


def _mem_get(key: str) -> Optional[str]:
    entry = _mem_store.get(key)
    if entry is None:
        return None
    value, expiry = entry
    if time.monotonic() > expiry:
        _mem_store.pop(key, None)
        return None
    return value


def _mem_delete(key: str) -> None:
    _mem_store.pop(key, None)


def _mem_clear() -> None:
    """Used by the test suite to reset state between tests."""
    _mem_store.clear()


# ---------------------------------------------------------------------------
# Unified cache-backed API
# ---------------------------------------------------------------------------

_cache = CacheService("tokens")


def set_with_ttl(key: str, value: str, ttl_seconds: int) -> None:
    _cache.set(key, value, ttl_seconds=ttl_seconds)


def get(key: str) -> Optional[str]:
    return _cache.get(key)


def delete(key: str) -> None:
    _cache.delete(key)
