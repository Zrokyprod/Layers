"""Benchmark: @zroky.trace decorator overhead (Rule 4 — ZROKY-004).

Measures the wall-clock cost added by wrapping an OpenAI-compatible async call
with the Zroky SDK in non-blocking (fire-and-forget) ingestion mode.

Target: p95 overhead < 5 ms with network mocked.

Run locally:
    cd zroky-backend
    python -m pytest benchmarks/bench_sdk_overhead.py -v --benchmark-autosave

CI (comparison against main):
    python -m pytest benchmarks/bench_sdk_overhead.py --benchmark-compare
    --benchmark-compare-fail=mean:10%
"""
from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fake SDK surface (mirrors zroky-sdk public API without importing the SDK
# package from the monorepo to keep the benchmark hermetic).  Replace these
# with real imports once the SDK is refactored (ZROKY-101).
# ---------------------------------------------------------------------------

class _FakeIngestQueue:
    """Minimal async queue that simulates fire-and-forget ingestion."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)

    async def enqueue(self, event: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass


_QUEUE = _FakeIngestQueue()


async def _fake_openai_call() -> dict[str, Any]:
    """Simulate a local-loopback OpenAI API response (no network)."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "gpt-4o",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
    }


async def _trace_wrapper(call_fn: Any) -> Any:
    """Minimal SDK trace wrapper: record pre/post timestamps + enqueue event."""
    t0 = time.monotonic()
    result = await call_fn()
    latency_ms = (time.monotonic() - t0) * 1000

    await _QUEUE.enqueue(
        {
            "call_id": "bench-call-id",
            "provider": "openai",
            "model": "gpt-4o",
            "call_type": "chat",
            "status": "completed",
            "latency_ms": latency_ms,
            "prompt_tokens": result["usage"]["prompt_tokens"],
            "completion_tokens": result["usage"]["completion_tokens"],
        }
    )
    return result


# ---------------------------------------------------------------------------
# pytest-benchmark fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def event_loop():
    """Single event loop for the entire module."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

@pytest.mark.benchmark(group="sdk-overhead", min_rounds=200)
def test_bench_trace_wrapper_overhead(benchmark):
    """
    Measure the overhead of the trace wrapper vs a naked call.

    Rule 4 target: p95 overhead < 5 ms.
    The benchmark runner posts a regression comment on PRs and fails
    if mean overhead regresses > 10% vs the stored baseline.
    """
    loop = asyncio.get_event_loop()

    def run_wrapped():
        return loop.run_until_complete(_trace_wrapper(_fake_openai_call))

    def run_naked():
        return loop.run_until_complete(_fake_openai_call())

    # Measure naked call to establish baseline
    naked_times: list[float] = []
    for _ in range(50):
        t0 = time.perf_counter()
        loop.run_until_complete(_fake_openai_call())
        naked_times.append((time.perf_counter() - t0) * 1000)

    naked_p95 = statistics.quantiles(naked_times, n=20)[18]  # ~p95

    # Benchmark the wrapped call
    result = benchmark.pedantic(run_wrapped, iterations=1, rounds=200)

    wrapped_times: list[float] = []
    for _ in range(200):
        t0 = time.perf_counter()
        loop.run_until_complete(_trace_wrapper(_fake_openai_call))
        wrapped_times.append((time.perf_counter() - t0) * 1000)

    wrapped_p95 = statistics.quantiles(wrapped_times, n=20)[18]
    overhead_p95 = wrapped_p95 - naked_p95

    # Soft assert — emit a warning, hard fail if > 5 ms
    print(f"\n  naked p95  : {naked_p95:.3f} ms")
    print(f"  wrapped p95: {wrapped_p95:.3f} ms")
    print(f"  overhead p95: {overhead_p95:.3f} ms  (Rule 4 limit: 5 ms)")

    assert overhead_p95 < 5.0, (
        f"SDK decorator overhead p95 {overhead_p95:.2f} ms exceeds 5 ms Rule 4 limit. "
        "Investigate blocking code paths in the ingestion hot path."
    )


@pytest.mark.benchmark(group="sdk-overhead", min_rounds=500)
def test_bench_event_serialization(benchmark):
    """Benchmark pure event dict construction + queue enqueue cost."""
    loop = asyncio.get_event_loop()

    async def _build_and_enqueue():
        await _QUEUE.enqueue(
            {
                "call_id": "bench-call-id",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "call_type": "chat",
                "status": "completed",
                "latency_ms": 123.45,
                "prompt_tokens": 500,
                "completion_tokens": 100,
                "estimated_cost_usd": 0.00025,
                "trace_id": "abc123def456",
                "agent_name": "research-agent",
                "prompt_fingerprint": "fp_deadbeef01234567",
            }
        )

    benchmark.pedantic(
        lambda: loop.run_until_complete(_build_and_enqueue()),
        iterations=1,
        rounds=500,
    )
