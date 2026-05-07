"""
Shared pytest environment setup.
Sets environment variables BEFORE any app module is imported.
conftest.py is loaded by pytest before test modules, so this runs first.
"""
import os

import pytest

# Signal the app that we are in test mode. The rate limiter checks this to
# use memory:// storage instead of trying to connect to Redis.
os.environ["TESTING"] = "true"

# Common test defaults — each test module may override these further with
# os.environ.setdefault() for module-specific values.
os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test_shared.db")
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-key-for-auth-tests")
os.environ.setdefault("ALLOW_PROJECT_HEADER_CONTEXT", "true")
os.environ.setdefault("REQUIRE_PROVISIONING_TOKEN", "false")

# Clear the settings lru_cache so any subsequent get_settings() call reads
# the env vars we just set above instead of a cached production value.
try:
    from app.core.config import get_settings
    get_settings.cache_clear()
except Exception:
    pass


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the in-memory rate limiter and token store between every test."""
    from app.core.limiter import limiter
    from app.services import token_store as ts
    storage = limiter._storage
    if hasattr(storage, "reset"):
        storage.reset()
    ts._mem_clear()
    yield
    if hasattr(storage, "reset"):
        storage.reset()
    ts._mem_clear()
