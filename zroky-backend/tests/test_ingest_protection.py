import json

import redis

from app.core.config import get_settings
from app.services import ingest_protection
from app.services.ingest_protection import evaluate_ingest_rate_limit


class FakeRedis:
    def __init__(self, raw: str | bytes | None) -> None:
        self.raw = raw
        self.counts: dict[str, int] = {}

    def get(self, key: str):
        if key == "zroky:owner:rate_limit_overrides":
            return self.raw
        return None

    def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key: str, seconds: int) -> None:
        pass

    def setex(self, key: str, seconds: int, value: str) -> None:
        pass


class BrokenRedis:
    def get(self, key: str):
        raise redis.RedisError("redis unavailable")

    def incr(self, key: str) -> int:
        raise redis.RedisError("redis unavailable")


class CaptureRedis:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def get(self, key: str):
        self.keys.append(key)
        return json.dumps({"ingest_enforce_rate_limit": False}).encode("utf-8")


def test_owner_override_can_disable_ingest_rate_limit(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setattr(ingest_protection, "get_redis_client", lambda: CaptureRedis())

    decision = evaluate_ingest_rate_limit("tenant-disable")

    assert decision.allowed is True
    assert decision.reason == "disabled"
    assert decision.request_count == 0


def test_owner_numeric_overrides_are_used_for_ingest_limits(monkeypatch) -> None:
    get_settings.cache_clear()
    fake_redis = FakeRedis(
        json.dumps(
            {
                "ingest_enforce_rate_limit": True,
                "ingest_soft_limit_rpm": 2,
                "ingest_burst_limit_rpm": 3,
                "ingest_rate_limit_window_seconds": 60,
                "ingest_sustained_breach_threshold": 2,
                "ingest_backpressure_ttl_seconds": 120,
            }
        )
    )
    monkeypatch.setattr(ingest_protection, "get_redis_client", lambda: fake_redis)

    first = evaluate_ingest_rate_limit("tenant-overrides")
    second = evaluate_ingest_rate_limit("tenant-overrides")
    third = evaluate_ingest_rate_limit("tenant-overrides")
    fourth = evaluate_ingest_rate_limit("tenant-overrides")

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is True
    assert fourth.allowed is False
    assert fourth.reason == "burst_limit_exceeded"
    assert fourth.soft_limit_rpm == 2
    assert fourth.burst_limit_rpm == 3


def test_invalid_or_unavailable_override_store_falls_back_to_env(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setattr(ingest_protection, "get_redis_client", lambda: BrokenRedis())
    monkeypatch.setattr(ingest_protection, "_evaluate_with_memory", lambda **kwargs: kwargs)

    result = evaluate_ingest_rate_limit("tenant-fallback")

    assert result["soft_limit"] == get_settings().INGEST_SOFT_LIMIT_RPM
    assert result["burst_limit"] == get_settings().INGEST_BURST_LIMIT_RPM
    assert result["window_seconds"] == get_settings().INGEST_RATE_LIMIT_WINDOW_SECONDS
