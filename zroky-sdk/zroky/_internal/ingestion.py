"""
Ingest HTTP client — sends batched call events to the ZROKY backend.
Includes retry with exponential backoff (with jitter) and circuit breaker integration.
"""
from __future__ import annotations

import json
import random
import time
from typing import Any

import httpx

from zroky._internal.circuit_breaker import CircuitBreaker
from zroky._internal.config import SDKConfig
from zroky._internal.models import CallEvent
from zroky._internal.offline_buffer import OfflineBuffer

_INGEST_PATH = "/api/v1/ingest"
_MAX_RETRIES = 3
_BASE_BACKOFF_S = 0.5
_MAX_BACKOFF_S = 30.0
_REQUEST_TIMEOUT_S = 8.0
_REPLAY_CHUNK_SIZE = 200


def _calculate_backoff(attempt: int) -> float:
    """Calculate backoff with jitter for congestion handling."""
    # Exponential backoff: 0.5s, 1s, 2s
    exponential = _BASE_BACKOFF_S * (2 ** attempt)
    # Add 0-25% jitter to avoid thundering herd
    jitter = random.uniform(0, exponential * 0.25)
    return min(exponential + jitter, _MAX_BACKOFF_S)


class IngestClient:
    def __init__(self, config: SDKConfig) -> None:
        self._config = config
        self._circuit = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            reset_timeout_seconds=config.circuit_breaker_reset_timeout_seconds,
        )
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.api_key:
            headers["x-api-key"] = config.api_key
        if config.project:
            headers["x-project-id"] = config.project

        # Configure connection pool for high-throughput scenarios
        limits = httpx.Limits(
            max_keepalive_connections=5,
            max_connections=10,
            keepalive_expiry=30.0,
        )

        self._client = httpx.Client(
            base_url=config.ingest_url,
            headers=headers,
            timeout=_REQUEST_TIMEOUT_S,
            limits=limits,
        )

        # Offline buffer for spooling events to disk when the backend is unreachable.
        self._offline_buffer = OfflineBuffer() if config.enable_offline_buffer else None

    @property
    def circuit_state(self) -> str:
        return self._circuit.state

    def _post_payload(self, payload: dict[str, Any]) -> bool:
        """Post a payload with retry. Returns True on 2xx/4xx, False on persistent failure."""
        data = json.dumps(payload, default=str).encode()
        for attempt in range(_MAX_RETRIES):
            try:
                response = self._client.post(_INGEST_PATH, content=data)
                if response.status_code < 500:
                    self._circuit.record_success()
                    return True
                self._circuit.record_failure()
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError):
                self._circuit.record_failure()
            except Exception:  # noqa: BLE001
                self._circuit.record_failure()
                return False
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_calculate_backoff(attempt))
        return False

    def _replay_offline_buffer(self) -> None:
        """Drain and replay any buffered events. No-op if buffer is empty/disabled."""
        if self._offline_buffer is None or self._offline_buffer.is_empty():
            return
        if not self._circuit.call_allowed():
            return
        payloads = self._offline_buffer.drain()
        # Replay in chunks to avoid huge requests.
        for i in range(0, len(payloads), _REPLAY_CHUNK_SIZE):
            chunk = payloads[i : i + _REPLAY_CHUNK_SIZE]
            ok = self._post_payload({"events": chunk})
            if not ok:
                # Failed again — re-spool remaining payloads and bail.
                self._offline_buffer.append(payloads[i:])
                return

    def send_batch(self, events: list[CallEvent]) -> None:
        """
        Send a batch of events to the ingest endpoint.
        On persistent failure events are spooled to the offline buffer (if enabled).
        """
        if not events:
            return

        # Try to flush any previously-buffered events first so they are replayed
        # in chronological order before the new batch.
        self._replay_offline_buffer()

        new_payloads = [e.to_ingest_payload() for e in events]

        if not self._circuit.call_allowed():
            # Circuit OPEN — buffer to disk for replay later instead of dropping.
            if self._offline_buffer is not None:
                self._offline_buffer.append(new_payloads)
            return

        ok = self._post_payload({"events": new_payloads})
        if not ok and self._offline_buffer is not None:
            self._offline_buffer.append(new_payloads)

    def close(self) -> None:
        # Best-effort flush of buffered events before closing.
        try:
            self._replay_offline_buffer()
        except Exception:  # noqa: BLE001
            pass
        self._client.close()
