"""
Cost calculation engine.
Applies pricing_config.json rates to captured token usage.

Formula per blueprint:
  total_cost_usd = input_cost + output_cost + reasoning_cost
                   + cache_create_cost + cache_read_cost - cache_savings

  wasted_cost_usd = total_cost_usd when status=failed or no usable output
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Fallback rates (USD per 1M tokens) used when pricing_config.json not found.
# These are intentionally conservative estimates. Real values load from config.
_FALLBACK_RATES: dict[str, dict[str, float]] = {
    "gpt-4o": {
        "input": 2.50,
        "output": 10.00,
        "reasoning": 0.0,
        "cache_create": 0.0,
        "cache_read": 0.0,
    },
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.60,
        "reasoning": 0.0,
        "cache_create": 0.0,
        "cache_read": 0.0,
    },
    "o3": {
        "input": 10.00,
        "output": 40.00,
        "reasoning": 60.00,
        "cache_create": 0.0,
        "cache_read": 0.0,
    },
    "claude-3-5-sonnet-20241022": {
        "input": 3.00,
        "output": 15.00,
        "reasoning": 0.0,
        "cache_create": 3.75,
        "cache_read": 0.30,
    },
}

_config_cache: dict[str, Any] | None = None


def _load_pricing_config() -> dict[str, Any]:
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    # Try to find pricing_config.json relative to CWD or package dir
    candidates = [
        Path("pricing_config.json"),
        Path(__file__).parent.parent.parent / "pricing_config.json",
    ]
    for path in candidates:
        if path.exists():
            with path.open() as f:
                _config_cache = json.load(f)
                return _config_cache

    _config_cache = {"models": _FALLBACK_RATES}
    return _config_cache


def _get_rates(model: str) -> dict[str, float]:
    config = _load_pricing_config()
    models: dict[str, Any] = config.get("models", {})

    # Exact match first
    if model in models:
        return models[model]

    # Prefix match (e.g., "gpt-4o-2024-11" -> "gpt-4o")
    for key, rates in models.items():
        if model.startswith(key):
            return rates

    return _FALLBACK_RATES.get(model, {
        "input": 0.0, "output": 0.0, "reasoning": 0.0,
        "cache_create": 0.0, "cache_read": 0.0,
    })


def calculate_cost(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    reasoning_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    status: str = "success",
) -> dict[str, float]:
    """
    Return a dict with cost breakdown in USD.

    Keys:
      input_cost_usd, output_cost_usd, reasoning_cost_usd,
      cache_create_cost_usd, cache_read_cost_usd,
      cache_savings_usd, total_cost_usd, wasted_cost_usd
    """
    rates = _get_rates(model)
    per_million = 1_000_000.0

    input_cost = prompt_tokens * rates.get("input", 0.0) / per_million
    output_cost = completion_tokens * rates.get("output", 0.0) / per_million
    reasoning_cost = reasoning_tokens * rates.get("reasoning", 0.0) / per_million
    cache_create_cost = cache_creation_tokens * rates.get("cache_create", 0.0) / per_million
    cache_read_cost = cache_read_tokens * rates.get("cache_read", 0.0) / per_million

    # Cache savings = what cache_read tokens would have cost at full input rate
    full_rate = rates.get("input", 0.0)
    discounted_rate = rates.get("cache_read", 0.0)
    cache_savings = cache_read_tokens * max(0.0, full_rate - discounted_rate) / per_million

    total_cost = (
        input_cost + output_cost + reasoning_cost
        + cache_create_cost + cache_read_cost - cache_savings
    )
    total_cost = max(0.0, total_cost)

    wasted_cost = total_cost if status == "failed" else 0.0

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
