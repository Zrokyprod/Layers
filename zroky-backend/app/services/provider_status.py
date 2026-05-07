from __future__ import annotations

import ipaddress
import json
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx
import redis

from app.core.config import get_settings
from app.services.redis_client import get_redis_client

_MEMORY_LOCK = Lock()
_MEMORY_PROVIDER_STATUS_CACHE: dict[str, tuple[dict[str, Any], float]] = {}


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                return int(float(text))
            except ValueError:
                return 0
    return 0


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _normalize_provider_status(status: str) -> str:
    normalized = status.strip().lower()
    if not normalized:
        return "unknown"

    if normalized in {"none", "operational", "ok", "up", "healthy"}:
        return "operational"
    if normalized in {"minor", "major", "degraded", "partial_outage"}:
        return "degraded"
    if normalized in {"critical", "outage", "down"}:
        return "outage"
    return normalized


def _provider_status_cache_key(provider: str) -> str:
    return f"zroky:provider:status:{provider}"


def _memory_cache_get(provider: str, now_ts: float) -> dict[str, Any] | None:
    with _MEMORY_LOCK:
        record = _MEMORY_PROVIDER_STATUS_CACHE.get(provider)
        if not record:
            return None

        payload, expires_at = record
        if expires_at <= now_ts:
            _MEMORY_PROVIDER_STATUS_CACHE.pop(provider, None)
            return None

        return dict(payload)


def _memory_cache_set(provider: str, payload: dict[str, Any], ttl_seconds: int, now_ts: float) -> None:
    with _MEMORY_LOCK:
        _MEMORY_PROVIDER_STATUS_CACHE[provider] = (dict(payload), now_ts + ttl_seconds)


def _cache_get(provider: str) -> dict[str, Any] | None:
    now_ts = time.time()
    cache_key = _provider_status_cache_key(provider)
    try:
        cached = get_redis_client().get(cache_key)
        if not cached:
            return None

        payload = json.loads(cached)
        if isinstance(payload, dict):
            return payload
        return None
    except (redis.RedisError, json.JSONDecodeError):
        return _memory_cache_get(provider, now_ts)


def _cache_set(provider: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    now_ts = time.time()
    cache_key = _provider_status_cache_key(provider)
    serialized = json.dumps(payload, separators=(",", ":"))
    try:
        get_redis_client().setex(cache_key, ttl_seconds, serialized)
    except redis.RedisError:
        _memory_cache_set(provider, payload, ttl_seconds, now_ts)


def _parse_endpoint_map(raw_value: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}

    endpoints: dict[str, str] = {}
    for key, value in parsed.items():
        provider = _as_str(key).lower()
        endpoint = _as_str(value)
        if provider and endpoint:
            endpoints[provider] = endpoint
    return endpoints


def _extract_payload_status(payload: Mapping[str, Any]) -> str:
    provider_status_raw = payload.get("provider_status")
    if isinstance(provider_status_raw, Mapping):
        return _normalize_provider_status(_as_str(provider_status_raw.get("status")))
    return _normalize_provider_status(_as_str(provider_status_raw))


def _extract_payload_p95(payload: Mapping[str, Any]) -> int:
    trend = payload.get("provider_latency_trend_ms")
    nested_trend_p95 = trend.get("p95") if isinstance(trend, Mapping) else None
    latency = payload.get("provider_latency")
    nested_latency_p95 = latency.get("p95_ms") if isinstance(latency, Mapping) else None

    return _as_int(
        payload.get("provider_latency_p95_ms")
        or nested_latency_p95
        or nested_trend_p95
    )


def _extract_payload_p99(payload: Mapping[str, Any]) -> int:
    trend = payload.get("provider_latency_trend_ms")
    nested_trend_p99 = trend.get("p99") if isinstance(trend, Mapping) else None
    latency = payload.get("provider_latency")
    nested_latency_p99 = latency.get("p99_ms") if isinstance(latency, Mapping) else None

    return _as_int(
        payload.get("provider_latency_p99_ms")
        or nested_latency_p99
        or nested_trend_p99
    )


_BLOCKED_HOSTS: frozenset[str] = frozenset({
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",
})


def _is_safe_provider_url(endpoint: str) -> bool:
    """Reject URLs that could be used for SSRF attacks."""
    try:
        parsed = urlparse(endpoint)
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        return False
    if hostname in _BLOCKED_HOSTS:
        return False
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return False
    except ValueError:
        pass  # hostname, not a bare IP — allowed
    return True


def _fetch_status_from_endpoint(*, endpoint: str, timeout_ms: int) -> dict[str, Any] | None:
    if not _is_safe_provider_url(endpoint):
        return None
    timeout_seconds = max(0.1, timeout_ms / 1000.0)
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(endpoint)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return None

    if not isinstance(data, Mapping):
        return None

    status_raw = _as_str(data.get("status"))
    if not status_raw and isinstance(data.get("status"), Mapping):
        status_raw = _as_str(data["status"].get("indicator"))

    latency = data.get("latency") if isinstance(data.get("latency"), Mapping) else {}
    p95 = _as_int(data.get("provider_latency_p95_ms") or latency.get("p95_ms"))
    p99 = _as_int(data.get("provider_latency_p99_ms") or latency.get("p99_ms"))

    return {
        "provider_status": _normalize_provider_status(status_raw),
        "provider_latency_p95_ms": p95,
        "provider_latency_p99_ms": p99,
    }


def _probe_provider_credentials(*, provider: str, timeout_ms: int) -> tuple[bool | None, str | None]:
    settings = get_settings()
    normalized_provider = _as_str(provider).lower()

    endpoint = ""
    headers: dict[str, str] = {}
    if normalized_provider == "openai":
        api_key = _as_str(settings.OPENAI_API_KEY)
        if not api_key:
            return None, None
        endpoint = "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif normalized_provider == "anthropic":
        api_key = _as_str(settings.ANTHROPIC_API_KEY)
        if not api_key:
            return None, None
        endpoint = "https://api.anthropic.com/v1/models"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    else:
        return None, None

    timeout_seconds = max(0.1, timeout_ms / 1000.0)
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(endpoint, headers=headers)
    except Exception:
        return False, "Provider credential probe request failed."

    if 200 <= response.status_code < 300:
        return True, None
    if response.status_code in {401, 403}:
        return False, "Provider rejected credentials."
    return False, f"Provider credential probe returned HTTP {response.status_code}."


def resolve_provider_status_context(*, provider: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    timeout_ms = max(100, settings.PROVIDER_STATUS_FETCH_TIMEOUT_MS)
    cache_ttl_seconds = max(1, settings.PROVIDER_STATUS_CACHE_TTL_SECONDS)

    normalized_provider = _as_str(provider).lower() or "unknown"
    payload_status = _extract_payload_status(payload)
    payload_p95 = _extract_payload_p95(payload)
    payload_p99 = _extract_payload_p99(payload)

    if payload_status != "unknown":
        return {
            "provider_status": payload_status,
            "provider_latency_p95_ms": payload_p95,
            "provider_latency_p99_ms": payload_p99,
            "status_fetch_timeout_ms": timeout_ms,
            "status_cache_ttl_seconds": cache_ttl_seconds,
            "status_fallback_used": False,
        }

    cached = _cache_get(normalized_provider)
    if cached is not None:
        return {
            "provider_status": _normalize_provider_status(_as_str(cached.get("provider_status"))),
            "provider_latency_p95_ms": payload_p95 or _as_int(cached.get("provider_latency_p95_ms")),
            "provider_latency_p99_ms": payload_p99 or _as_int(cached.get("provider_latency_p99_ms")),
            "status_fetch_timeout_ms": timeout_ms,
            "status_cache_ttl_seconds": cache_ttl_seconds,
            "status_fallback_used": True,
        }

    endpoint_map = _parse_endpoint_map(settings.PROVIDER_STATUS_ENDPOINTS_JSON)
    endpoint = endpoint_map.get(normalized_provider)
    if endpoint:
        fetched = _fetch_status_from_endpoint(endpoint=endpoint, timeout_ms=timeout_ms)
        if fetched is not None:
            _cache_set(normalized_provider, fetched, cache_ttl_seconds)
            return {
                "provider_status": _normalize_provider_status(_as_str(fetched.get("provider_status"))),
                "provider_latency_p95_ms": payload_p95 or _as_int(fetched.get("provider_latency_p95_ms")),
                "provider_latency_p99_ms": payload_p99 or _as_int(fetched.get("provider_latency_p99_ms")),
                "status_fetch_timeout_ms": timeout_ms,
                "status_cache_ttl_seconds": cache_ttl_seconds,
                "status_fallback_used": False,
            }

    return {
        "provider_status": "unknown",
        "provider_latency_p95_ms": payload_p95,
        "provider_latency_p99_ms": payload_p99,
        "status_fetch_timeout_ms": timeout_ms,
        "status_cache_ttl_seconds": cache_ttl_seconds,
        "status_fallback_used": True,
    }


def verify_provider_connection(provider: str) -> dict[str, Any]:
    settings = get_settings()
    timeout_ms = max(100, settings.PROVIDER_STATUS_FETCH_TIMEOUT_MS)
    cache_ttl_seconds = max(1, settings.PROVIDER_STATUS_CACHE_TTL_SECONDS)
    checked_at = datetime.now(timezone.utc)

    normalized_provider = _as_str(provider).lower() or "unknown"

    credential_probe_ok, credential_probe_error = _probe_provider_credentials(
        provider=normalized_provider,
        timeout_ms=timeout_ms,
    )
    if credential_probe_ok is True:
        return {
            "provider": normalized_provider,
            "verified": True,
            "provider_status": "operational",
            "message": "Credentialed provider handshake succeeded.",
            "last_error": None,
            "checked_at": checked_at,
            "status_fetch_timeout_ms": timeout_ms,
            "status_cache_ttl_seconds": cache_ttl_seconds,
            "status_fallback_used": False,
        }
    if credential_probe_ok is False:
        failure_message = credential_probe_error or "Credentialed provider handshake failed."
        return {
            "provider": normalized_provider,
            "verified": False,
            "provider_status": "unknown",
            "message": failure_message,
            "last_error": failure_message,
            "checked_at": checked_at,
            "status_fetch_timeout_ms": timeout_ms,
            "status_cache_ttl_seconds": cache_ttl_seconds,
            "status_fallback_used": False,
        }

    endpoint_map = _parse_endpoint_map(settings.PROVIDER_STATUS_ENDPOINTS_JSON)
    endpoint = endpoint_map.get(normalized_provider)

    if endpoint:
        fetched = _fetch_status_from_endpoint(endpoint=endpoint, timeout_ms=timeout_ms)
        if fetched is not None:
            _cache_set(normalized_provider, fetched, cache_ttl_seconds)
            provider_status = _normalize_provider_status(_as_str(fetched.get("provider_status")))
            verified = provider_status in {"operational", "degraded"}
            return {
                "provider": normalized_provider,
                "verified": verified,
                "provider_status": provider_status,
                "message": (
                    f"Provider check succeeded with status '{provider_status}'."
                    if verified
                    else f"Provider reachable but status is '{provider_status}'."
                ),
                "last_error": None if verified else f"provider_status={provider_status}",
                "checked_at": checked_at,
                "status_fetch_timeout_ms": timeout_ms,
                "status_cache_ttl_seconds": cache_ttl_seconds,
                "status_fallback_used": False,
            }

    cached = _cache_get(normalized_provider)
    if cached is not None:
        provider_status = _normalize_provider_status(_as_str(cached.get("provider_status")))
        verified = provider_status in {"operational", "degraded"}
        return {
            "provider": normalized_provider,
            "verified": verified,
            "provider_status": provider_status,
            "message": (
                f"Live status fetch unavailable; using cached status '{provider_status}'."
            ),
            "last_error": None if verified else f"provider_status={provider_status} (cached)",
            "checked_at": checked_at,
            "status_fetch_timeout_ms": timeout_ms,
            "status_cache_ttl_seconds": cache_ttl_seconds,
            "status_fallback_used": True,
        }

    if not endpoint:
        message = "Provider status endpoint is not configured for this provider."
    else:
        message = "Provider status check failed and no cached fallback is available."

    return {
        "provider": normalized_provider,
        "verified": False,
        "provider_status": "unknown",
        "message": message,
        "last_error": message,
        "checked_at": checked_at,
        "status_fetch_timeout_ms": timeout_ms,
        "status_cache_ttl_seconds": cache_ttl_seconds,
        "status_fallback_used": True,
    }
