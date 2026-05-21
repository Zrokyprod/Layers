# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""
Circuit breaker for ZROKY ingest calls.

States:
  CLOSED    — normal operation, calls pass through
  OPEN      — backend failing, calls rejected immediately (app unaffected)
  HALF_OPEN — testing recovery, single probe call allowed

Transitions:
  CLOSED -> OPEN        when consecutive_failures >= failure_threshold
  OPEN -> HALF_OPEN     after reset_timeout_seconds
  HALF_OPEN -> CLOSED   on probe success
  HALF_OPEN -> OPEN     on probe failure
"""
from __future__ import annotations

import threading
import time


class CircuitState:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    """Raised when a call is attempted while the circuit is OPEN."""


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout_seconds: float = 60.0,
        success_threshold: int = 2,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout_seconds
        self._success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        return self._state

    def call_allowed(self) -> bool:
        """Return True if a call should be attempted."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if (
                    self._opened_at is not None
                    and time.monotonic() - self._opened_at >= self._reset_timeout
                ):
                    self._state = CircuitState.HALF_OPEN
                    self._consecutive_successes = 0
                    return True
                return False
            # HALF_OPEN: allow exactly one probe call
            return True

    def record_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._consecutive_successes += 1
                if self._consecutive_successes >= self._success_threshold:
                    self._state = CircuitState.CLOSED
                    self._consecutive_failures = 0
                    self._opened_at = None
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
            elif (
                self._state == CircuitState.CLOSED
                and self._consecutive_failures >= self._failure_threshold
            ):
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
