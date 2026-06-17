from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import redis

from app.services.redis_client import get_redis_client

COST_BUCKET_SECONDS = 15 * 60
COST_BASELINE_WINDOW_DAYS = 14
COST_BASELINE_BUCKETS = int((COST_BASELINE_WINDOW_DAYS * 24 * 60 * 60) / COST_BUCKET_SECONDS)
PRICING_STALE_THRESHOLD_DAYS = 14
BASE_CURRENCY = "USD"
TOKEN_UNIT = "tokens"

_FALLBACK_PROVIDER_MODEL_RATES_PER_1M: dict[str, dict[str, dict[str, float]]] = {
    "openai": {
        "gpt-4o": {
            "input": 5.0,
            "output": 15.0,
            "reasoning": 0.0,
            "cache_create": 0.0,
            "cache_read": 0.0,
        },
        "o3": {
            "input": 15.0,
            "output": 15.0,
            "reasoning": 60.0,
            "cache_create": 0.0,
            "cache_read": 0.0,
        },
    },
    "anthropic": {
        "claude-3-7-sonnet": {
            "input": 3.0,
            "output": 15.0,
            "reasoning": 0.0,
            "cache_create": 3.0,
            "cache_read": 0.3,
        },
    },
    "google": {
        "gemini-2.5-pro": {
            "input": 3.5,
            "output": 10.5,
            "reasoning": 0.0,
            "cache_create": 3.5,
            "cache_read": 0.35,
        },
    },
}
_PRICING_CACHE_LOCK = threading.Lock()
_PRICING_CONFIG_CACHE: dict[str, Any] | None = None

_MEMORY_LOCK = threading.Lock()
_MEMORY_SPEND_BUCKETS: dict[tuple[str, int], float] = {}
_MEMORY_CALL_BUCKETS: dict[tuple[str, int], int] = {}

_FAILED_STATUSES: frozenset[str] = frozenset(
    {"failed", "error", "errored", "timeout", "dead_lettered", "enqueue_failed"}
)


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _redis_cost_buckets_enabled() -> bool:
    return os.getenv("TESTING", "").strip().lower() != "true"


def _as_datetime_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None

    if len(candidate) == 10 and candidate.count("-") == 2:
        candidate = f"{candidate}T00:00:00+00:00"
    elif candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""

    try:
        return str(value).strip()
    except Exception:
        return ""


def _normalize_provider(value: str) -> str:
    return value.strip().lower()


def _normalize_model(value: str) -> str:
    return value.strip().lower()


def _fallback_pricing_config() -> dict[str, Any]:
    return {
        "meta": {
            "schema_version": "fallback-v1",
            "retrieved_at": None,
            "effective_from": None,
            "expires_after_days": 14,
            "source_of_truth": "fallback_default",
        },
        "providers": {
            provider: {
                "models": {
                    model: dict(rates)
                    for model, rates in model_map.items()
                }
            }
            for provider, model_map in _FALLBACK_PROVIDER_MODEL_RATES_PER_1M.items()
        },
    }


def _candidate_pricing_paths() -> list[Path]:
    current_dir = Path(__file__).resolve()
    return [
        Path("pricing_config.json"),
        current_dir.parents[2] / "pricing_config.json",
        current_dir.parents[3] / "pricing_config.json",
    ]


def _safe_json_file(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    if not isinstance(parsed, dict):
        return None
    return parsed


def _load_pricing_config() -> dict[str, Any]:
    global _PRICING_CONFIG_CACHE

    if _PRICING_CONFIG_CACHE is not None:
        return _PRICING_CONFIG_CACHE

    with _PRICING_CACHE_LOCK:
        if _PRICING_CONFIG_CACHE is not None:
            return _PRICING_CONFIG_CACHE

        for path in _candidate_pricing_paths():
            if not path.exists() or not path.is_file():
                continue

            parsed = _safe_json_file(path)
            if not parsed:
                continue

            providers = parsed.get("providers")
            if not isinstance(providers, Mapping):
                continue

            _PRICING_CONFIG_CACHE = {
                "meta": parsed.get("meta") if isinstance(parsed.get("meta"), Mapping) else {},
                "providers": providers,
                "loaded_from_file": True,
                "source_path": str(path),
            }
            return _PRICING_CONFIG_CACHE

        fallback = _fallback_pricing_config()
        _PRICING_CONFIG_CACHE = {
            "meta": fallback["meta"],
            "providers": fallback["providers"],
            "loaded_from_file": False,
            "source_path": "fallback",
        }
        return _PRICING_CONFIG_CACHE


def _resolve_pricing_meta(config: Mapping[str, Any]) -> tuple[str, str | None, int | None]:
    meta = config.get("meta") if isinstance(config.get("meta"), Mapping) else {}
    version = _as_text(meta.get("schema_version")) or "fallback-v1"

    retrieved_at = _parse_datetime(meta.get("retrieved_at"))
    if retrieved_at is None:
        retrieved_at = _parse_datetime(meta.get("effective_from"))
    pricing_last_updated_at = _as_datetime_iso(retrieved_at)

    pricing_age_days: int | None = None
    if retrieved_at is not None:
        age = _utcnow() - retrieved_at
        pricing_age_days = max(0, int(age.total_seconds() // (24 * 60 * 60)))

    return version, pricing_last_updated_at, pricing_age_days


def _resolve_pricing_source(config: Mapping[str, Any], rate_card: Mapping[str, Any]) -> str:
    if bool(rate_card.get("fallback_used")):
        return "fallback_default"

    meta = config.get("meta") if isinstance(config.get("meta"), Mapping) else {}
    raw_source = _as_text(meta.get("source_of_truth") or meta.get("pricing_source")).lower()
    if raw_source in {"official", "official_provider", "provider", "provider_official"}:
        return "official_provider"

    return "cached_rate_card"


def _coerce_rate_map(raw: Mapping[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(raw, Mapping):
        return None

    rates = {
        "input": max(0.0, _as_float(raw.get("input"))),
        "output": max(0.0, _as_float(raw.get("output"))),
        "reasoning": max(0.0, _as_float(raw.get("reasoning"))),
        "cache_create": max(0.0, _as_float(raw.get("cache_create"))),
        "cache_read": max(0.0, _as_float(raw.get("cache_read"))),
    }
    return rates


def _find_model_rates(models: Mapping[str, Any], model: str) -> tuple[str | None, dict[str, float] | None]:
    normalized_model = _normalize_model(model)

    for candidate_name, raw_rates in models.items():
        if _normalize_model(str(candidate_name)) == normalized_model:
            rates = _coerce_rate_map(raw_rates if isinstance(raw_rates, Mapping) else None)
            if rates is not None:
                return str(candidate_name), rates

    for candidate_name, raw_rates in models.items():
        if normalized_model.startswith(_normalize_model(str(candidate_name))):
            rates = _coerce_rate_map(raw_rates if isinstance(raw_rates, Mapping) else None)
            if rates is not None:
                return str(candidate_name), rates

    return None, None


def _find_rate_card(config: Mapping[str, Any], *, provider: str, model: str) -> dict[str, Any]:
    providers = config.get("providers") if isinstance(config.get("providers"), Mapping) else {}
    normalized_provider = _normalize_provider(provider)
    loaded_from_file = bool(config.get("loaded_from_file"))

    for provider_name, provider_data in providers.items():
        if _normalize_provider(str(provider_name)) != normalized_provider:
            continue
        models = provider_data.get("models") if isinstance(provider_data, Mapping) else {}
        if not isinstance(models, Mapping):
            continue

        matched_model, rates = _find_model_rates(models, model)
        if rates is not None:
            return {
                "provider": str(provider_name),
                "model": matched_model,
                "rates": rates,
                "fallback_used": not loaded_from_file,
                "loaded_from_file": loaded_from_file,
            }

    fallback_provider = _FALLBACK_PROVIDER_MODEL_RATES_PER_1M.get(normalized_provider)
    if isinstance(fallback_provider, Mapping):
        matched_model, rates = _find_model_rates(fallback_provider, model)
        if rates is not None:
            return {
                "provider": normalized_provider,
                "model": matched_model,
                "rates": rates,
                "fallback_used": True,
                "loaded_from_file": loaded_from_file,
            }

    default_provider = "openai"
    default_model = "gpt-4o"
    default_rates = dict(_FALLBACK_PROVIDER_MODEL_RATES_PER_1M[default_provider][default_model])
    return {
        "provider": default_provider,
        "model": default_model,
        "rates": default_rates,
        "fallback_used": True,
        "loaded_from_file": loaded_from_file,
    }


def _calculate_cost_components(
    *,
    rates: Mapping[str, float],
    prompt_tokens: int,
    completion_tokens: int,
    reasoning_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
    status: str,
) -> dict[str, Any]:
    per_million = 1_000_000.0

    input_rate = max(0.0, _as_float(rates.get("input")))
    output_rate = max(0.0, _as_float(rates.get("output")))
    reasoning_rate = max(0.0, _as_float(rates.get("reasoning")))
    cache_create_rate = max(0.0, _as_float(rates.get("cache_create")))
    cache_read_rate = max(0.0, _as_float(rates.get("cache_read")))

    input_cost = (max(0, prompt_tokens) * input_rate) / per_million
    output_cost = (max(0, completion_tokens) * output_rate) / per_million
    reasoning_cost = (max(0, reasoning_tokens) * reasoning_rate) / per_million
    cache_create_cost = (max(0, cache_creation_tokens) * cache_create_rate) / per_million
    cache_read_cost = (max(0, cache_read_tokens) * cache_read_rate) / per_million
    cache_savings = (max(0, cache_read_tokens) * max(0.0, input_rate - cache_read_rate)) / per_million

    total_cost = max(0.0, input_cost + output_cost + reasoning_cost + cache_create_cost + cache_read_cost - cache_savings)
    wasted_cost = total_cost if _as_text(status).lower() in _FAILED_STATUSES else 0.0

    return {
        "input_cost_usd": round(input_cost, 8),
        "output_cost_usd": round(output_cost, 8),
        "reasoning_cost_usd": round(reasoning_cost, 8),
        "cache_create_cost_usd": round(cache_create_cost, 8),
        "cache_read_cost_usd": round(cache_read_cost, 8),
        "cache_savings_usd": round(cache_savings, 8),
        "total_cost_usd": round(total_cost, 8),
        "wasted_cost_usd": round(wasted_cost, 8),
    }


def _calculate_total_for_comparison(
    *,
    rates: Mapping[str, float],
    prompt_tokens: int,
    completion_tokens: int,
    reasoning_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
) -> float:
    components = _calculate_cost_components(
        rates=rates,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
        status="completed",
    )
    return _as_float(components.get("total_cost_usd"))


def _component_sum_usd(components: Mapping[str, Any]) -> float:
    total = (
        _as_float(components.get("input_cost_usd"))
        + _as_float(components.get("output_cost_usd"))
        + _as_float(components.get("reasoning_cost_usd"))
        + _as_float(components.get("cache_create_cost_usd"))
        + _as_float(components.get("cache_read_cost_usd"))
        - _as_float(components.get("cache_savings_usd"))
    )
    return round(max(0.0, total), 8)


def _component_integrity_ok(components: Mapping[str, Any]) -> bool:
    expected_total = _component_sum_usd(components)
    actual_total = round(max(0.0, _as_float(components.get("total_cost_usd"))), 8)
    return abs(expected_total - actual_total) <= 0.000001


def _build_provider_comparison(
    *,
    config: Mapping[str, Any],
    actual_provider: str,
    actual_model: str,
    actual_total_cost_usd: float,
    prompt_tokens: int,
    completion_tokens: int,
    reasoning_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
) -> dict[str, Any]:
    providers = config.get("providers") if isinstance(config.get("providers"), Mapping) else {}
    comparison_items: list[dict[str, Any]] = []

    for provider_name, provider_data in providers.items():
        models = provider_data.get("models") if isinstance(provider_data, Mapping) else {}
        if not isinstance(models, Mapping) or not models:
            continue

        if _normalize_provider(str(provider_name)) == _normalize_provider(actual_provider):
            chosen_model_name, rates = _find_model_rates(models, actual_model)
            if rates is None:
                first_model_name = sorted(str(name) for name in models.keys())[0]
                chosen_model_name = first_model_name
                rates = _coerce_rate_map(models.get(first_model_name) if isinstance(models.get(first_model_name), Mapping) else None)
        else:
            first_model_name = sorted(str(name) for name in models.keys())[0]
            chosen_model_name = first_model_name
            rates = _coerce_rate_map(models.get(first_model_name) if isinstance(models.get(first_model_name), Mapping) else None)

        if rates is None:
            continue

        estimated_total = _calculate_total_for_comparison(
            rates=rates,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
        )

        comparison_items.append(
            {
                "provider": str(provider_name),
                "model": chosen_model_name,
                "estimated_total_cost_usd": round(estimated_total, 8),
                "delta_vs_actual_usd": round(estimated_total - actual_total_cost_usd, 8),
            }
        )

    if not comparison_items:
        return {
            "comparison_type": "mock",
            "items": [],
            "best_provider": None,
            "best_model": None,
            "best_estimated_total_cost_usd": None,
        }

    comparison_items.sort(key=lambda item: _as_float(item.get("estimated_total_cost_usd")))
    best = comparison_items[0]
    return {
        "comparison_type": "mock",
        "items": comparison_items,
        "best_provider": best.get("provider"),
        "best_model": best.get("model"),
        "best_estimated_total_cost_usd": best.get("estimated_total_cost_usd"),
    }


def build_per_call_cost_breakdown(payload: Mapping[str, Any]) -> dict[str, Any]:
    provider = _as_text(payload.get("provider")) or "unknown"
    model = _as_text(payload.get("model")) or "unknown"
    status = _as_text(payload.get("status")) or "unknown"

    prompt_tokens = _as_int(payload.get("prompt_tokens"))
    completion_tokens = _as_int(payload.get("completion_tokens"))
    reasoning_tokens = _as_int(payload.get("reasoning_tokens"))
    cache_creation_tokens = _as_int(payload.get("cache_creation_tokens"))
    cache_read_tokens = _as_int(payload.get("cache_read_tokens"))
    provided_total_raw = payload.get("total_cost_usd")
    if provided_total_raw is None:
        provided_total_raw = payload.get("cost_usd")
    provided_total_cost_usd = _as_float(provided_total_raw) if provided_total_raw is not None else None

    config = _load_pricing_config()
    pricing_version, pricing_last_updated_at, pricing_age_days = _resolve_pricing_meta(config)
    rate_card = _find_rate_card(config, provider=provider, model=model)
    rates = rate_card["rates"]

    components = _calculate_cost_components(
        rates=rates,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
        status=status,
    )

    if _normalize_provider(provider) == "unknown":
        confidence = "degraded"
        confidence_reason = "provider_unknown"
    elif prompt_tokens + completion_tokens + reasoning_tokens + cache_creation_tokens + cache_read_tokens <= 0:
        confidence = "degraded"
        confidence_reason = "missing_tokens"
    elif bool(rate_card.get("fallback_used")):
        confidence = "degraded"
        confidence_reason = "fallback_rate_card"
    elif pricing_age_days is None:
        confidence = "degraded"
        confidence_reason = "pricing_timestamp_missing"
    elif pricing_age_days > PRICING_STALE_THRESHOLD_DAYS:
        confidence = "stale"
        confidence_reason = "pricing_catalog_stale"
    else:
        confidence = "high"
        confidence_reason = "pricing_config_fresh"

    component_sum_usd = _component_sum_usd(components)
    component_integrity_ok = _component_integrity_ok(components)
    if not component_integrity_ok:
        confidence = "degraded"
        confidence_reason = "cost_component_mismatch"

    provided_total_matches_calculated = True
    if provided_total_cost_usd is not None:
        provided_total_matches_calculated = abs(
            round(provided_total_cost_usd, 8) - round(_as_float(components.get("total_cost_usd")), 8)
        ) <= 0.000001
        if not provided_total_matches_calculated:
            confidence = "degraded"
            confidence_reason = "provided_cost_mismatch"

    comparison = _build_provider_comparison(
        config=config,
        actual_provider=provider,
        actual_model=model,
        actual_total_cost_usd=_as_float(components.get("total_cost_usd")),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
    )
    pricing_source = _resolve_pricing_source(config, rate_card)

    return {
        "provider": provider,
        "model": model,
        "status": status,
        "currency": BASE_CURRENCY,
        "token_unit": TOKEN_UNIT,
        "token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "cache_read_tokens": cache_read_tokens,
        },
        "rate_card_per_1m_tokens": {
            "input": round(_as_float(rates.get("input")), 8),
            "output": round(_as_float(rates.get("output")), 8),
            "reasoning": round(_as_float(rates.get("reasoning")), 8),
            "cache_create": round(_as_float(rates.get("cache_create")), 8),
            "cache_read": round(_as_float(rates.get("cache_read")), 8),
        },
        **components,
        "component_sum_usd": component_sum_usd,
        "component_integrity_ok": component_integrity_ok,
        "provided_total_cost_usd": None if provided_total_cost_usd is None else round(provided_total_cost_usd, 8),
        "provided_total_matches_calculated": provided_total_matches_calculated,
        "pricing_version": pricing_version,
        "pricing_source": pricing_source,
        "pricing_last_updated_at": pricing_last_updated_at,
        "pricing_age_days": pricing_age_days,
        "cost_confidence": confidence,
        "confidence_reason": confidence_reason,
        "pricing_source_detail": {
            "provider": rate_card.get("provider"),
            "model": rate_card.get("model"),
            "fallback_used": bool(rate_card.get("fallback_used")),
            "loaded_from_file": bool(rate_card.get("loaded_from_file")),
            "source_path": config.get("source_path"),
        },
        "provider_comparison": comparison,
    }


def _bucket_start(timestamp_seconds: float) -> int:
    return int(timestamp_seconds // COST_BUCKET_SECONDS) * COST_BUCKET_SECONDS


def _bucket_starts(current_bucket_start: int) -> list[int]:
    return [current_bucket_start - (idx * COST_BUCKET_SECONDS) for idx in range(COST_BASELINE_BUCKETS)]


def _redis_spend_key(tenant_id: str, bucket_start: int) -> str:
    return f"zroky:cost:v1:spend:{tenant_id}:{bucket_start}"


def _redis_calls_key(tenant_id: str, bucket_start: int) -> str:
    return f"zroky:cost:v1:calls:{tenant_id}:{bucket_start}"


def _parse_payload_timestamp(payload: Mapping[str, Any]) -> float:
    created_at = payload.get("created_at")
    if isinstance(created_at, (int, float)):
        return float(created_at)

    if isinstance(created_at, str):
        candidate = created_at.strip()
        if not candidate:
            return time.time()

        try:
            return float(candidate)
        except ValueError:
            try:
                dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except ValueError:
                return time.time()

    return time.time()


def _aggregate_with_memory(*, tenant_id: str, bucket_start: int, event_cost_usd: float) -> dict[str, Any]:
    starts = _bucket_starts(bucket_start)
    cutoff = starts[-1]

    with _MEMORY_LOCK:
        stale_keys = [key for key in _MEMORY_SPEND_BUCKETS if key[0] == tenant_id and key[1] < cutoff]
        for key in stale_keys:
            _MEMORY_SPEND_BUCKETS.pop(key, None)
            _MEMORY_CALL_BUCKETS.pop(key, None)

        current_key = (tenant_id, bucket_start)
        _MEMORY_SPEND_BUCKETS[current_key] = _MEMORY_SPEND_BUCKETS.get(current_key, 0.0) + event_cost_usd
        _MEMORY_CALL_BUCKETS[current_key] = _MEMORY_CALL_BUCKETS.get(current_key, 0) + 1

        spends = [float(_MEMORY_SPEND_BUCKETS.get((tenant_id, bucket), 0.0)) for bucket in starts]
        calls = [int(_MEMORY_CALL_BUCKETS.get((tenant_id, bucket), 0)) for bucket in starts]

    current_spend = spends[0]
    historical_spends = spends[1:]
    baseline_spend = sum(historical_spends) / max(1, len(historical_spends))
    history_calls = sum(calls)
    non_zero_buckets = sum(1 for value in calls if value > 0)
    history_days = (non_zero_buckets * COST_BUCKET_SECONDS) / (24 * 60 * 60)

    return {
        "event_cost_usd": event_cost_usd,
        "current_15m_spend_usd": round(current_spend, 6),
        "baseline_15m_spend_usd": round(baseline_spend, 6),
        "history_days": round(history_days, 4),
        "history_calls": history_calls,
        "baseline_window_days": COST_BASELINE_WINDOW_DAYS,
        "spend_bucket_minutes": COST_BUCKET_SECONDS // 60,
        "model_spend_coefficient": 1.0,
    }


def _aggregate_with_redis(*, tenant_id: str, bucket_start: int, event_cost_usd: float) -> dict[str, Any]:
    starts = _bucket_starts(bucket_start)
    ttl_seconds = (COST_BASELINE_BUCKETS * COST_BUCKET_SECONDS) + COST_BUCKET_SECONDS

    client = get_redis_client()

    spend_key = _redis_spend_key(tenant_id, bucket_start)
    calls_key = _redis_calls_key(tenant_id, bucket_start)
    client.incrbyfloat(spend_key, event_cost_usd)
    client.expire(spend_key, ttl_seconds)
    client.incr(calls_key)
    client.expire(calls_key, ttl_seconds)

    spend_values = client.mget([_redis_spend_key(tenant_id, bucket) for bucket in starts])
    call_values = client.mget([_redis_calls_key(tenant_id, bucket) for bucket in starts])

    spends = [round(_as_float(value), 8) for value in spend_values]
    calls = [_as_int(value) for value in call_values]

    current_spend = spends[0]
    historical_spends = spends[1:]
    baseline_spend = sum(historical_spends) / max(1, len(historical_spends))
    history_calls = sum(calls)
    non_zero_buckets = sum(1 for value in calls if value > 0)
    history_days = (non_zero_buckets * COST_BUCKET_SECONDS) / (24 * 60 * 60)

    return {
        "event_cost_usd": event_cost_usd,
        "current_15m_spend_usd": round(current_spend, 6),
        "baseline_15m_spend_usd": round(baseline_spend, 6),
        "history_days": round(history_days, 4),
        "history_calls": history_calls,
        "baseline_window_days": COST_BASELINE_WINDOW_DAYS,
        "spend_bucket_minutes": COST_BUCKET_SECONDS // 60,
        "model_spend_coefficient": 1.0,
    }


def enrich_payload_with_cost_buckets(*, tenant_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    enriched = dict(payload)

    per_call_breakdown = build_per_call_cost_breakdown(enriched)
    event_cost_usd = max(0.0, _as_float(per_call_breakdown.get("total_cost_usd")))

    event_ts = _parse_payload_timestamp(enriched)
    bucket_start = _bucket_start(event_ts)

    if event_cost_usd > 0:
        try:
            if _redis_cost_buckets_enabled():
                bucket_cost = _aggregate_with_redis(
                    tenant_id=tenant_id,
                    bucket_start=bucket_start,
                    event_cost_usd=event_cost_usd,
                )
            else:
                bucket_cost = _aggregate_with_memory(
                    tenant_id=tenant_id,
                    bucket_start=bucket_start,
                    event_cost_usd=event_cost_usd,
                )
        except redis.RedisError:
            bucket_cost = _aggregate_with_memory(
                tenant_id=tenant_id,
                bucket_start=bucket_start,
                event_cost_usd=event_cost_usd,
            )
    else:
        bucket_cost = {
            "event_cost_usd": event_cost_usd,
            "current_15m_spend_usd": 0.0,
            "baseline_15m_spend_usd": 0.0,
            "history_days": 0.0,
            "history_calls": 0,
            "baseline_window_days": COST_BASELINE_WINDOW_DAYS,
            "spend_bucket_minutes": COST_BUCKET_SECONDS // 60,
            "model_spend_coefficient": 1.0,
        }

    cost = dict(bucket_cost)
    cost["per_call_breakdown"] = per_call_breakdown
    cost["pricing_version"] = per_call_breakdown.get("pricing_version")
    cost["pricing_source"] = per_call_breakdown.get("pricing_source")
    cost["pricing_last_updated_at"] = per_call_breakdown.get("pricing_last_updated_at")
    cost["pricing_age_days"] = per_call_breakdown.get("pricing_age_days")
    cost["cost_confidence"] = per_call_breakdown.get("cost_confidence")
    cost["confidence_reason"] = per_call_breakdown.get("confidence_reason")
    cost["currency"] = BASE_CURRENCY
    cost["token_unit"] = TOKEN_UNIT
    cost["provider_comparison"] = per_call_breakdown.get("provider_comparison")

    enriched["cost"] = cost
    enriched["cost_usd"] = _as_float(per_call_breakdown.get("total_cost_usd"))
    enriched["total_cost_usd"] = _as_float(per_call_breakdown.get("total_cost_usd"))
    enriched["reasoning_cost_usd"] = _as_float(per_call_breakdown.get("reasoning_cost_usd"))
    enriched["cache_savings_usd"] = _as_float(per_call_breakdown.get("cache_savings_usd"))
    enriched["pricing_version"] = _as_text(per_call_breakdown.get("pricing_version"))
    enriched["pricing_source"] = _as_text(per_call_breakdown.get("pricing_source"))
    enriched["pricing_last_updated_at"] = _as_text(per_call_breakdown.get("pricing_last_updated_at"))
    enriched["pricing_age_days"] = _as_int(per_call_breakdown.get("pricing_age_days"))
    enriched["cost_confidence"] = _as_text(per_call_breakdown.get("cost_confidence"))
    enriched["confidence_reason"] = _as_text(per_call_breakdown.get("confidence_reason"))
    enriched["cost_currency"] = BASE_CURRENCY
    enriched["token_unit"] = TOKEN_UNIT
    enriched["provider_comparison"] = per_call_breakdown.get("provider_comparison")
    enriched["current_15m_spend_usd"] = cost["current_15m_spend_usd"]
    enriched["baseline_15m_spend_usd"] = cost["baseline_15m_spend_usd"]
    enriched["history_days"] = cost["history_days"]
    enriched["history_calls"] = cost["history_calls"]
    enriched["baseline_window_days"] = cost["baseline_window_days"]
    enriched["spend_bucket_minutes"] = cost["spend_bucket_minutes"]
    enriched["model_spend_coefficient"] = cost["model_spend_coefficient"]

    return enriched
