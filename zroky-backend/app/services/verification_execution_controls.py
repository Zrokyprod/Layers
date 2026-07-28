"""Shared safety controls for backend-owned system-of-record verification.

Post-execution verification is allowed to be deferred; it must never turn a
degraded provider into a retry storm. Redis is used only for short-lived shared
coordination. The transactional outbox remains the durable source of truth.
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import redis

from app.core.config import get_settings
from app.services.outcome_reconciliation import SourceRecord, SystemOfRecordConnector
from app.services.redis_client import get_redis_client


_ACQUIRE_SLOT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local expires_at = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local token = ARGV[4]
local ttl = tonumber(ARGV[5])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
if redis.call('ZSCORE', key, token) then
  return 1
end
if redis.call('ZCARD', key) >= limit then
  return 0
end
redis.call('ZADD', key, expires_at, token)
redis.call('EXPIRE', key, ttl)
return 1
"""


def _safe_key_part(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_." else "_" for char in value)[:128]


@dataclass(frozen=True)
class VerificationControlDecision:
    allowed: bool
    reason: str | None = None


@dataclass
class VerificationExecutionControls:
    """Redis-backed connector circuit breaker and bounded concurrency lease."""

    project_id: str
    connector_type: str
    token: str
    redis_client: Any | None = None
    enabled: bool | None = None
    fail_closed: bool | None = None
    max_in_flight: int | None = None
    lease_seconds: int | None = None
    failure_threshold: int | None = None
    failure_window_seconds: int | None = None
    circuit_open_seconds: int | None = None
    _lease_acquired: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        settings = get_settings()
        if self.enabled is None:
            testing = os.environ.get("TESTING", "").strip().lower() in {"1", "true", "yes"}
            self.enabled = bool(settings.VERIFICATION_EXECUTION_CONTROLS_ENABLED) and not testing
        if self.fail_closed is None:
            self.fail_closed = bool(settings.VERIFICATION_EXECUTION_CONTROLS_FAIL_CLOSED)
        if self.max_in_flight is None:
            self.max_in_flight = max(1, int(settings.VERIFICATION_CONNECTOR_MAX_IN_FLIGHT))
        if self.lease_seconds is None:
            self.lease_seconds = max(5, int(settings.VERIFICATION_CONNECTOR_LEASE_SECONDS))
        if self.failure_threshold is None:
            self.failure_threshold = max(1, int(settings.VERIFICATION_CONNECTOR_FAILURE_THRESHOLD))
        if self.failure_window_seconds is None:
            self.failure_window_seconds = max(1, int(settings.VERIFICATION_CONNECTOR_FAILURE_WINDOW_SECONDS))
        if self.circuit_open_seconds is None:
            self.circuit_open_seconds = max(1, int(settings.VERIFICATION_CONNECTOR_CIRCUIT_OPEN_SECONDS))

    @property
    def _prefix(self) -> str:
        return f"zroky:verification:{_safe_key_part(self.project_id)}:{_safe_key_part(self.connector_type)}"

    @property
    def _slot_key(self) -> str:
        return f"{self._prefix}:inflight"

    @property
    def _failure_key(self) -> str:
        return f"{self._prefix}:failures"

    @property
    def _open_key(self) -> str:
        return f"{self._prefix}:circuit_open"

    def _client(self) -> Any:
        return self.redis_client if self.redis_client is not None else get_redis_client()

    def acquire(self) -> VerificationControlDecision:
        if not self.enabled:
            return VerificationControlDecision(True)
        try:
            client = self._client()
            if client.get(self._open_key):
                return VerificationControlDecision(False, "connector_circuit_open")
            now = time.time()
            allowed = bool(
                client.eval(
                    _ACQUIRE_SLOT_SCRIPT,
                    1,
                    self._slot_key,
                    now,
                    now + int(self.lease_seconds or 30),
                    int(self.max_in_flight or 1),
                    self.token,
                    int(self.lease_seconds or 30),
                )
            )
            if not allowed:
                return VerificationControlDecision(False, "connector_concurrency_limited")
            self._lease_acquired = True
            return VerificationControlDecision(True)
        except redis.RedisError:
            if self.fail_closed:
                return VerificationControlDecision(False, "verification_controls_unavailable")
            return VerificationControlDecision(True)

    def release(self) -> None:
        if not self.enabled or not self._lease_acquired:
            return
        self._lease_acquired = False
        try:
            self._client().zrem(self._slot_key, self.token)
        except redis.RedisError:
            # The ZSET member has a lease and therefore self-cleans after a
            # process crash or Redis transport failure.
            return

    def record_result(self, metadata: Mapping[str, Any] | None) -> None:
        if not self.enabled:
            return
        details = dict(metadata or {})
        retryable = details.get("retryable") is True
        try:
            status_code = int(details.get("http_status"))
        except (TypeError, ValueError):
            status_code = None
        failed = retryable or (status_code is not None and status_code >= 500)
        try:
            client = self._client()
            if not failed:
                client.delete(self._failure_key)
                return
            failures = int(client.incr(self._failure_key))
            if failures == 1:
                client.expire(self._failure_key, int(self.failure_window_seconds or 60))
            if failures >= int(self.failure_threshold or 3):
                client.set(self._open_key, "1", ex=int(self.circuit_open_seconds or 90))
        except redis.RedisError:
            return


@dataclass
class ControlledConnector:
    """Wrap a remote connector with shared breaker and concurrency controls."""

    connector: SystemOfRecordConnector
    controls: VerificationExecutionControls

    @property
    def connector_type(self) -> str:
        return self.connector.connector_type

    def fetch(self) -> SourceRecord:
        decision = self.controls.acquire()
        if not decision.allowed:
            return SourceRecord(
                record=None,
                record_found=None,
                metadata={
                    "connector_type": self.connector_type,
                    "error": decision.reason,
                    "error_code": decision.reason,
                    "retryable": True,
                    "controlled": True,
                },
            )
        try:
            source = self.connector.fetch()
            self.controls.record_result(source.metadata)
            return source
        except Exception:  # noqa: BLE001
            # A connector that raises before returning metadata is still a
            # provider failure for breaker purposes. Re-raise so the durable
            # outbox retains the original failure semantics.
            self.controls.record_result({"retryable": True})
            raise
        finally:
            self.controls.release()


__all__ = [name for name in globals() if not name.startswith("__")]
