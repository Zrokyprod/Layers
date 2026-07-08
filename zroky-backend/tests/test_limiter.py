"""Tests for rate limiter storage configuration."""

from __future__ import annotations


def test_redis_limiter_uses_short_timeouts_and_memory_fallback(monkeypatch):
    import slowapi.extension as slowapi_extension
    from limits.storage.memory import MemoryStorage

    from app.core import config
    from app.core import limiter as limiter_module

    captured: dict[str, object] = {}

    def fake_storage_from_string(uri: str, **options: object) -> MemoryStorage:
        captured["uri"] = uri
        captured["options"] = options
        return MemoryStorage("memory://")

    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("RATE_LIMIT_STORAGE_URI", "redis://redis.example.test:6379/0")
    config.get_settings.cache_clear()
    monkeypatch.setattr(slowapi_extension, "storage_from_string", fake_storage_from_string)

    test_limiter = limiter_module._build_limiter()

    assert captured["uri"] == "redis://redis.example.test:6379/0"
    assert captured["options"] == {
        "socket_connect_timeout": 0.25,
        "socket_timeout": 1.0,
    }
    assert test_limiter._in_memory_fallback_enabled is True
    assert test_limiter._swallow_errors is True

    config.get_settings.cache_clear()
