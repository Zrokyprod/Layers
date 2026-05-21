# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

# ---------------------------------------------------------------------------
# Tests for Intelligent Timeout Control
# ---------------------------------------------------------------------------
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zroky._internal.timeout_manager import (
    LatencyTracker,
    TimeoutManager,
    _ADAPTIVE_FLOOR_SECONDS,
    _DEFAULT_BUFFER_MULTIPLIER,
    _FULL_CONFIDENCE_SAMPLES,
    _MIN_SAMPLES,
    _timed_async_iter,
    _timed_sync_iter,
)


# ---------------------------------------------------------------------------
# Static resolution (existing tests)
# ---------------------------------------------------------------------------


class TestTimeoutManagerResolve:
    def test_user_override_wins(self):
        mgr = TimeoutManager()
        assert mgr.resolve("gpt-4o-mini", user_override=42.0) == 42.0

    def test_fast_model_default(self):
        mgr = TimeoutManager()
        assert mgr.resolve("gpt-4o-mini") == 15.0

    def test_heavy_model_default(self):
        mgr = TimeoutManager()
        assert mgr.resolve("o3-preview") == 120.0

    def test_unknown_model_returns_default(self):
        mgr = TimeoutManager()
        assert mgr.resolve("some-unknown-model") == 60.0

    def test_disabled_returns_none(self):
        mgr = TimeoutManager(enabled=False)
        assert mgr.resolve("gpt-4o-mini") is None

    def test_custom_defaults(self):
        mgr = TimeoutManager(defaults={"my-model": 7.0, "default": 99.0})
        assert mgr.resolve("my-model") == 7.0
        assert mgr.resolve("unknown") == 99.0


# ---------------------------------------------------------------------------
# Stream chunk timeout wrappers
# ---------------------------------------------------------------------------


class TestTimedSyncIter:
    def test_yields_items_when_fast(self):
        def gen():
            yield "a"
            yield "b"
            yield "c"

        it = _timed_sync_iter(gen(), chunk_timeout=5.0, on_timeout=TimeoutError("to"))
        assert list(it) == ["a", "b", "c"]

    def test_raises_timeout_on_slow_chunk(self):
        def gen():
            yield "a"
            time.sleep(0.2)
            yield "b"

        it = _timed_sync_iter(gen(), chunk_timeout=0.05, on_timeout=TimeoutError("to"))
        assert next(it) == "a"
        with pytest.raises(TimeoutError):
            next(it)


class TestTimedAsyncIter:
    @pytest.mark.asyncio
    async def test_yields_items_when_fast(self):
        async def gen():
            yield "a"
            yield "b"
            yield "c"

        result = []
        async for item in _timed_async_iter(gen(), chunk_timeout=5.0, on_timeout=TimeoutError("to")):
            result.append(item)
        assert result == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_raises_timeout_on_slow_chunk(self):
        async def gen():
            yield "a"
            await asyncio.sleep(0.2)
            yield "b"

        it = _timed_async_iter(gen(), chunk_timeout=0.05, on_timeout=TimeoutError("to"))
        result = []
        async for item in it:
            result.append(item)
            break  # consume only first
        assert result == ["a"]
        with pytest.raises(TimeoutError):
            async for _ in it:
                pass


class TestTimeoutManagerDefaultTimeout:
    def test_global_default_override(self):
        mgr = TimeoutManager(default_timeout=99.0)
        # user_override still wins
        assert mgr.resolve("gpt-4o-mini", user_override=5.0) == 5.0
        # global default applies when no user_override and no model match
        assert mgr.resolve("unknown-model") == 99.0
        # per-model defaults still apply when no global default
        mgr2 = TimeoutManager()
        assert mgr2.resolve("gpt-4o-mini") == 15.0


class TestTimeoutManagerStreamChunkTimeout:
    def test_default_stream_chunk_timeout(self):
        mgr = TimeoutManager()
        assert mgr.stream_chunk_timeout == 15.0

    def test_custom_stream_chunk_timeout(self):
        mgr = TimeoutManager(stream_chunk_timeout=7.0)
        assert mgr.stream_chunk_timeout == 7.0


# ---------------------------------------------------------------------------
# LatencyTracker
# ---------------------------------------------------------------------------


class TestLatencyTracker:
    def test_empty_returns_none(self):
        tracker = LatencyTracker()
        assert tracker.count("gpt-4o") == 0
        assert tracker.percentile("gpt-4o") is None
        assert tracker.mean("gpt-4o") is None

    def test_single_entry(self):
        tracker = LatencyTracker()
        tracker.record("gpt-4o", 1.5)
        assert tracker.count("gpt-4o") == 1
        assert tracker.percentile("gpt-4o", 50) == 1.5
        assert tracker.mean("gpt-4o") == 1.5

    def test_multiple_entries_percentile(self):
        tracker = LatencyTracker()
        for v in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]:
            tracker.record("m", v)
        p50 = tracker.percentile("m", 50)
        assert p50 is not None
        assert 5.0 <= p50 <= 6.0  # median of 1..10
        p99 = tracker.percentile("m", 99)
        assert p99 is not None
        assert p99 >= 9.0

    def test_clear_model(self):
        tracker = LatencyTracker()
        tracker.record("a", 1.0)
        tracker.record("b", 2.0)
        tracker.clear("a")
        assert tracker.count("a") == 0
        assert tracker.count("b") == 1

    def test_clear_all(self):
        tracker = LatencyTracker()
        tracker.record("a", 1.0)
        tracker.record("b", 2.0)
        tracker.clear()
        assert tracker.count("a") == 0
        assert tracker.count("b") == 0

    def test_max_entries_cap(self):
        tracker = LatencyTracker(max_entries=5)
        for i in range(20):
            tracker.record("m", float(i))
        assert tracker.count("m") == 5


# ---------------------------------------------------------------------------
# Adaptive timeout resolution
# ---------------------------------------------------------------------------


class TestAdaptiveTimeout:
    def test_below_min_samples_returns_static(self):
        mgr = TimeoutManager()
        # Feed fewer than _MIN_SAMPLES observations
        for _ in range(_MIN_SAMPLES - 1):
            mgr.record_latency("gpt-4o", 2.0)
        # Should still return the static default (30.0)
        assert mgr.resolve("gpt-4o") == 30.0

    def test_at_min_samples_starts_blending(self):
        mgr = TimeoutManager()
        # Feed _MIN_SAMPLES + 1 so confidence > 0 and blending kicks in
        for _ in range(_MIN_SAMPLES + 1):
            mgr.record_latency("gpt-4o", 2.0)
        result = mgr.resolve("gpt-4o")
        static = 30.0
        # Should be less than pure static because adaptive pulls it down
        assert result < static
        # But not fully adaptive yet (confidence < 1)
        adaptive_raw = 2.0 * _DEFAULT_BUFFER_MULTIPLIER
        assert result > adaptive_raw

    def test_full_confidence_uses_adaptive(self):
        mgr = TimeoutManager()
        # Feed _FULL_CONFIDENCE_SAMPLES observations all at 2s
        for _ in range(_FULL_CONFIDENCE_SAMPLES):
            mgr.record_latency("gpt-4o", 2.0)
        result = mgr.resolve("gpt-4o")
        expected = max(2.0 * _DEFAULT_BUFFER_MULTIPLIER, _ADAPTIVE_FLOOR_SECONDS)
        assert result == round(expected, 2)

    def test_adaptive_floor_enforced(self):
        mgr = TimeoutManager()
        # Feed tiny latencies
        for _ in range(_FULL_CONFIDENCE_SAMPLES):
            mgr.record_latency("gpt-4o", 0.01)
        result = mgr.resolve("gpt-4o")
        # Should not go below the floor
        assert result >= _ADAPTIVE_FLOOR_SECONDS

    def test_adaptive_disabled_returns_static(self):
        mgr = TimeoutManager(adaptive=False)
        for _ in range(_FULL_CONFIDENCE_SAMPLES):
            mgr.record_latency("gpt-4o", 2.0)
        assert mgr.resolve("gpt-4o") == 30.0

    def test_user_override_beats_adaptive(self):
        mgr = TimeoutManager()
        for _ in range(_FULL_CONFIDENCE_SAMPLES):
            mgr.record_latency("gpt-4o", 2.0)
        assert mgr.resolve("gpt-4o", user_override=99.0) == 99.0

    def test_default_timeout_skips_adaptive(self):
        mgr = TimeoutManager(default_timeout=42.0)
        for _ in range(_FULL_CONFIDENCE_SAMPLES):
            mgr.record_latency("gpt-4o", 2.0)
        assert mgr.resolve("gpt-4o") == 42.0

    def test_high_latency_raises_timeout(self):
        mgr = TimeoutManager()
        # Simulate a model that is slow — 25s calls
        for _ in range(_FULL_CONFIDENCE_SAMPLES):
            mgr.record_latency("gpt-4o", 25.0)
        result = mgr.resolve("gpt-4o")
        # P99 ≈ 25.0, adaptive = 25.0 * 1.3 = 32.5
        expected = round(25.0 * _DEFAULT_BUFFER_MULTIPLIER, 2)
        assert result == expected

    def test_mixed_latencies_percentile_behavior(self):
        mgr = TimeoutManager()
        # 29 fast calls + 1 slow call
        for _ in range(_FULL_CONFIDENCE_SAMPLES - 1):
            mgr.record_latency("gpt-4o", 1.0)
        mgr.record_latency("gpt-4o", 20.0)
        result = mgr.resolve("gpt-4o")
        # P99 should be high (near 20s), so timeout should be higher than
        # the pure 1.0 * buffer value
        pure_fast = 1.0 * _DEFAULT_BUFFER_MULTIPLIER
        assert result > pure_fast

    def test_independent_model_tracking(self):
        mgr = TimeoutManager()
        for _ in range(_FULL_CONFIDENCE_SAMPLES):
            mgr.record_latency("gpt-4o", 2.0)
            mgr.record_latency("claude-3-opus", 50.0)
        gpt_timeout = mgr.resolve("gpt-4o")
        claude_timeout = mgr.resolve("claude-3-opus")
        assert gpt_timeout < claude_timeout


# ---------------------------------------------------------------------------
# Edge cases and boundary conditions
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_sync_iter(self):
        def gen():
            return
            yield  # type: ignore[unreachable]

        it = _timed_sync_iter(gen(), chunk_timeout=5.0, on_timeout=TimeoutError("to"))
        assert list(it) == []

    @pytest.mark.asyncio
    async def test_empty_async_iter(self):
        async def gen():
            return
            yield  # type: ignore[unreachable]

        result = []
        async for item in _timed_async_iter(gen(), chunk_timeout=5.0, on_timeout=TimeoutError("to")):
            result.append(item)
        assert result == []

    def test_zero_chunk_timeout_sync(self):
        def gen():
            yield "a"
            time.sleep(0.5)
            yield "b"

        it = _timed_sync_iter(gen(), chunk_timeout=0.0, on_timeout=TimeoutError("to"))
        assert next(it) == "a"
        with pytest.raises(TimeoutError):
            next(it)

    @pytest.mark.asyncio
    async def test_zero_chunk_timeout_async(self):
        async def gen():
            await asyncio.sleep(0.5)
            yield "a"

        it = _timed_async_iter(gen(), chunk_timeout=0.0, on_timeout=TimeoutError("to"))
        with pytest.raises(TimeoutError):
            async for _ in it:
                pass

    def test_latency_tracker_negative_latency_ignored(self):
        tracker = LatencyTracker()
        tracker.record("m", -1.0)
        tracker.record("m", 2.0)
        tracker.record("m", 3.0)
        mean = tracker.mean("m")
        assert mean is not None
        # Negative values still get stored, but math is correct
        assert tracker.count("m") == 3

    def test_resolve_empty_model_name(self):
        mgr = TimeoutManager()
        assert mgr.resolve("") == 60.0  # falls through to default

    def test_resolve_none_user_override(self):
        mgr = TimeoutManager()
        assert mgr.resolve("gpt-4o-mini", user_override=None) == 15.0

    def test_stream_chunk_timeout_disabled(self):
        mgr = TimeoutManager(enabled=False)
        assert mgr.stream_chunk_timeout == 15.0  # field still readable

    def test_custom_defaults_override_builtin(self):
        mgr = TimeoutManager(defaults={"default": 10.0})
        assert mgr.resolve("unknown-model") == 10.0

    @pytest.mark.asyncio
    async def test_async_timeout_error_not_leaked(self):
        """Ensure asyncio.TimeoutError is translated to the caller's on_timeout."""
        async def gen():
            yield "a"
            await asyncio.sleep(1.0)
            yield "b"

        custom_exc = RuntimeError("custom timeout")
        it = _timed_async_iter(gen(), chunk_timeout=0.01, on_timeout=custom_exc)
        result = []
        async for item in it:
            result.append(item)
            break
        assert result == ["a"]
        with pytest.raises(RuntimeError, match="custom timeout"):
            async for _ in it:
                pass
