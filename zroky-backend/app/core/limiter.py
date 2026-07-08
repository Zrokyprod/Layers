"""Shared rate limiter instance used across the application.

Both main.py and route modules import from here so that a single
Limiter instance is registered on app.state and used in decorators.
This prevents slowapi from creating multiple disconnected instances
that would not share storage and would break FastAPI dependency injection.
"""
from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address


def _build_limiter() -> Limiter:
    # Always use in-memory storage in test mode so tests don't need a Redis
    # server and rate counters are reset between test runs via conftest.py.
    if os.getenv("TESTING", "").lower() == "true":
        disable_limits = os.getenv("ZROKY_DISABLE_SLOWAPI_LIMITS", "").lower() in {
            "1",
            "true",
            "yes",
        }
        return Limiter(
            key_func=get_remote_address,
            storage_uri="memory://",
            enabled=not disable_limits,
        )
    try:
        from app.core.config import get_settings
        settings = get_settings()
        storage_uri: str = (
            getattr(settings, "RATE_LIMIT_STORAGE_URI", None)
            or getattr(settings, "REDIS_URL", None)
            or "memory://"
        )
    except Exception:
        storage_uri = "memory://"
    storage_options: dict[str, float] = {}
    if storage_uri.startswith(("redis://", "rediss://", "redis+unix://")):
        storage_options = {
            "socket_connect_timeout": 0.25,
            "socket_timeout": 1.0,
        }
    return Limiter(
        key_func=get_remote_address,
        storage_uri=storage_uri,
        storage_options=storage_options,
        swallow_errors=True,
        in_memory_fallback_enabled=True,
    )


limiter: Limiter = _build_limiter()
