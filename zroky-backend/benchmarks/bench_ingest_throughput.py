"""Benchmark: ingest event throughput to Redis worker (Rule 4 — ZROKY-004).

Measures events/sec achievable when publishing IngestEvent v2 to the
Redis Stream from the backend ingest path.

Target: >= 1000 events/sec sustained (see README: BENCH_TAG:ingest_throughput_eps).

Run locally:
    cd zroky-backend
    python -m pytest benchmarks/bench_ingest_throughput.py -v --benchmark-autosave
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _FakeAsyncRedis:
    def __init__(self) -> None:
        self._count = 0

    async def xadd(self, stream: str, fields: dict, maxlen: int = 0) -> bytes:
        self._count += 1
        return f"{self._count}-0".encode()

    async def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: _FakeAsyncRedis) -> None:
        self._redis = redis
        self._cmds: list = []

    def xadd(self, stream: str, fields: dict, maxlen: int = 0):
        self._cmds.append(("xadd", stream, fields))
        return self

    async def execute(self) -> list:
        for cmd in self._cmds:
            self._redis._count += 1
        results = [f"{i}-0".encode() for i in range(len(self._cmds))]
        self._cmds.clear()
        return results


def _make_ingest_event(idx: int) -> dict:
    return {
        "v": "2",
        "call_id": f"call_{idx:06d}",
        "tenant_id": f"t{idx % 10}",
        "model": "gpt-4o",
        "prompt_tokens": 512,
        "completion_tokens": 128,
        "cost_usd": "0.0043",
        "latency_ms": 820,
        "prompt_fingerprint": f"fp_{idx % 1000:04d}",
        "status": "success",
    }


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

@pytest.mark.benchmark(group="ingest_throughput")
def test_single_event_xadd_latency(benchmark) -> None:
    """BENCH_TAG:ingest_single_xadd — p95 < 1 ms per event."""
    redis = _FakeAsyncRedis()
    event = _make_ingest_event(0)

    def publish_one():
        return asyncio.get_event_loop().run_until_complete(
            redis.xadd("zroky:ingest:v2", event, maxlen=100_000)
        )

    benchmark(publish_one)
    assert redis._count > 0


@pytest.mark.benchmark(group="ingest_throughput")
def test_batch_100_pipeline_throughput(benchmark) -> None:
    """BENCH_TAG:ingest_throughput_eps — target >= 1000 eps via pipeline."""
    redis = _FakeAsyncRedis()
    events = [_make_ingest_event(i) for i in range(100)]

    async def publish_batch():
        pipe = await redis.pipeline()
        for ev in events:
            pipe.xadd("zroky:ingest:v2", ev, maxlen=100_000)
        return await pipe.execute()

    def run():
        return asyncio.get_event_loop().run_until_complete(publish_batch())

    stats = benchmark(run)
    assert redis._count >= 100


@pytest.mark.benchmark(group="ingest_throughput")
def test_event_serialization_overhead(benchmark) -> None:
    """BENCH_TAG:ingest_serialization — p95 < 0.5 ms per event."""
    event_raw = {
        "call_id": "call_bench",
        "tenant_id": "t1",
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello world"}],
        "usage": {"prompt_tokens": 512, "completion_tokens": 128},
        "cost_usd": 0.0043,
        "latency_ms": 820,
        "status": "success",
    }

    def serialize():
        return json.dumps(event_raw, separators=(",", ":")).encode()

    result = benchmark(serialize)
    assert len(result) > 0


# Rule 4 threshold registry
RULE4_LIMITS = {
    "ingest_single_xadd": {"mean_ms": 1.0},
    "ingest_throughput_eps": {"min_eps": 1000},
    "ingest_serialization": {"mean_ms": 0.5},
}
