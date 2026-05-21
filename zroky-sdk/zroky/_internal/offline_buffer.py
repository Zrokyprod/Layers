# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""
Offline-mode persistent buffer for the ZROKY SDK.

When the ingest endpoint is unreachable (network failure, DNS, server 5xx,
circuit breaker open), events are appended to a local newline-delimited JSON
file. On reconnect they are replayed to the backend in chronological order.

Design goals:
- Crash-safe: each event is one append-only line, fsync'd on flush.
- Bounded: caps total disk usage to avoid unbounded growth on long outages.
- Cheap: no SQLite, just a single file handle behind a lock.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Iterable

_DEFAULT_BUFFER_PATH = Path.home() / ".zroky" / "offline_buffer.ndjson"
_DEFAULT_MAX_BYTES = 25 * 1024 * 1024  # 25 MB cap per buffer file


class OfflineBuffer:
    """File-backed event buffer used as a fallback when the network is down."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        self._path = Path(
            path
            or os.environ.get("ZROKY_OFFLINE_BUFFER", str(_DEFAULT_BUFFER_PATH))
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._max_bytes = max(0, int(max_bytes))

    @property
    def path(self) -> Path:
        return self._path

    def is_empty(self) -> bool:
        return not self._path.exists() or self._path.stat().st_size == 0

    def size_bytes(self) -> int:
        return self._path.stat().st_size if self._path.exists() else 0

    def append(self, payloads: Iterable[dict]) -> int:
        """Append one or more event payloads. Returns the number of bytes written."""
        with self._lock:
            written = 0
            current_size = self.size_bytes()
            with self._path.open("a", encoding="utf-8") as fh:
                for payload in payloads:
                    line = json.dumps(payload, default=str, separators=(",", ":")) + "\n"
                    encoded_len = len(line.encode("utf-8"))
                    if current_size + encoded_len > self._max_bytes:
                        # Drop the event silently — the SDK never blocks the
                        # host application even on disk pressure.
                        break
                    fh.write(line)
                    written += encoded_len
                    current_size += encoded_len
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass  # fsync may not be supported on all filesystems
            return written

    def drain(self) -> list[dict]:
        """Atomically read and remove all buffered payloads.

        Returns the list of payloads in insertion order. The buffer file is
        truncated only after the contents have been successfully read.
        """
        with self._lock:
            if not self._path.exists():
                return []
            try:
                with self._path.open("r", encoding="utf-8") as fh:
                    lines = fh.readlines()
            except OSError:
                return []

            payloads: list[dict] = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    payloads.append(json.loads(line))
                except (ValueError, json.JSONDecodeError):
                    continue

            # Truncate after successful read.
            try:
                self._path.write_text("", encoding="utf-8")
            except OSError:
                pass

            return payloads

    def clear(self) -> None:
        """Reset the buffer (used by tests)."""
        with self._lock:
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                pass
