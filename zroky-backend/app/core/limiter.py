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
        return Limiter(key_func=get_remote_address, storage_uri="memory://")
    try:
        from app.core.config import get_settings
        settings = get_settings()
        storage_uri: str = getattr(settings, "REDIS_URL", None) or "memory://"
    except Exception:
        storage_uri = "memory://"
    return Limiter(key_func=get_remote_address, storage_uri=storage_uri)


limiter: Limiter = _build_limiter()
