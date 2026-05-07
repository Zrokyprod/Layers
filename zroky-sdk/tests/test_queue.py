"""Tests for async event queue."""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from zroky._internal.config import SDKConfig
from zroky._internal.models import CallEvent
from zroky._internal.queue import EventQueue


def _make_config(**overrides: object) -> SDKConfig:
    defaults = dict(
        api_key="test-key",
        project="test-proj",
        mode="cloud",
        mask_pii=False,
        ingest_url="http://localhost:8000",
        default_agent=None,
        verbose=False,
        batch_size=3,
        flush_interval_seconds=0.2,
        max_queue_size=1000,
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


def test_batch_flush_on_size():
    """Queue flushes when batch_size is reached."""
    sent: list[list[CallEvent]] = []
    config = _make_config(batch_size=3, flush_interval_seconds=60.0)

    with patch("zroky._internal.queue.IngestClient") as MockClient:
        instance = MockClient.return_value
        instance.send_batch.side_effect = lambda batch: sent.append(list(batch))

        q = EventQueue(config=config)
        q.start()

        for _ in range(3):
            q.enqueue(_make_event())

        # Wait for flush
        deadline = time.monotonic() + 2.0
        while not sent and time.monotonic() < deadline:
            time.sleep(0.05)

        q.shutdown()

    assert len(sent) >= 1
    assert sum(len(b) for b in sent) == 3


def test_flush_on_interval():
    """Queue flushes on interval even when batch not full."""
    sent: list[list[CallEvent]] = []
    config = _make_config(batch_size=100, flush_interval_seconds=0.1)

    with patch("zroky._internal.queue.IngestClient") as MockClient:
        instance = MockClient.return_value
        instance.send_batch.side_effect = lambda batch: sent.append(list(batch))

        q = EventQueue(config=config)
        q.start()
        q.enqueue(_make_event())

        time.sleep(0.4)
        q.shutdown()

    assert sum(len(b) for b in sent) == 1


def test_shutdown_drains_queue():
    """Shutdown sends all pending events before stopping."""
    sent: list[list[CallEvent]] = []
    config = _make_config(batch_size=100, flush_interval_seconds=60.0)

    with patch("zroky._internal.queue.IngestClient") as MockClient:
        instance = MockClient.return_value
        instance.send_batch.side_effect = lambda batch: sent.append(list(batch))

        q = EventQueue(config=config)
        q.start()

        for i in range(5):
            q.enqueue(_make_event(model=f"model-{i}"))

        q.shutdown()

    assert sum(len(b) for b in sent) == 5


def test_ingest_error_does_not_crash_worker():
    """Worker catches ingest errors and keeps running."""
    config = _make_config(batch_size=1, flush_interval_seconds=60.0)

    with patch("zroky._internal.queue.IngestClient") as MockClient:
        instance = MockClient.return_value
        instance.send_batch.side_effect = RuntimeError("network failure")

        q = EventQueue(config=config)
        q.start()
        q.enqueue(_make_event())
        q.enqueue(_make_event())
        q.shutdown()  # must not raise


def test_local_mode_uses_local_writer():
    """In local mode, queue uses LocalWriter instead of IngestClient."""
    config = _make_config(mode="local")

    with patch("zroky._internal.queue.LocalWriter") as MockWriter, \
         patch("zroky._internal.queue.IngestClient") as MockClient:
        q = EventQueue(config=config)
        MockWriter.assert_called_once()
        MockClient.assert_not_called()
        q.shutdown()


def test_queue_drops_events_when_full():
    """Queue drops events when at capacity."""
    config = _make_config(max_queue_size=5, batch_size=100, flush_interval_seconds=60.0)

    with patch("zroky._internal.queue.IngestClient") as MockClient:
        instance = MockClient.return_value
        # Don't flush to keep queue full
        instance.send_batch = lambda batch: None

        q = EventQueue(config=config)
        q.start()

        # Fill queue beyond capacity
        results = []
        for _ in range(10):
            result = q.enqueue(_make_event())
            results.append(result)

        # Some should have been dropped
        assert q.dropped_count > 0
        assert results.count(False) > 0
        assert results.count(True) < 10

        q.shutdown()


def test_enqueue_returns_bool():
    """enqueue() returns True on success, False on drop."""
    config = _make_config(max_queue_size=1, batch_size=100, flush_interval_seconds=60.0)

    with patch("zroky._internal.queue.IngestClient"):
        q = EventQueue(config=config)
        q.start()

        # First enqueue should succeed
        assert q.enqueue(_make_event()) is True
        # Second should fail (queue full)
        assert q.enqueue(_make_event()) is False

        q.shutdown()


def test_queue_tracks_dropped_count():
    """Dropped count is tracked correctly."""
    config = _make_config(max_queue_size=2, batch_size=100, flush_interval_seconds=60.0)

    with patch("zroky._internal.queue.IngestClient"):
        q = EventQueue(config=config)
        q.start()

        initial_dropped = q.dropped_count
        assert initial_dropped == 0

        # Overfill the queue
        for _ in range(10):
            q.enqueue(_make_event())

        assert q.dropped_count > 0

        q.shutdown()
