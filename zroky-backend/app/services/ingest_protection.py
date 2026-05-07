from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock

import redis

from app.core.config import get_settings
from app.services.redis_client import get_redis_client

_MEMORY_LOCK = Lock()
_MEMORY_WINDOW_COUNTS: dict[tuple[str, int], int] = {}
_MEMORY_BREACH: dict[str, tuple[int, float]] = {}
_MEMORY_BACKPRESSURE_UNTIL: dict[str, float] = {}


@dataclass
class IngestRateLimitDecision:
    allowed: bool
    retry_after_seconds: int | None
    reason: str
    request_count: int
    soft_limit_rpm: int
    burst_limit_rpm: int
    backpressure_active: bool
    backpressure_activated: bool


def _window_and_retry(now_ts: float, window_seconds: int) -> tuple[int, int]:
    window_id = int(now_ts // window_seconds)
    offset = int(now_ts % window_seconds)
    retry_after = max(1, window_seconds - offset)
    return window_id, retry_after


def _cleanup_memory_state(current_window: int, now_ts: float) -> None:
    stale_keys = [
        key
        for key in _MEMORY_WINDOW_COUNTS
        if key[1] < current_window - 2
    ]
    for key in stale_keys:
        _MEMORY_WINDOW_COUNTS.pop(key, None)

    expired_backpressure = [tenant for tenant, until in _MEMORY_BACKPRESSURE_UNTIL.items() if until <= now_ts]
    for tenant in expired_backpressure:
        _MEMORY_BACKPRESSURE_UNTIL.pop(tenant, None)

    expired_breach = [tenant for tenant, (_, expiry) in _MEMORY_BREACH.items() if expiry <= now_ts]
    for tenant in expired_breach:
        _MEMORY_BREACH.pop(tenant, None)


def _evaluate_with_memory(
    *,
    tenant_id: str,
    now_ts: float,
    soft_limit: int,
    burst_limit: int,
    window_seconds: int,
    sustained_threshold: int,
    backpressure_ttl_seconds: int,
) -> IngestRateLimitDecision:
    with _MEMORY_LOCK:
        window_id, retry_after = _window_and_retry(now_ts, window_seconds)
        _cleanup_memory_state(window_id, now_ts)

        backpressure_active = _MEMORY_BACKPRESSURE_UNTIL.get(tenant_id, 0.0) > now_ts
        key = (tenant_id, window_id)
        request_count = _MEMORY_WINDOW_COUNTS.get(key, 0) + 1
        _MEMORY_WINDOW_COUNTS[key] = request_count

        effective_limit = soft_limit if backpressure_active else burst_limit
        if request_count <= effective_limit:
            return IngestRateLimitDecision(
                allowed=True,
                retry_after_seconds=None,
                reason="allowed",
                request_count=request_count,
                soft_limit_rpm=soft_limit,
                burst_limit_rpm=burst_limit,
                backpressure_active=backpressure_active,
                backpressure_activated=False,
            )

        breach_count, breach_expiry = _MEMORY_BREACH.get(tenant_id, (0, 0.0))
        if breach_expiry <= now_ts:
            breach_count = 0

        breach_count += 1
        _MEMORY_BREACH[tenant_id] = (breach_count, now_ts + backpressure_ttl_seconds)

        backpressure_activated = False
        if breach_count >= sustained_threshold and not backpressure_active:
            _MEMORY_BACKPRESSURE_UNTIL[tenant_id] = now_ts + backpressure_ttl_seconds
            backpressure_active = True
            backpressure_activated = True

        return IngestRateLimitDecision(
            allowed=False,
            retry_after_seconds=retry_after,
            reason="backpressure_active" if backpressure_active else "burst_limit_exceeded",
            request_count=request_count,
            soft_limit_rpm=soft_limit,
            burst_limit_rpm=burst_limit,
            backpressure_active=backpressure_active,
            backpressure_activated=backpressure_activated,
        )


def _evaluate_with_redis(
    *,
    tenant_id: str,
    now_ts: float,
    soft_limit: int,
    burst_limit: int,
    window_seconds: int,
    sustained_threshold: int,
    backpressure_ttl_seconds: int,
) -> IngestRateLimitDecision:
    window_id, retry_after = _window_and_retry(now_ts, window_seconds)
    client = get_redis_client()

    backpressure_key = f"zroky:ingest:backpressure:{tenant_id}"
    counter_key = f"zroky:ingest:req:{tenant_id}:{window_id}"
    breach_key = f"zroky:ingest:breach:{tenant_id}"

    backpressure_active = bool(client.get(backpressure_key))

    request_count = int(client.incr(counter_key))
    if request_count == 1:
        client.expire(counter_key, window_seconds * 2)

    effective_limit = soft_limit if backpressure_active else burst_limit
    if request_count <= effective_limit:
        return IngestRateLimitDecision(
            allowed=True,
            retry_after_seconds=None,
            reason="allowed",
            request_count=request_count,
            soft_limit_rpm=soft_limit,
            burst_limit_rpm=burst_limit,
            backpressure_active=backpressure_active,
            backpressure_activated=False,
        )

    breach_count = int(client.incr(breach_key))
    client.expire(breach_key, backpressure_ttl_seconds)

    backpressure_activated = False
    if breach_count >= sustained_threshold and not backpressure_active:
        client.setex(backpressure_key, backpressure_ttl_seconds, "1")
        backpressure_active = True
        backpressure_activated = True

    return IngestRateLimitDecision(
        allowed=False,
        retry_after_seconds=retry_after,
        reason="backpressure_active" if backpressure_active else "burst_limit_exceeded",
        request_count=request_count,
        soft_limit_rpm=soft_limit,
        burst_limit_rpm=burst_limit,
        backpressure_active=backpressure_active,
        backpressure_activated=backpressure_activated,
    )


def evaluate_ingest_rate_limit(tenant_id: str) -> IngestRateLimitDecision:
    settings = get_settings()
    if not settings.INGEST_ENFORCE_RATE_LIMIT:
        return IngestRateLimitDecision(
            allowed=True,
            retry_after_seconds=None,
            reason="disabled",
            request_count=0,
            soft_limit_rpm=settings.INGEST_SOFT_LIMIT_RPM,
            burst_limit_rpm=settings.INGEST_BURST_LIMIT_RPM,
            backpressure_active=False,
            backpressure_activated=False,
        )

    now_ts = time.time()
    soft_limit = max(1, settings.INGEST_SOFT_LIMIT_RPM)
    burst_limit = max(soft_limit, settings.INGEST_BURST_LIMIT_RPM)
    window_seconds = max(1, settings.INGEST_RATE_LIMIT_WINDOW_SECONDS)
    sustained_threshold = max(1, settings.INGEST_SUSTAINED_BREACH_THRESHOLD)
    backpressure_ttl_seconds = max(window_seconds, settings.INGEST_BACKPRESSURE_TTL_SECONDS)

    try:
        return _evaluate_with_redis(
            tenant_id=tenant_id,
            now_ts=now_ts,
            soft_limit=soft_limit,
            burst_limit=burst_limit,
            window_seconds=window_seconds,
            sustained_threshold=sustained_threshold,
            backpressure_ttl_seconds=backpressure_ttl_seconds,
        )
    except redis.RedisError:
        return _evaluate_with_memory(
            tenant_id=tenant_id,
            now_ts=now_ts,
            soft_limit=soft_limit,
            burst_limit=burst_limit,
            window_seconds=window_seconds,
            sustained_threshold=sustained_threshold,
            backpressure_ttl_seconds=backpressure_ttl_seconds,
        )
