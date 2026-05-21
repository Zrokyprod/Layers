# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Intelligent timeout control for provider calls.

Features:
  - Static model-class defaults (GPT-4o=30s, Claude Opus=120s, etc.)
  - User override resolution (always wins)
  - **Adaptive percentile-based timeouts**: tracks real latencies per model in
    a sliding window; once enough observations are collected the timeout is
    derived from the observed P-th percentile (default P99) plus a configurable
    multiplier buffer.  The static default is blended with the adaptive value
    using a confidence ramp so the transition is smooth.
  - Stream chunk timeout wrappers (sync via ThreadPoolExecutor, async via
    asyncio.wait_for).
"""
from __future__ import annotations

import math
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterator


# ---------------------------------------------------------------------------
# Model-class → default timeout (seconds)
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUTS: dict[str, float] = {
    "gpt-4o-mini": 15.0,
    "gpt-4o": 30.0,
    "gpt-4": 60.0,
    "claude-3-haiku": 30.0,
    "claude-3-sonnet": 60.0,
    "claude-3-opus": 120.0,
    "claude-3-5-sonnet": 90.0,
    "o1": 120.0,
    "o3": 120.0,
    "deepseek": 60.0,
    "gemini": 60.0,
    "default": 60.0,
}

# Minimum number of observations before the adaptive timeout starts to blend
_MIN_SAMPLES: int = 5
# Full confidence (100 % adaptive) reached at this many observations
_FULL_CONFIDENCE_SAMPLES: int = 30
# Default percentile to use for adaptive timeout (0–100)
_DEFAULT_PERCENTILE: float = 99.0
# Multiplier applied on top of the percentile value as safety buffer
_DEFAULT_BUFFER_MULTIPLIER: float = 1.3
# Sliding window for latency observations (seconds)
_DEFAULT_WINDOW_SECONDS: float = 600.0
# Max entries per model
_DEFAULT_MAX_ENTRIES: int = 200
# Hard floor – never set an adaptive timeout below this value
_ADAPTIVE_FLOOR_SECONDS: float = 2.0

_SENTINEL = object()


# ---------------------------------------------------------------------------
# Latency tracker (per-model sliding window + percentile math)
# ---------------------------------------------------------------------------

@dataclass
class _LatencyEntry:
    ts: float
    latency_s: float


class LatencyTracker:
    """Keeps a sliding window of successful-call latencies per model."""

    def __init__(
        self,
        window_seconds: float = _DEFAULT_WINDOW_SECONDS,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._window = window_seconds
        self._maxlen = max_entries
        self._data: dict[str, deque[_LatencyEntry]] = {}

    # -- recording ----------------------------------------------------------

    def record(self, model: str, latency_s: float) -> None:
        """Record a successful call latency (in **seconds**)."""
        now = time.monotonic()
        dq = self._data.setdefault(model, deque(maxlen=self._maxlen))
        dq.append(_LatencyEntry(now, latency_s))
        self._evict(dq, now)

    def _evict(self, dq: deque[_LatencyEntry], now: float) -> None:
        cutoff = now - self._window
        while dq and dq[0].ts < cutoff:
            dq.popleft()

    # -- queries ------------------------------------------------------------

    def count(self, model: str) -> int:
        dq = self._data.get(model)
        if dq is None:
            return 0
        self._evict(dq, time.monotonic())
        return len(dq)

    def percentile(self, model: str, p: float = 99.0) -> float | None:
        """Return the *p*-th percentile latency (seconds) or *None*."""
        dq = self._data.get(model)
        if not dq:
            return None
        self._evict(dq, time.monotonic())
        if not dq:
            return None
        vals = sorted(e.latency_s for e in dq)
        k = (p / 100.0) * (len(vals) - 1)
        lo = int(math.floor(k))
        hi = min(lo + 1, len(vals) - 1)
        frac = k - lo
        return vals[lo] + frac * (vals[hi] - vals[lo])

    def mean(self, model: str) -> float | None:
        dq = self._data.get(model)
        if not dq:
            return None
        self._evict(dq, time.monotonic())
        if not dq:
            return None
        return sum(e.latency_s for e in dq) / len(dq)

    def clear(self, model: str | None = None) -> None:
        if model is None:
            self._data.clear()
        else:
            self._data.pop(model, None)


# ---------------------------------------------------------------------------
# Timeout manager
# ---------------------------------------------------------------------------

@dataclass
class TimeoutManager:
    defaults: dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_TIMEOUTS))
    stream_chunk_timeout: float = 15.0
    enabled: bool = True
    default_timeout: float | None = None
    # Adaptive settings
    adaptive: bool = True
    adaptive_percentile: float = _DEFAULT_PERCENTILE
    adaptive_buffer: float = _DEFAULT_BUFFER_MULTIPLIER
    adaptive_floor: float = _ADAPTIVE_FLOOR_SECONDS
    latency_tracker: LatencyTracker = field(default_factory=LatencyTracker)

    # -- public API ---------------------------------------------------------

    def record_latency(self, model: str, latency_s: float) -> None:
        """Feed a successful-call latency into the adaptive engine."""
        self.latency_tracker.record(model, latency_s)

    def resolve(self, model: str, user_override: float | None = None) -> float | None:
        """Return the timeout (seconds) to use for *model*.

        Resolution order:
        1. Disabled → ``None``
        2. Explicit *user_override* → that value
        3. Global ``default_timeout`` → that value (skips adaptive)
        4. **Adaptive blend** of static default and historical percentile
        5. Pure static default from ``defaults`` dict
        """
        if not self.enabled:
            return None
        if user_override is not None:
            return user_override
        if self.default_timeout is not None:
            return self.default_timeout

        static = self._static_default(model)

        if not self.adaptive:
            return static

        return self._adaptive_resolve(model, static)

    # -- internals ----------------------------------------------------------

    def _static_default(self, model: str) -> float:
        lower = (model or "").lower()
        for pattern, seconds in sorted(self.defaults.items(), key=lambda x: -len(x[0])):
            if pattern in lower:
                return seconds
        return self.defaults.get("default", 60.0)

    def _adaptive_resolve(self, model: str, static: float) -> float:
        """Blend static default with observed percentile based on confidence."""
        n = self.latency_tracker.count(model)
        if n < _MIN_SAMPLES:
            return static

        pval = self.latency_tracker.percentile(model, self.adaptive_percentile)
        if pval is None:
            return static

        adaptive_timeout = max(pval * self.adaptive_buffer, self.adaptive_floor)

        # Confidence ramp: linear from 0 at _MIN_SAMPLES to 1 at _FULL_CONFIDENCE_SAMPLES
        confidence = min(
            (n - _MIN_SAMPLES) / max(_FULL_CONFIDENCE_SAMPLES - _MIN_SAMPLES, 1),
            1.0,
        )
        blended = static * (1.0 - confidence) + adaptive_timeout * confidence
        return round(blended, 2)


def _timed_sync_iter(iterable: Iterator[Any], chunk_timeout: float, on_timeout: Any) -> Iterator[Any]:
    """Yield from *iterable* but abort if no chunk arrives within *chunk_timeout* seconds."""
    it = iter(iterable)
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        while True:
            future = executor.submit(lambda: next(it, _SENTINEL))
            try:
                item = future.result(timeout=chunk_timeout)
            except TimeoutError:
                raise on_timeout
            if item is _SENTINEL:
                break
            yield item  # type: ignore[misc]
    finally:
        executor.shutdown(wait=False)


async def _timed_async_iter(iterable: AsyncIterator[Any], chunk_timeout: float, on_timeout: Any) -> AsyncIterator[Any]:
    """Async version of _timed_sync_iter."""
    import asyncio
    it = iterable.__aiter__()
    while True:
        try:
            item = await asyncio.wait_for(it.__anext__(), timeout=chunk_timeout)
            yield item
        except asyncio.TimeoutError:
            raise on_timeout
        except StopAsyncIteration:
            break
