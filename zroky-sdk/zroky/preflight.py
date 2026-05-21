# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""
Pre-execution validation (preflight) API and internals.

Public API:
    estimate_tokens, check_token_overflow, check_rate_limit_risk,
    model_context_limit_resolution, validate, print_validation

Internal:
    _run_preflight_validation, _is_preflight_sampled_in,
    _recent_calls_for_preflight, _provider_api_key_hint

The deque _recent_preflight_calls is re-exported from zroky.__init__ so
the test fixture (which does zroky._recent_preflight_calls.clear()) works
against the same underlying object defined here.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import deque
from typing import Any

from zroky._internal import validation as _validation
from zroky._internal.config import SDKConfig

# ---------------------------------------------------------------------------
# State — re-exported from zroky.__init__ for test-fixture compat
# ---------------------------------------------------------------------------

_PREFLIGHT_RECENT_CALLS_WINDOW_SECONDS = 60.0

_recent_preflight_calls: deque[float] = deque()
_preflight_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public validation API
# ---------------------------------------------------------------------------

def estimate_tokens(payload: dict[str, Any]) -> int:
    """Estimate token usage using a lightweight heuristic (~4 chars/token)."""
    return _validation.estimate_tokens(payload)


def check_token_overflow(
    payload: dict[str, Any],
    *,
    estimated_tokens: int | None = None,
) -> dict[str, Any] | None:
    """Check whether payload is near model context limit."""
    return _validation.check_token_overflow(payload, estimated_tokens=estimated_tokens)


def check_rate_limit_risk(
    payload: dict[str, Any],
    *,
    estimated_tokens: int | None = None,
) -> dict[str, Any] | None:
    """Check burst/heavy-request risk before executing provider call."""
    return _validation.check_rate_limit_risk(payload, estimated_tokens=estimated_tokens)


def model_context_limit_resolution(model: str | None) -> dict[str, Any]:
    """Resolve context limit with source/confidence metadata for a model."""
    return _validation.model_context_limit_resolution(model)


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Analyze an upcoming LLM call payload and return structured warnings."""
    return _validation.validate(payload)


def print_validation(result: dict[str, Any]) -> None:
    """Print validation result with developer-friendly warnings."""
    _validation.print_validation(result)


# ---------------------------------------------------------------------------
# Internal preflight helpers
# ---------------------------------------------------------------------------

def _recent_calls_for_preflight(now: float | None = None) -> int:
    current_time = now if now is not None else time.monotonic()
    cutoff = current_time - _PREFLIGHT_RECENT_CALLS_WINDOW_SECONDS
    with _preflight_lock:
        _recent_preflight_calls.append(current_time)
        while _recent_preflight_calls and _recent_preflight_calls[0] < cutoff:
            _recent_preflight_calls.popleft()
        return len(_recent_preflight_calls)


def _provider_api_key_hint(*, provider: str, kwargs: dict[str, Any]) -> str | None:
    explicit_key = kwargs.get("api_key")
    if isinstance(explicit_key, str) and explicit_key.strip():
        return explicit_key
    if kwargs.get("_client") is not None:
        return "client-configured"
    provider_key_env_map: dict[str, tuple[str, ...]] = {
        "openai": ("OPENAI_API_KEY",),
        "azure_openai": ("AZURE_OPENAI_API_KEY", "OPENAI_API_KEY"),
        "anthropic": ("ANTHROPIC_API_KEY",),
    }
    for env_name in provider_key_env_map.get(provider, ()):
        env_value = os.environ.get(env_name)
        if isinstance(env_value, str) and env_value.strip():
            return "env-configured"
    return None


def _is_preflight_sampled_in(*, sample_rate: float, sample_key: str) -> bool:
    if sample_rate <= 0.0:
        return False
    if sample_rate >= 1.0:
        return True
    digest = hashlib.sha256(sample_key.encode("utf-8")).digest()
    bucket_value = int.from_bytes(digest[:8], byteorder="big", signed=False)
    normalized_bucket = bucket_value / float(1 << 64)
    return normalized_bucket < sample_rate


def _run_preflight_validation(
    *,
    cfg: SDKConfig,
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    sample_key: str,
    kwargs: dict[str, Any],
) -> None:
    from zroky._errors import ZrokyPreflightError  # local to avoid circular at module load

    blocking_types = {
        warning_type.strip().upper()
        for warning_type in cfg.preflight_blocking_warning_types
        if warning_type.strip()
    }
    if not cfg.validate_preflight and not blocking_types:
        return
    if cfg.validate_preflight and not _is_preflight_sampled_in(
        sample_rate=cfg.validate_preflight_sample_rate,
        sample_key=sample_key,
    ) and not blocking_types:
        return

    try:
        payload: dict[str, Any] = {
            "provider": provider,
            "model": model,
            "messages": messages,
            "tools": tools,
            "meta": {"recent_calls": _recent_calls_for_preflight()},
        }
        api_key_hint = _provider_api_key_hint(provider=provider, kwargs=kwargs)
        if api_key_hint:
            payload["api_key"] = api_key_hint
        validation_result = _validation.validate(payload)
        warnings = (
            validation_result.get("warnings")
            if isinstance(validation_result, dict)
            else None
        )
        if isinstance(warnings, list) and warnings:
            _validation.print_validation(validation_result)
            blocking_warnings = [
                warning
                for warning in warnings
                if str(warning.get("type", "")).strip().upper() in blocking_types
            ]
            if blocking_warnings:
                raise ZrokyPreflightError(blocking_warnings)
    except ZrokyPreflightError:
        raise
    except Exception:
        if cfg.verbose:
            print("[ZROKY] Preflight validation unavailable; continuing call.")
