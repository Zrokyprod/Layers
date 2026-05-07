"""
Async event queue — batches call events and flushes to the ingest client
without blocking the application request path.

Flush conditions (whichever comes first):
  - batch_size reached (default 10)
  - flush_interval_seconds elapsed (default 5s)

Queue behavior:
  - Bounded queue with configurable max size
  - When full, oldest events are dropped (drop-tail policy)
  - Drop metrics tracked for observability

Blueprint SLOs:
  - async flush timeout <= 2s
  - event drop rate < 0.1% (healthy backend)
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import TYPE_CHECKING

from zroky._internal.ingestion import IngestClient
from zroky._internal.local_mode import LocalWriter
from zroky._internal.metrics import notify_flush

if TYPE_CHECKING:
    from zroky._internal.config import SDKConfig
    from zroky._internal.models import CallEvent

_SENTINEL = object()  # signals shutdown
_logger = logging.getLogger(__name__)

# Default maximum queue size to prevent unbounded memory growth
_DEFAULT_MAX_QUEUE_SIZE = 10_000


class EventQueue:
    def __init__(self, config: "SDKConfig") -> None:
        self._config = config
        self._max_size = getattr(config, "max_queue_size", _DEFAULT_MAX_QUEUE_SIZE)
        # Use bounded queue to prevent memory exhaustion under high load
        self._q: queue.Queue["CallEvent | object"] = queue.Queue(maxsize=self._max_size)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._dropped_count = 0
        self._dropped_lock = threading.Lock()

        if config.mode == "local":
            self._writer: IngestClient | LocalWriter = LocalWriter()
        else:
            self._writer = IngestClient(config)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._worker,
            name="zroky-flush-worker",
            daemon=True,
        )
        self._thread.start()

    def enqueue(self, event: "CallEvent") -> bool:
        """
        Add event to queue. Returns True if enqueued, False if dropped (queue full).
        """
        try:
            self._q.put_nowait(event)
            return True
        except queue.Full:
            with self._dropped_lock:
                self._dropped_count += 1
                total_dropped = self._dropped_count
            # Log periodically to avoid spam
            if total_dropped % 100 == 1:
                _logger.warning(
                    "[ZROKY] Event queue full, dropped %d events. "
                    "Consider increasing max_queue_size or checking backend connectivity.",
                    total_dropped
                )
            return False

    @property
    def dropped_count(self) -> int:
        """Number of events dropped due to queue overflow."""
        with self._dropped_lock:
            return self._dropped_count

    def flush(self, timeout: float = 2.0) -> None:
        """Block until the queue is drained or timeout expires."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._q.empty():
                return
            time.sleep(0.05)

    def shutdown(self) -> None:
        """Shutdown the queue worker, waiting for pending events."""
        # Try to put sentinel, waiting if queue is full
        max_wait_attempts = 50  # 5 seconds total
        for attempt in range(max_wait_attempts):
            try:
                self._q.put_nowait(_SENTINEL)
                break
            except queue.Full:
                # Queue is full, wait a bit and try again
                time.sleep(0.1)
                if attempt == max_wait_attempts - 1:
                    # Last attempt failed, force clear some space
                    try:
                        # Remove oldest item to make room for sentinel
                        self._q.get_nowait()
                        self._q.put_nowait(_SENTINEL)
                    except queue.Empty:
                        pass  # Queue became empty, sentinel not needed
                    break

        if self._thread is not None:
            self._thread.join(timeout=5.0)

    # ------------------------------------------------------------------
    # Internal worker
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        batch: list["CallEvent"] = []
        last_flush = time.monotonic()
        consecutive_errors = 0
        max_consecutive_errors = 5

        while True:
            now = time.monotonic()
            interval = self._config.flush_interval_seconds
            remaining = max(0.0, interval - (now - last_flush))

            try:
                item = self._q.get(timeout=remaining)
            except queue.Empty:
                # Interval elapsed — flush whatever we have
                if batch:
                    if self._flush_batch(batch):
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                    batch = []
                last_flush = time.monotonic()
                # Back off if too many consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    time.sleep(min(30.0, 2 ** (consecutive_errors - max_consecutive_errors)))
                continue

            if item is _SENTINEL:
                # Drain remaining items then exit
                while True:
                    try:
                        item2 = self._q.get_nowait()
                        if item2 is not _SENTINEL:
                            batch.append(item2)  # type: ignore[arg-type]
                    except queue.Empty:
                        break
                if batch:
                    self._flush_batch(batch)
                return

            batch.append(item)  # type: ignore[arg-type]

            if len(batch) >= self._config.batch_size:
                if self._flush_batch(batch):
                    consecutive_errors = 0
                else:
                    consecutive_errors += 1
                batch = []
                last_flush = time.monotonic()

    def _flush_batch(self, batch: list["CallEvent"]) -> bool:
        """
        Flush batch to writer. Returns True on success, False on failure.
        """
        try:
            self._writer.send_batch(batch)
            notify_flush(len(batch), 0)
            return True
        except Exception as exc:  # noqa: BLE001
            # Never propagate errors to the worker thread, but track failure
            _logger.debug("[ZROKY] Failed to flush batch: %s", exc)
            notify_flush(0, len(batch))
            return False
