from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from threading import Lock
from typing import Any, Callable, Iterable, Literal, Mapping

import httpx
import redis

from app.core.config import get_settings
from app.db.models import Call
from app.observability.metrics import record_exchange_rate_event
from app.services.redis_client import get_redis_client

BASE_CURRENCY = "USD"
TOKEN_UNIT = "tokens"
SUPPORTED_DISPLAY_CURRENCIES = {"USD", "INR"}
DISPLAY_DECIMAL_PLACES = 2
EXCHANGE_RATE_DECIMAL_PLACES = 8
DISPLAY_ROUNDING_MODE = "HALF_UP"
CURRENCY_SYMBOLS = {
    "USD": "$",
    "INR": "₹",
}
EXCHANGE_RATE_CACHE_KEY = "zroky:exchange_rate:usd_inr:latest"
DisplayCurrency = Literal["USD", "INR"]

_MEMORY_LOCK = Lock()
_MEMORY_EXCHANGE_RATE_CACHE: dict[str, tuple[dict[str, Any], float]] = {}


@dataclass(frozen=True)
class CurrencyDisplayContext:
    requested_display_currency: DisplayCurrency
    display_currency: DisplayCurrency
    exchange_rate_used: float | None
    exchange_rate_timestamp: str | None
    exchange_rate_source: str | None
    exchange_rates_mixed: bool = False
    missing_exchange_rate: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "display_currency": self.display_currency,
            "display_currency_code": self.display_currency,
            "display_currency_symbol": CURRENCY_SYMBOLS[self.display_currency],
            "requested_display_currency": self.requested_display_currency,
            "exchange_rate_used": self.exchange_rate_used,
            "exchange_rate_timestamp": self.exchange_rate_timestamp,
            "exchange_rate_source": self.exchange_rate_source,
            "exchange_rates_mixed": self.exchange_rates_mixed,
            "display_decimal_places": DISPLAY_DECIMAL_PLACES,
            "display_rounding_mode": DISPLAY_ROUNDING_MODE,
            "exchange_rate_decimal_places": EXCHANGE_RATE_DECIMAL_PLACES,
            "cost_currency": BASE_CURRENCY,
            "token_unit": TOKEN_UNIT,
        }


def normalize_display_currency(value: str | None) -> DisplayCurrency:
    normalized = (value or BASE_CURRENCY).strip().upper()
    if normalized in SUPPORTED_DISPLAY_CURRENCIES:
        return normalized  # type: ignore[return-value]
    return "USD"


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def isoformat_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return as_utc(dt).isoformat()


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return as_utc(value)

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None

    try:
        return datetime.fromtimestamp(float(candidate), tz=timezone.utc)
    except ValueError:
        pass

    if len(candidate) == 10 and candidate.count("-") == 2:
        candidate = f"{candidate}T00:00:00+00:00"
    elif candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    return as_utc(parsed)


def as_positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed > 0 else None


def _quantize_decimal(value: Decimal, places: int) -> Decimal:
    quantizer = Decimal("1").scaleb(-places)
    return value.quantize(quantizer, rounding=ROUND_HALF_UP)


def rounded_exchange_rate(value: Any) -> float | None:
    parsed = _to_decimal(value)
    if parsed is None:
        return None
    return float(_quantize_decimal(parsed, EXCHANGE_RATE_DECIMAL_PLACES))


def rounded_display_amount(value: Any) -> float:
    parsed = _to_decimal(value)
    if parsed is None:
        return 0.0
    return float(_quantize_decimal(parsed, DISPLAY_DECIMAL_PLACES))


def _memory_cache_get(cache_key: str, now_ts: float) -> dict[str, Any] | None:
    with _MEMORY_LOCK:
        record = _MEMORY_EXCHANGE_RATE_CACHE.get(cache_key)
        if not record:
            return None

        payload, expires_at = record
        if expires_at <= now_ts:
            _MEMORY_EXCHANGE_RATE_CACHE.pop(cache_key, None)
            return None

        return dict(payload)


def _memory_cache_set(cache_key: str, payload: dict[str, Any], ttl_seconds: int, now_ts: float) -> None:
    with _MEMORY_LOCK:
        _MEMORY_EXCHANGE_RATE_CACHE[cache_key] = (dict(payload), now_ts + ttl_seconds)


def _cache_get() -> dict[str, Any] | None:
    now_ts = time.time()
    cache_key = EXCHANGE_RATE_CACHE_KEY
    try:
        cached = get_redis_client().get(cache_key)
        if not cached:
            return None

        payload = json.loads(cached)
        if isinstance(payload, dict):
            return payload
        return None
    except (redis.RedisError, json.JSONDecodeError):
        return _memory_cache_get(cache_key, now_ts)


def _cache_set(payload: dict[str, Any], ttl_seconds: int) -> None:
    now_ts = time.time()
    cache_key = EXCHANGE_RATE_CACHE_KEY
    serialized = json.dumps(payload, separators=(",", ":"), default=str)
    try:
        get_redis_client().setex(cache_key, ttl_seconds, serialized)
    except redis.RedisError:
        _memory_cache_set(cache_key, payload, ttl_seconds, now_ts)


def _configured_usd_to_inr_rate() -> tuple[float | None, str | None]:
    raw_rate = os.getenv("ZROKY_EXCHANGE_RATE_USD_TO_INR")
    rate = rounded_exchange_rate(raw_rate)
    if rate is None:
        return None, None

    source = (os.getenv("ZROKY_EXCHANGE_RATE_SOURCE") or "configured_static").strip()
    return rate, source[:64] if source else "configured_static"


def _live_source_label() -> str:
    settings = get_settings()
    source = settings.EXCHANGE_RATE_PROVIDER_SOURCE.strip()
    return source[:64] if source else "live_exchangerate_host"


def _fetch_live_exchange_rate_payload() -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.EXCHANGE_RATE_ENABLE_LIVE_FETCH:
        return None

    endpoint = settings.EXCHANGE_RATE_PROVIDER_URL.strip()
    if not endpoint:
        return None

    timeout_seconds = max(0.1, settings.EXCHANGE_RATE_FETCH_TIMEOUT_MS / 1000.0)
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(endpoint)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return None

    if not isinstance(payload, Mapping):
        return None
    return dict(payload)


def _extract_live_rate_payload(payload: Mapping[str, Any], *, checked_at: datetime) -> dict[str, Any] | None:
    rates_mapping = payload.get("rates") if isinstance(payload.get("rates"), Mapping) else {}
    rate = rounded_exchange_rate(
        rates_mapping.get("INR")
        or payload.get("INR")
        or payload.get("usd_to_inr")
        or payload.get("usdInr")
    )
    if rate is None:
        return None

    timestamp = (
        parse_datetime(payload.get("timestamp"))
        or parse_datetime(payload.get("date"))
        or parse_datetime(payload.get("last_updated_at"))
        or parse_datetime(payload.get("updated_at"))
        or checked_at
    )
    if timestamp is None:
        timestamp = checked_at

    return {
        "status": "ok",
        "exchange_rate_usd_to_inr": rate,
        "exchange_rate_timestamp": timestamp.isoformat(),
        "exchange_rate_source": _live_source_label(),
        "fetched_at": checked_at.isoformat(),
    }


def refresh_live_usd_to_inr_rate(*, force: bool = False) -> dict[str, Any]:
    settings = get_settings()
    source = _live_source_label()
    checked_at = datetime.now(timezone.utc)

    if not settings.EXCHANGE_RATE_ENABLE_LIVE_FETCH:
        record_exchange_rate_event(source, "disabled")
        return {
            "status": "disabled",
            "exchange_rate_source": source,
            "exchange_rate_usd_to_inr": None,
            "exchange_rate_timestamp": None,
            "checked_at": checked_at.isoformat(),
        }

    if not force:
        cached = _cache_get()
        if isinstance(cached, Mapping) and str(cached.get("status") or "").strip().lower() == "ok":
            fetched_at = parse_datetime(cached.get("fetched_at"))
            min_refresh_seconds = max(60, int(settings.EXCHANGE_RATE_CACHE_TTL_SECONDS // 2))
            if fetched_at is not None and (checked_at - fetched_at).total_seconds() < min_refresh_seconds:
                rate = rounded_exchange_rate(cached.get("exchange_rate_usd_to_inr"))
                if rate is not None:
                    record_exchange_rate_event(source, "cached_fresh")
                    return {
                        "status": "cached_fresh",
                        "exchange_rate_source": str(cached.get("exchange_rate_source") or source)[:64],
                        "exchange_rate_usd_to_inr": rate,
                        "exchange_rate_timestamp": str(cached.get("exchange_rate_timestamp") or fetched_at.isoformat()),
                        "checked_at": checked_at.isoformat(),
                    }

    fetched_payload = _fetch_live_exchange_rate_payload()
    if fetched_payload is None:
        error_payload = {
            "status": "error",
            "exchange_rate_source": source,
            "error": "fetch_failed",
            "fetched_at": checked_at.isoformat(),
        }
        _cache_set(error_payload, max(1, settings.EXCHANGE_RATE_FAILURE_CACHE_TTL_SECONDS))
        record_exchange_rate_event(source, "fetch_failed")
        return {
            "status": "fetch_failed",
            "exchange_rate_source": source,
            "exchange_rate_usd_to_inr": None,
            "exchange_rate_timestamp": None,
            "checked_at": checked_at.isoformat(),
        }

    success_payload = _extract_live_rate_payload(fetched_payload, checked_at=checked_at)
    if success_payload is None:
        error_payload = {
            "status": "error",
            "exchange_rate_source": source,
            "error": "invalid_payload",
            "fetched_at": checked_at.isoformat(),
        }
        _cache_set(error_payload, max(1, settings.EXCHANGE_RATE_FAILURE_CACHE_TTL_SECONDS))
        record_exchange_rate_event(source, "invalid_payload")
        return {
            "status": "invalid_payload",
            "exchange_rate_source": source,
            "exchange_rate_usd_to_inr": None,
            "exchange_rate_timestamp": None,
            "checked_at": checked_at.isoformat(),
        }

    _cache_set(success_payload, max(1, settings.EXCHANGE_RATE_CACHE_TTL_SECONDS))
    record_exchange_rate_event(source, "refreshed")
    return {
        "status": "ok",
        "exchange_rate_source": str(success_payload["exchange_rate_source"]),
        "exchange_rate_usd_to_inr": float(success_payload["exchange_rate_usd_to_inr"]),
        "exchange_rate_timestamp": str(success_payload["exchange_rate_timestamp"]),
        "checked_at": checked_at.isoformat(),
    }


def _cached_live_usd_to_inr_rate(*, now: datetime) -> tuple[float | None, datetime | None, str | None]:
    settings = get_settings()
    if not settings.EXCHANGE_RATE_ENABLE_LIVE_FETCH:
        return None, None, None

    cached = _cache_get()
    if not isinstance(cached, Mapping):
        return None, None, None

    if str(cached.get("status") or "").strip().lower() != "ok":
        source = str(cached.get("exchange_rate_source") or _live_source_label()).strip()[:64]
        record_exchange_rate_event(source or _live_source_label(), "cached_error")
        return None, None, None

    rate = rounded_exchange_rate(cached.get("exchange_rate_usd_to_inr"))
    timestamp = parse_datetime(cached.get("exchange_rate_timestamp"))
    fetched_at = parse_datetime(cached.get("fetched_at")) or timestamp
    if rate is None or timestamp is None:
        return None, None, None

    max_stale_seconds = max(1, settings.EXCHANGE_RATE_MAX_STALE_SECONDS)
    effective_now = as_utc(now)
    if fetched_at is not None and (effective_now - fetched_at).total_seconds() > max_stale_seconds:
        source = str(cached.get("exchange_rate_source") or _live_source_label()).strip()[:64]
        record_exchange_rate_event(source or _live_source_label(), "cached_stale")
        return None, None, None

    source = str(cached.get("exchange_rate_source") or _live_source_label()).strip()[:64]
    if not source:
        source = _live_source_label()
    return rate, timestamp, f"{source}_cached"[:64]


def _resolve_default_usd_to_inr_rate(
    *,
    captured_at: datetime,
) -> tuple[float | None, datetime | None, str | None]:
    live_rate, live_timestamp, live_source = _cached_live_usd_to_inr_rate(now=captured_at)
    if live_rate is not None and live_timestamp is not None:
        record_exchange_rate_event(live_source or _live_source_label(), "resolved")
        return live_rate, live_timestamp, live_source

    configured_rate, configured_source = _configured_usd_to_inr_rate()
    if configured_rate is not None:
        source = (configured_source or "configured_static")[:64]
        record_exchange_rate_event(source, "resolved")
        return configured_rate, captured_at, source

    record_exchange_rate_event("missing", "missing")
    return None, None, None


def get_exchange_rate_debug_snapshot(*, now: datetime | None = None) -> dict[str, Any]:
    settings = get_settings()
    checked_at = as_utc(now or datetime.now(timezone.utc))
    configured_rate, configured_source = _configured_usd_to_inr_rate()

    cache_payload = _cache_get() if settings.EXCHANGE_RATE_ENABLE_LIVE_FETCH else None
    cache_status = "disabled" if not settings.EXCHANGE_RATE_ENABLE_LIVE_FETCH else "empty"
    cache_rate: float | None = None
    cache_timestamp: datetime | None = None
    cache_fetched_at: datetime | None = None
    cache_source: str | None = None
    cache_error: str | None = None

    if isinstance(cache_payload, Mapping):
        normalized_status = str(cache_payload.get("status") or "").strip().lower()
        cache_status = normalized_status or "unknown"
        cache_rate = rounded_exchange_rate(cache_payload.get("exchange_rate_usd_to_inr"))
        cache_timestamp = parse_datetime(cache_payload.get("exchange_rate_timestamp"))
        cache_fetched_at = parse_datetime(cache_payload.get("fetched_at"))
        source_candidate = str(cache_payload.get("exchange_rate_source") or "").strip()
        cache_source = source_candidate[:64] if source_candidate else None
        error_candidate = str(cache_payload.get("error") or "").strip()
        cache_error = error_candidate[:64] if error_candidate else None

    reference_time = cache_fetched_at or cache_timestamp
    cache_age_seconds: int | None = None
    cache_is_stale: bool | None = None
    if reference_time is not None:
        cache_age_seconds = max(0, int((checked_at - reference_time).total_seconds()))
        cache_is_stale = cache_age_seconds > max(1, int(settings.EXCHANGE_RATE_MAX_STALE_SECONDS))

    cache_is_usable = (
        cache_status == "ok"
        and cache_rate is not None
        and cache_timestamp is not None
        and cache_is_stale is False
    )

    resolved_rate: float | None = None
    resolved_timestamp: datetime | None = None
    resolved_source: str | None = None
    resolution_mode = "missing"
    if cache_is_usable:
        resolved_rate = cache_rate
        resolved_timestamp = cache_timestamp
        resolved_source = f"{(cache_source or _live_source_label())}_cached"[:64]
        resolution_mode = "live_cached"
    elif configured_rate is not None:
        resolved_rate = configured_rate
        resolved_timestamp = checked_at
        resolved_source = (configured_source or "configured_static")[:64]
        resolution_mode = "configured_static"

    return {
        "checked_at": checked_at.isoformat(),
        "live_fetch": {
            "enabled": bool(settings.EXCHANGE_RATE_ENABLE_LIVE_FETCH),
            "provider_url": settings.EXCHANGE_RATE_PROVIDER_URL.strip() or None,
            "provider_source": _live_source_label(),
            "refresh_interval_minutes": int(settings.EXCHANGE_RATE_REFRESH_INTERVAL_MINUTES),
            "cache_ttl_seconds": int(settings.EXCHANGE_RATE_CACHE_TTL_SECONDS),
            "failure_cache_ttl_seconds": int(settings.EXCHANGE_RATE_FAILURE_CACHE_TTL_SECONDS),
            "max_stale_seconds": int(settings.EXCHANGE_RATE_MAX_STALE_SECONDS),
        },
        "cache": {
            "status": cache_status,
            "exchange_rate_usd_to_inr": cache_rate,
            "exchange_rate_timestamp": isoformat_utc(cache_timestamp),
            "fetched_at": isoformat_utc(cache_fetched_at),
            "exchange_rate_source": cache_source,
            "cache_age_seconds": cache_age_seconds,
            "is_stale": cache_is_stale,
            "is_usable": cache_is_usable,
            "error": cache_error,
        },
        "configured_fallback": {
            "is_available": configured_rate is not None,
            "exchange_rate_usd_to_inr": configured_rate,
            "exchange_rate_source": configured_source,
        },
        "resolved_default": {
            "mode": resolution_mode,
            "exchange_rate_usd_to_inr": resolved_rate,
            "exchange_rate_timestamp": isoformat_utc(resolved_timestamp),
            "exchange_rate_source": resolved_source,
        },
    }


def resolve_ingest_exchange_rate(
    payload: dict[str, Any],
    *,
    captured_at: datetime,
) -> dict[str, Any]:
    rate = rounded_exchange_rate(payload.get("exchange_rate_usd_to_inr"))
    source = str(payload.get("exchange_rate_source") or "").strip()[:64] or None

    if rate is not None:
        timestamp = parse_datetime(payload.get("exchange_rate_timestamp")) or captured_at
        resolved_source = source or "ingest_payload"
        record_exchange_rate_event(resolved_source, "resolved")
        return {
            "exchange_rate_usd_to_inr": rate,
            "exchange_rate_timestamp": timestamp,
            "exchange_rate_source": resolved_source,
        }

    fallback_rate, fallback_timestamp, fallback_source = _resolve_default_usd_to_inr_rate(
        captured_at=captured_at,
    )
    return {
        "exchange_rate_usd_to_inr": fallback_rate,
        "exchange_rate_timestamp": fallback_timestamp,
        "exchange_rate_source": fallback_source,
    }


def call_has_inr_rate(call: Call) -> bool:
    return (
        rounded_exchange_rate(call.exchange_rate_usd_to_inr) is not None
        and call.exchange_rate_timestamp is not None
    )


def build_currency_context(
    calls: Iterable[Call],
    requested_display_currency: str | None,
) -> CurrencyDisplayContext:
    requested = normalize_display_currency(requested_display_currency)
    call_list = list(calls)
    if requested == "USD":
        return CurrencyDisplayContext(
            requested_display_currency=requested,
            display_currency="USD",
            exchange_rate_used=None,
            exchange_rate_timestamp=None,
            exchange_rate_source=None,
        )

    if not call_list or any(not call_has_inr_rate(call) for call in call_list):
        return CurrencyDisplayContext(
            requested_display_currency=requested,
            display_currency="USD",
            exchange_rate_used=None,
            exchange_rate_timestamp=None,
            exchange_rate_source=None,
            missing_exchange_rate=True,
        )

    rates = [
        rate
        for rate in (rounded_exchange_rate(call.exchange_rate_usd_to_inr) for call in call_list)
        if rate is not None
    ]
    rounded_rates = {round(rate, EXCHANGE_RATE_DECIMAL_PLACES) for rate in rates}
    timestamps = [
        as_utc(call.exchange_rate_timestamp)
        for call in call_list
        if call.exchange_rate_timestamp is not None
    ]
    sources = {
        str(call.exchange_rate_source).strip()
        for call in call_list
        if call.exchange_rate_source and str(call.exchange_rate_source).strip()
    }

    return CurrencyDisplayContext(
        requested_display_currency=requested,
        display_currency="INR",
        exchange_rate_used=next(iter(rounded_rates)) if len(rounded_rates) == 1 else None,
        exchange_rate_timestamp=isoformat_utc(max(timestamps)) if timestamps else None,
        exchange_rate_source=next(iter(sources)) if len(sources) == 1 else "mixed",
        exchange_rates_mixed=len(rounded_rates) > 1 or len(sources) > 1,
    )


def convert_usd_amount(
    amount_usd: float,
    *,
    call: Call | None = None,
    context: CurrencyDisplayContext,
) -> float:
    amount = _to_decimal(amount_usd) or Decimal("0")
    if context.display_currency != "INR":
        return rounded_display_amount(amount)

    rate = _to_decimal(call.exchange_rate_usd_to_inr if call is not None else context.exchange_rate_used)
    if rate is None:
        return rounded_display_amount(amount)
    return rounded_display_amount(amount * rate)


def aggregate_display_total(
    calls: Iterable[Call],
    amount_selector: Callable[[Call], float],
    *,
    context: CurrencyDisplayContext,
) -> float:
    total = Decimal("0")
    for call in calls:
        amount = _to_decimal(amount_selector(call)) or Decimal("0")
        if context.display_currency == "INR":
            rate = _to_decimal(call.exchange_rate_usd_to_inr)
            if rate is not None:
                amount *= rate
        total += amount
    return rounded_display_amount(total)


def append_confidence_reason(base_reason: str | None, reason: str) -> str:
    if not base_reason:
        return reason
    parts = [part.strip() for part in base_reason.split(";") if part.strip()]
    if reason not in parts:
        parts.append(reason)
    return ";".join(parts)
