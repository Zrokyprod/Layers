"""Tests for async event queue."""
from __future__ import annotations

import asyncio

import pytest

from zroky._internal.async_queue import AsyncEventQueue
from zroky._internal.config import SDKConfig
from zroky._internal.models import CallEvent


def _make_config(**overrides: object) -> SDKConfig:
    defaults = dict(
        api_key="test-key",
        project="test-proj",
        mode="local",  # Use local mode to avoid HTTP
        mask_pii=False,
        ingest_url="http://localhost:8000",
        default_agent=None,
        verbose=False,
        batch_size=3,
        flush_interval_seconds=0.2,
        max_queue_size=100,
    )
    defaults.update(overrides)
    return SDKConfig(**defaults)  # type: ignore[arg-type]


def _make_event(model: str = "gpt-4o") -> CallEvent:
    return CallEvent(
        provider="openai",
        model=model,
        messages=[],
        status="success",
    )


@pytest.mark.asyncio
async def test_async_enqueue_and_flush():
    """Basic async enqueue and flush works."""
    config = _make_config(batch_size=100, flush_interval_seconds=60.0)
    queue = AsyncEventQueue(config=config)
    await queue.start()

    # Enqueue events
    for i in range(5):
        result = await queue.enqueue(_make_event(model=f"model-{i}"))
        assert result is True

    # Flush
    await queue.flush(timeout=2.0)
    assert queue.dropped_count == 0

    await queue.shutdown()


@pytest.mark.asyncio
async def test_async_queue_drops_when_full():
    """Queue drops events when at capacity."""
    config = _make_config(max_queue_size=5, batch_size=100, flush_interval_seconds=60.0)
    queue = AsyncEventQueue(config=config)
    await queue.start()

    # Fill the queue beyond capacity (without flushing)
    results = []
    for i in range(10):
        result = await queue.enqueue(_make_event())
        results.append(result)

    # Some should have been dropped
    assert queue.dropped_count > 0
    assert results.count(True) < 10

    await queue.shutdown()


@pytest.mark.asyncio
async def test_async_batch_flush_on_size():
    """Queue flushes when batch_size is reached."""
    config = _make_config(batch_size=3, flush_interval_seconds=60.0)
    queue = AsyncEventQueue(config=config)
    await queue.start()

    # Enqueue exactly batch_size events
    for _ in range(3):
        await queue.enqueue(_make_event())

    # Give time for flush
    await asyncio.sleep(0.5)
    await queue.flush(timeout=1.0)

    await queue.shutdown()


@pytest.mark.asyncio
async def test_async_flush_on_interval():
    """Queue flushes on interval even when batch not full."""
    config = _make_config(batch_size=100, flush_interval_seconds=0.1)
    queue = AsyncEventQueue(config=config)
    await queue.start()

    await queue.enqueue(_make_event())

    # Wait for interval flush
    await asyncio.sleep(0.5)

    await queue.shutdown()


@pytest.mark.asyncio
async def test_async_shutdown_drains_queue():
    """Shutdown sends all pending events."""
    config = _make_config(batch_size=100, flush_interval_seconds=60.0)
    queue = AsyncEventQueue(config=config)
    await queue.start()

    # Enqueue without flushing
    for i in range(5):
        await queue.enqueue(_make_event(model=f"model-{i}"))

    # Shutdown should drain
    await queue.shutdown()
    assert queue.dropped_count == 0


@pytest.mark.asyncio
async def test_async_concurrent_enqueue():
    """Multiple coroutines can enqueue safely."""
    config = _make_config(batch_size=100, flush_interval_seconds=60.0)
    queue = AsyncEventQueue(config=config)
    await queue.start()

    async def producer(n: int) -> int:
        for i in range(n):
            await queue.enqueue(_make_event())
        return n

    # Run multiple producers concurrently
    results = await asyncio.gather(
        producer(10),
        producer(10),
        producer(10),
    )

    assert sum(results) == 30
    await queue.shutdown()
