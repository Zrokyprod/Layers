#!/usr/bin/env python3
"""
Refresh pricing_config.json from provider snapshot URLs.

Expected snapshot payload per provider URL:
{
  "models": {
    "model-name": {
      "input": 5.0,
      "output": 15.0,
      "reasoning": 0.0,
      "cache_create": 0.0,
      "cache_read": 0.0
    }
  },
  "source_url": "https://provider.example/pricing"
}

Environment variables:
- OPENAI_PRICING_SNAPSHOT_URL
- ANTHROPIC_PRICING_SNAPSHOT_URL
- GOOGLE_PRICING_SNAPSHOT_URL
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict


REQUIRED_KEYS = ["input", "output", "reasoning", "cache_create", "cache_read"]


def _utc_now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _fetch_json(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "zroky-pricing-refresh/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError(f"Snapshot at {url} must be a JSON object")
    return payload


def _validate_model_rate(model_name: str, rate: Dict[str, Any]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    for key in REQUIRED_KEYS:
        if key not in rate:
            raise ValueError(f"Model '{model_name}' missing required key '{key}'")
        value = rate[key]
        if not isinstance(value, (int, float)):
            raise ValueError(f"Model '{model_name}' key '{key}' must be numeric")
        if value < 0:
            raise ValueError(f"Model '{model_name}' key '{key}' must be >= 0")
        normalized[key] = float(value)
    return normalized


def _update_provider(
    config: Dict[str, Any], provider: str, snapshot: Dict[str, Any]
) -> bool:
    models = snapshot.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError(f"Provider '{provider}' snapshot requires non-empty 'models' object")

    providers = config.setdefault("providers", {})
    provider_obj = providers.setdefault(provider, {})
    provider_models = provider_obj.setdefault("models", {})

    changed = False
    for model_name, raw_rate in models.items():
        if not isinstance(raw_rate, dict):
            raise ValueError(f"Provider '{provider}', model '{model_name}' must be object")

        rate = _validate_model_rate(model_name, raw_rate)
        new_record = {
            "billing_unit": "per_1m_tokens",
            **rate,
        }

        if provider_models.get(model_name) != new_record:
            provider_models[model_name] = new_record
            changed = True

    source_url = snapshot.get("source_url")
    if isinstance(source_url, str) and source_url.strip():
        pricing_source = provider_obj.setdefault("pricing_source", {})
        if pricing_source.get("url") != source_url:
            pricing_source["url"] = source_url
            changed = True

    return changed


def refresh(config_path: str) -> int:
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    env_map = {
        "openai": os.environ.get("OPENAI_PRICING_SNAPSHOT_URL", "").strip(),
        "anthropic": os.environ.get("ANTHROPIC_PRICING_SNAPSHOT_URL", "").strip(),
        "google": os.environ.get("GOOGLE_PRICING_SNAPSHOT_URL", "").strip(),
    }

    configured_sources = {k: v for k, v in env_map.items() if v}
    if not configured_sources:
        print("No provider snapshot URLs configured. Skipping refresh.")
        return 0

    any_changes = False
    for provider, url in configured_sources.items():
        try:
            snapshot = _fetch_json(url)
            changed = _update_provider(config, provider, snapshot)
            any_changes = any_changes or changed
            print(f"{provider}: snapshot fetched, changed={changed}")
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"{provider}: fetch failed: {exc}")
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"{provider}: invalid snapshot: {exc}")

    meta = config.setdefault("meta", {})
    if any_changes:
        meta["retrieved_at"] = _utc_now_iso()
        meta["last_auto_update"] = _utc_now_iso()
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        print("pricing_config updated.")
    else:
        print("No pricing changes detected.")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh pricing_config.json from snapshot URLs.")
    parser.add_argument(
        "--config",
        default="pricing_config.json",
        help="Path to pricing config file (default: pricing_config.json)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not os.path.exists(args.config):
        print(f"Config file not found: {args.config}")
        return 1
    return refresh(args.config)


if __name__ == "__main__":
    sys.exit(main())
