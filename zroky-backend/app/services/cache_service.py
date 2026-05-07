"""Unified cache service with Redis backend and in-process fallback.

Provides transparent caching for expensive DB queries, API responses, and
computation results. In tests (TESTING=true) or when Redis is unreachable,
automatically falls back to an in-process dict so the test suite never needs
a live Redis server.

Usage:
    cache = CacheService("analytics")
    cache.set("summary:proj_123", json.dumps(data), ttl=300)
    cached = cache.get("summary:proj_123")
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Protocol

import redis

from app.services.redis_client import get_redis_client


class _Backend(Protocol):
    """Internal protocol for cache backends."""

    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def ttl(self, key: str) -> int: ...
    def incr(self, key: str, amount: int = 1, ttl_seconds: int | None = None) -> int: ...


class _MemoryBackend:
    """In-process dict backend with TTL support for tests and Redis failover."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}

    def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if expiry is not None and time.monotonic() > expiry:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        expiry = time.monotonic() + ttl_seconds if ttl_seconds else None
        self._store[key] = (value, expiry)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def ttl(self, key: str) -> int:
        entry = self._store.get(key)
        if entry is None:
            return -2
        _, expiry = entry
        if expiry is None:
            return -1
        remaining = int(expiry - time.monotonic())
        return max(remaining, 0)

    def incr(self, key: str, amount: int = 1, ttl_seconds: int | None = None) -> int:
        value_str = self.get(key)
        try:
            value = int(value_str or 0)
        except ValueError:
            value = 0
        new_value = value + amount
        self.set(key, str(new_value), ttl_seconds=ttl_seconds)
        return new_value

    def clear(self) -> None:
        """Reset state — used by the test suite."""
        self._store.clear()


class _RedisBackend:
    """Redis backend wrapper with graceful degradation."""

    def __init__(self) -> None:
        self._client = get_redis_client()

    def get(self, key: str) -> str | None:
        result = self._client.get(key)
        return result if isinstance(result, str) else None

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        self._client.set(key, value, ex=ttl_seconds)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def exists(self, key: str) -> bool:
        return bool(self._client.exists(key))

    def ttl(self, key: str) -> int:
        return int(self._client.ttl(key))

    def incr(self, key: str, amount: int = 1, ttl_seconds: int | None = None) -> int:
        new_value = self._client.incrby(key, amount)
        if ttl_seconds is not None and new_value == amount:
            # First time the key was created — set TTL
            self._client.expire(key, ttl_seconds)
        return int(new_value)


class CacheService:
    """Namespace-aware cache service with JSON serialization support.

    Automatically falls back to in-process memory when Redis is unreachable
    or when ``TESTING=true``.
    """

    def __init__(self, namespace: str = "default") -> None:
        self._namespace = namespace
        if os.getenv("TESTING", "").lower() == "true":
            self._backend: _Backend = _MemoryBackend()
        else:
            try:
                self._backend = _RedisBackend()
            except redis.RedisError:
                self._backend = _MemoryBackend()

    def _key(self, key: str) -> str:
        return f"zroky:{self._namespace}:{key}"

    def get(self, key: str) -> str | None:
        """Fetch raw string value, or ``None`` if missing / expired."""
        try:
            return self._backend.get(self._key(key))
        except redis.RedisError:
            return None

    def get_json(self, key: str) -> Any | None:
        """Fetch and deserialize JSON value."""
        raw = self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def set(
        self,
        key: str,
        value: str,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store raw string value with optional TTL."""
        try:
            self._backend.set(self._key(key), value, ttl_seconds=ttl_seconds)
        except redis.RedisError:
            pass

    def set_json(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Serialize and store JSON value with optional TTL."""
        self.set(key, json.dumps(value, default=str), ttl_seconds=ttl_seconds)

    def delete(self, key: str) -> None:
        try:
            self._backend.delete(self._key(key))
        except redis.RedisError:
            pass

    def exists(self, key: str) -> bool:
        try:
            return self._backend.exists(self._key(key))
        except redis.RedisError:
            return False

    def ttl(self, key: str) -> int:
        """Return TTL in seconds (-1 = no TTL, -2 = key missing)."""
        try:
            return self._backend.ttl(self._key(key))
        except redis.RedisError:
            return -2

    def incr(
        self,
        key: str,
        amount: int = 1,
        *,
        ttl_seconds: int | None = None,
    ) -> int:
        """Atomically increment a counter, returning the new value."""
        try:
            return self._backend.incr(self._key(key), amount, ttl_seconds=ttl_seconds)
        except redis.RedisError:
            return amount

    def mget(self, keys: list[str]) -> list[str | None]:
        """Batch fetch raw string values."""
        namespaced = [self._key(k) for k in keys]
        try:
            results = self._backend.get if not hasattr(self._backend, "mget") else self._backend.mget
            if hasattr(self._backend, "_client"):
                raw = self._backend._client.mget(namespaced)
                return [v if isinstance(v, str) else None for v in raw]
        except redis.RedisError:
            pass
        # Fallback to individual gets
        return [self.get(k) for k in keys]

    def mget_json(self, keys: list[str]) -> list[Any | None]:
        """Batch fetch and deserialize JSON values."""
        return [json.loads(v) if v is not None else None for v in self.mget(keys)]

    def mset(
        self,
        mapping: dict[str, str],
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Batch store raw string values."""
        try:
            if hasattr(self._backend, "_client"):
                pipe = self._backend._client.pipeline()
                for k, v in mapping.items():
                    pipe.set(self._key(k), v, ex=ttl_seconds)
                pipe.execute()
                return
        except redis.RedisError:
            pass
        for k, v in mapping.items():
            self.set(k, v, ttl_seconds=ttl_seconds)

    def mset_json(
        self,
        mapping: dict[str, Any],
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Batch serialize and store JSON values."""
        str_mapping = {k: json.dumps(v, default=str) for k, v in mapping.items()}
        self.mset(str_mapping, ttl_seconds=ttl_seconds)


def get_cache(namespace: str = "default") -> CacheService:
    """Factory for cache service instances."""
    return CacheService(namespace)


def _cache_key_from_args(*args: Any, **kwargs: Any) -> str:
    """Deterministic cache key from positional and keyword arguments."""
    parts = [repr(a) for a in args] + [f"{k}={repr(v)}" for k, v in sorted(kwargs.items())]
    return hash("|".join(parts)) if parts else ""


def cached(
    *,
    namespace: str,
    ttl_seconds: int = 60,
    key_func: Any | None = None,
    skip_on_none: bool = True,
):
    """Decorator to cache function results in Redis (with in-process fallback).

    Usage::

        @cached(namespace="analytics", ttl_seconds=300)
        def expensive_query(tenant_id: str) -> dict:
            return run_db_query(tenant_id)
    """
    _cache = CacheService(namespace)

    def decorator(func):
        import functools

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = (
                key_func(*args, **kwargs)
                if key_func is not None
                else _cache_key_from_args(*args, **kwargs)
            )
            # Try cache first
            cached_value = _cache.get_json(cache_key)
            if cached_value is not None:
                return cached_value

            # Compute and store
            result = func(*args, **kwargs)
            if result is not None or not skip_on_none:
                _cache.set_json(cache_key, result, ttl_seconds=ttl_seconds)
            return result

        return wrapper

    return decorator


def clear_cache(namespace: str = "default") -> None:
    """Clear all keys in a namespace. Only affects in-process backend."""
    backend = CacheService(namespace)._backend
    if hasattr(backend, "clear"):
        backend.clear()
