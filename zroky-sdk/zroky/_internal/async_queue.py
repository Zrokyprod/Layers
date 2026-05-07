"""
Async event queue for asyncio-based applications.

This module provides an async-compatible version of the event queue
that integrates seamlessly with asyncio event loops.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from zroky._internal.async_ingestion import AsyncIngestClient
from zroky._internal.ingestion import IngestClient
from zroky._internal.local_mode import LocalWriter

if TYPE_CHECKING:
    from zroky._internal.config import SDKConfig
    from zroky._internal.models import CallEvent

_logger = logging.getLogger(__name__)

# Default maximum queue size
_DEFAULT_MAX_QUEUE_SIZE = 10_000


class AsyncEventQueue:
    """
    Async-compatible event queue for non-blocking event ingestion.
    
    Use this in asyncio applications instead of the sync EventQueue.
    """

    def __init__(self, config: "SDKConfig") -> None:
        self._config = config
        self._max_size = getattr(config, "max_queue_size", _DEFAULT_MAX_QUEUE_SIZE)
        # Use asyncio.Queue for async compatibility
        self._q: asyncio.Queue["CallEvent | None"] = asyncio.Queue(maxsize=self._max_size)
        self._task: asyncio.Task[None] | None = None
        self._dropped_count = 0
        self._shutdown_event = asyncio.Event()

        if config.mode == "local":
            self._writer: AsyncIngestClient | LocalWriter = LocalWriter()
        else:
            self._writer = AsyncIngestClient(config)

    async def start(self) -> None:
        """Start the background flush worker."""
        if self._task is None:
            self._task = asyncio.create_task(
                self._worker(),
                name="zroky-async-flush-worker"
            )

    async def enqueue(self, event: "CallEvent") -> bool:
        """
        Add event to queue. Returns True if enqueued, False if dropped.
        """
        try:
            self._q.put_nowait(event)
            return True
        except asyncio.QueueFull:
            self._dropped_count += 1
            total_dropped = self._dropped_count
            # Log periodically to avoid spam
            if total_dropped % 100 == 1:
                _logger.warning(
                    "[ZROKY] Async event queue full, dropped %d events. "
                    "Consider increasing max_queue_size or checking backend connectivity.",
                    total_dropped
                )
            return False

    @property
    def dropped_count(self) -> int:
        """Number of events dropped due to queue overflow."""
        return self._dropped_count

    async def flush(self, timeout: float = 10.0) -> None:
        """Block until the queue is drained or timeout expires."""
        try:
            await asyncio.wait_for(self._q.join(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    async def shutdown(self) -> None:
        """Flush and stop the background worker."""
        if self._task is not None:
            # Signal shutdown by putting None
            await self._q.put(None)
            self._shutdown_event.set()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            finally:
                self._task = None
                if asyncio.iscoroutinefunction(self._writer.close):
                    await self._writer.close()
                else:
                    self._writer.close()

    async def _worker(self) -> None:
        """Background worker that batches and flushes events."""
        batch: list["CallEvent"] = []
        flush_interval = self._config.flush_interval_seconds
        consecutive_errors = 0
        max_consecutive_errors = 5

        while True:
            try:
                # Wait for event or timeout
                timeout = flush_interval if not batch else 0.1
                try:
                    item = await asyncio.wait_for(
                        self._q.get(),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    item = None

                if item is None and not batch:
                    # Timeout with empty batch
                    continue

                if item is None and batch:
                    # Flush current batch on timeout
                    if await self._flush_batch(batch):
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                    batch = []
                    continue

                if item is None:
                    # Shutdown signal
                    if batch:
                        await self._flush_batch(batch)
                    break

                batch.append(item)
                self._q.task_done()

                if len(batch) >= self._config.batch_size:
                    if await self._flush_batch(batch):
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                    batch = []

                # Back off if too many consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    backoff = min(30.0, 2 ** (consecutive_errors - max_consecutive_errors))
                    await asyncio.sleep(backoff)

            except asyncio.CancelledError:
                # Drain remaining events on cancellation
                if batch:
                    await self._flush_batch(batch)
                # Try to drain queue
                while not self._q.empty():
                    try:
                        event = self._q.get_nowait()
                        if event is not None:
                            batch.append(event)
                            if len(batch) >= self._config.batch_size:
                                await self._flush_batch(batch)
                                batch = []
                    except asyncio.QueueEmpty:
                        break
                if batch:
                    await self._flush_batch(batch)
                raise
            except Exception as exc:
                _logger.error("[ZROKY] Unexpected error in async worker: %s", exc)
                consecutive_errors += 1

    async def _flush_batch(self, batch: list["CallEvent"]) -> bool:
        """Flush batch to writer. Returns True on success."""
        try:
            await self._writer.send_batch(batch)
            return True
        except Exception as exc:
            _logger.debug("[ZROKY] Failed to flush async batch: %s", exc)
            return False
