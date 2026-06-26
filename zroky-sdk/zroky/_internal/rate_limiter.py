# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Client-side rate management.

Prevents 429s by tracking per-provider/model rate limits and waiting
before sending requests that would exceed them.

Architecture:
  - Dual token-bucket per key: one for RPM (requests), one for TPM (tokens).
  - Continuous refill: tokens drip back at ``capacity / 60`` per second.
  - Auto-learn: response headers update bucket capacity on the fly.
  - Pre-flight wait: ``acquire()`` blocks until capacity is available
    (with timeout), so the SDK never sends a request that will be rejected.
  - Thread-safe: one ``threading.Lock`` per bucket pair.
  - Async: ``acquire_async`` uses ``asyncio.sleep`` instead of ``time.sleep``.
  - Graceful passthrough: if no limits are known, calls are never blocked.
"""
from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

# Hard ceiling to avoid a misconfigured header stalling the SDK forever.
_MAX_WAIT_SECONDS: float = 120.0

# Avoid pretending sub-tick sleeps are enforceable. On Windows especially,
# time.sleep(0.01) can overshoot heavily under load; for tiny caller
# deadlines the SDK should fail open immediately.
_MIN_BLOCKING_WAIT_SECONDS: float = 0.05

# Minimum bucket capacity we'll accept from headers (sanity floor).
_MIN_CAPACITY: int = 1


# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------

class _TokenBucket:
    """Continuous-refill token bucket.

    Tokens are refilled at a constant rate (``capacity / period_seconds``).
    ``try_acquire(n)`` returns the wait time (seconds) before *n* tokens will
    be available. ``consume(n)`` removes tokens immediately.
    """

    __slots__ = ("capacity", "tokens", "refill_rate", "_last_refill")

    def __init__(self, capacity: float, period_seconds: float = 60.0) -> None:
        self.capacity = capacity
        self.tokens = capacity  # start full
        self.refill_rate = capacity / period_seconds if period_seconds > 0 else float("inf")
        self._last_refill = time.monotonic()

    # -- internal ----------------------------------------------------------

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self._last_refill = now

    # -- public API --------------------------------------------------------

    def wait_time(self, n: float = 1) -> float:
        """Seconds until *n* tokens become available (0 if ready now)."""
        self._refill()
        if self.tokens >= n:
            return 0.0
        deficit = n - self.tokens
        if self.refill_rate <= 0:
            return float("inf")
        return deficit / self.refill_rate

    def consume(self, n: float = 1) -> None:
        """Remove *n* tokens.  May go negative (debt that refill recovers)."""
        self._refill()
        self.tokens -= n

    def update_capacity(self, new_capacity: float, period_seconds: float = 60.0) -> None:
        """Change capacity without resetting current token level."""
        if new_capacity < _MIN_CAPACITY:
            return
        self._refill()
        self.capacity = new_capacity
        self.refill_rate = new_capacity / period_seconds if period_seconds > 0 else float("inf")
        # clamp existing tokens to new capacity
        self.tokens = min(self.tokens, self.capacity)

    def set_remaining(self, remaining: float) -> None:
        """Override current token level from a header value."""
        self._refill()
        self.tokens = min(remaining, self.capacity)


# ---------------------------------------------------------------------------
# Bucket pair (RPM + TPM) per key
# ---------------------------------------------------------------------------

@dataclass
class BucketPair:
    """Holds the RPM and TPM buckets for a single provider/model key."""
    rpm: _TokenBucket
    tpm: _TokenBucket
    lock: threading.Lock = field(default_factory=threading.Lock)

    @staticmethod
    def from_limits(rpm: int | None = None, tpm: int | None = None) -> BucketPair:
        rpm_bucket = _TokenBucket(float(rpm), 60.0) if rpm else _TokenBucket(float("inf"), 60.0)
        tpm_bucket = _TokenBucket(float(tpm), 60.0) if tpm else _TokenBucket(float("inf"), 60.0)
        return BucketPair(rpm=rpm_bucket, tpm=tpm_bucket)


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

_HEADER_MAP_REQUEST = {
    # OpenAI
    "x-ratelimit-remaining-requests": "remaining",
    "x-ratelimit-limit-requests": "limit",
    "x-ratelimit-reset-requests": "reset",
    # Anthropic
    "anthropic-ratelimit-requests-remaining": "remaining",
    "anthropic-ratelimit-requests-limit": "limit",
    "anthropic-ratelimit-requests-reset": "reset",
}

_HEADER_MAP_TOKEN = {
    # OpenAI
    "x-ratelimit-remaining-tokens": "remaining",
    "x-ratelimit-limit-tokens": "limit",
    "x-ratelimit-reset-tokens": "reset",
    # Anthropic
    "anthropic-ratelimit-tokens-remaining": "remaining",
    "anthropic-ratelimit-tokens-limit": "limit",
    "anthropic-ratelimit-tokens-reset": "reset",
}


@dataclass
class _ParsedHeaders:
    req_remaining: float | None = None
    req_limit: float | None = None
    tok_remaining: float | None = None
    tok_limit: float | None = None


def _parse_rate_headers(response: Any) -> _ParsedHeaders:
    """Extract rate-limit metadata from a provider response object."""
    headers = getattr(response, "headers", None)
    if headers is None:
        # Some providers wrap response in .response attribute
        inner = getattr(response, "response", None)
        if inner is not None:
            headers = getattr(inner, "headers", None)
    if headers is None:
        return _ParsedHeaders()

    parsed = _ParsedHeaders()
    for hdr_name, role in _HEADER_MAP_REQUEST.items():
        val = _safe_header(headers, hdr_name)
        if val is None:
            continue
        if role == "remaining":
            parsed.req_remaining = val
        elif role == "limit":
            parsed.req_limit = val

    for hdr_name, role in _HEADER_MAP_TOKEN.items():
        val = _safe_header(headers, hdr_name)
        if val is None:
            continue
        if role == "remaining":
            parsed.tok_remaining = val
        elif role == "limit":
            parsed.tok_limit = val

    return parsed


def _safe_header(headers: Any, name: str) -> float | None:
    """Safely extract a numeric header value."""
    try:
        raw = headers.get(name)
    except Exception:  # noqa: BLE001
        return None
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Rate limiter registry
# ---------------------------------------------------------------------------

class RateLimiter:
    """Global registry of per-key rate-limit buckets.

    Usage::

        limiter = RateLimiter()
        limiter.configure("openai/gpt-4o", rpm=500, tpm=30_000)

        # Before a call:
        limiter.acquire("openai/gpt-4o", estimated_tokens=1500)

        # After a call:
        limiter.update_from_response("openai/gpt-4o", response, actual_tokens=2000)
    """

    def __init__(self) -> None:
        self._buckets: dict[str, BucketPair] = {}
        self._global_lock = threading.Lock()

    # -- configuration -----------------------------------------------------

    def configure(self, key: str, *, rpm: int | None = None, tpm: int | None = None) -> None:
        """Set or update rate limits for a provider/model key."""
        with self._global_lock:
            existing = self._buckets.get(key)
            if existing is not None:
                with existing.lock:
                    if rpm is not None:
                        existing.rpm.update_capacity(float(rpm))
                    if tpm is not None:
                        existing.tpm.update_capacity(float(tpm))
            else:
                self._buckets[key] = BucketPair.from_limits(rpm, tpm)

    def configure_all(self, limits: dict[str, dict[str, int]]) -> None:
        """Bulk-configure from a mapping like ``{"openai/gpt-4o": {"rpm": 500, "tpm": 30000}}``."""
        for key, spec in limits.items():
            self.configure(key, rpm=spec.get("rpm"), tpm=spec.get("tpm"))

    # -- bucket access (internal) ------------------------------------------

    def _get_or_create(self, key: str) -> BucketPair:
        pair = self._buckets.get(key)
        if pair is not None:
            return pair
        with self._global_lock:
            # double-check after acquiring lock
            pair = self._buckets.get(key)
            if pair is not None:
                return pair
            pair = BucketPair.from_limits()  # infinite = passthrough
            self._buckets[key] = pair
            return pair

    # -- sync acquire ------------------------------------------------------

    def acquire(
        self,
        key: str,
        *,
        estimated_tokens: int = 0,
        timeout: float = _MAX_WAIT_SECONDS,
        verbose: bool = False,
    ) -> float:
        """Block until capacity is available.  Returns total wait time in seconds.

        If no limits are known for *key*, returns immediately (0.0).
        """
        pair = self._get_or_create(key)
        total_waited = 0.0

        while True:
            with pair.lock:
                rpm_wait = pair.rpm.wait_time(1)
                tpm_wait = pair.tpm.wait_time(float(estimated_tokens)) if estimated_tokens > 0 else 0.0
                wait = max(rpm_wait, tpm_wait)

                if wait <= 0:
                    pair.rpm.consume(1)
                    if estimated_tokens > 0:
                        pair.tpm.consume(float(estimated_tokens))
                    return total_waited

            # Need to wait — release the lock while sleeping
            wait = min(wait, timeout - total_waited)
            if wait <= 0 or wait < _MIN_BLOCKING_WAIT_SECONDS:
                # Timeout exhausted — let the call through anyway
                with pair.lock:
                    pair.rpm.consume(1)
                    if estimated_tokens > 0:
                        pair.tpm.consume(float(estimated_tokens))
                if verbose:
                    _logger.warning(
                        "[ZROKY] Rate limiter timeout for %s after %.1fs — sending anyway",
                        key, total_waited,
                    )
                return total_waited

            if verbose and total_waited == 0.0:
                _logger.info("[ZROKY] Rate limiter: waiting %.2fs for %s", wait, key)

            time.sleep(wait)
            total_waited += wait

    # -- async acquire -----------------------------------------------------

    async def acquire_async(
        self,
        key: str,
        *,
        estimated_tokens: int = 0,
        timeout: float = _MAX_WAIT_SECONDS,
        verbose: bool = False,
    ) -> float:
        """Async version of :meth:`acquire`."""
        pair = self._get_or_create(key)
        total_waited = 0.0

        while True:
            with pair.lock:
                rpm_wait = pair.rpm.wait_time(1)
                tpm_wait = pair.tpm.wait_time(float(estimated_tokens)) if estimated_tokens > 0 else 0.0
                wait = max(rpm_wait, tpm_wait)

                if wait <= 0:
                    pair.rpm.consume(1)
                    if estimated_tokens > 0:
                        pair.tpm.consume(float(estimated_tokens))
                    return total_waited

            wait = min(wait, timeout - total_waited)
            if wait <= 0 or wait < _MIN_BLOCKING_WAIT_SECONDS:
                with pair.lock:
                    pair.rpm.consume(1)
                    if estimated_tokens > 0:
                        pair.tpm.consume(float(estimated_tokens))
                if verbose:
                    _logger.warning(
                        "[ZROKY] Rate limiter timeout for %s after %.1fs — sending anyway",
                        key, total_waited,
                    )
                return total_waited

            if verbose and total_waited == 0.0:
                _logger.info("[ZROKY] Rate limiter: waiting %.2fs for %s", wait, key)

            await asyncio.sleep(wait)
            total_waited += wait

    # -- post-response update ----------------------------------------------

    def update_from_response(
        self,
        key: str,
        response: Any,
        *,
        actual_tokens: int = 0,
        estimated_tokens: int = 0,
    ) -> None:
        """Update buckets from provider response headers and actual usage.

        If *actual_tokens* > *estimated_tokens*, consume the difference
        (because acquire() already consumed the estimate).
        """
        pair = self._get_or_create(key)
        parsed = _parse_rate_headers(response)

        with pair.lock:
            # Adjust token debt if actual usage exceeded estimate
            token_delta = actual_tokens - estimated_tokens
            if token_delta > 0:
                pair.tpm.consume(float(token_delta))

            # Update capacities from header limits
            if parsed.req_limit is not None and parsed.req_limit >= _MIN_CAPACITY:
                pair.rpm.update_capacity(parsed.req_limit)
            if parsed.tok_limit is not None and parsed.tok_limit >= _MIN_CAPACITY:
                pair.tpm.update_capacity(parsed.tok_limit)

            # Sync remaining values from headers (more accurate than our model)
            if parsed.req_remaining is not None:
                pair.rpm.set_remaining(parsed.req_remaining)
            if parsed.tok_remaining is not None:
                pair.tpm.set_remaining(parsed.tok_remaining)

    # -- inspection --------------------------------------------------------

    def status(self, key: str) -> dict[str, Any]:
        """Return current bucket state for debugging / verbose output."""
        pair = self._buckets.get(key)
        if pair is None:
            return {"key": key, "configured": False}
        with pair.lock:
            pair.rpm._refill()
            pair.tpm._refill()
            return {
                "key": key,
                "configured": True,
                "rpm_capacity": pair.rpm.capacity,
                "rpm_remaining": pair.rpm.tokens,
                "tpm_capacity": pair.tpm.capacity,
                "tpm_remaining": pair.tpm.tokens,
            }

    def reset(self, key: str | None = None) -> None:
        """Reset buckets.  If *key* is None, reset all."""
        with self._global_lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)


# ---------------------------------------------------------------------------
# Helper: build rate-limit key
# ---------------------------------------------------------------------------

def rate_limit_key(provider: str, model: str) -> str:
    """Canonical key for the rate limiter: ``'provider/model'``."""
    return f"{provider}/{model}"
