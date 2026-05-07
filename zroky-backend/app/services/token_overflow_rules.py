from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

MODEL_CONTEXT_LIMITS: dict[str, int] = {
    # ── OpenAI ──────────────────────────────────────────────────────────
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-4-turbo": 128000,
    "gpt-4-turbo-preview": 128000,
    "gpt-4.1": 1047576,
    "gpt-4.1-mini": 1047576,
    "gpt-4.1-nano": 1047576,
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-16k": 16385,
    "o3": 200000,
    "o3-mini": 200000,
    "o4-mini": 200000,
    # ── DeepSeek (direct API names) ──────────────────────────────────────
    "deepseek-chat": 65536,
    "deepseek-coder": 65536,
    "deepseek-reasoner": 65536,
    # ── Anthropic Claude (direct API names) ─────────────────────────────
    "claude-3-5-sonnet-20241022": 200000,
    "claude-3-5-haiku-20241022": 200000,
    "claude-3-opus-20240229": 200000,
    "claude-3-sonnet-20240229": 200000,
    "claude-3-haiku-20240307": 200000,
    "claude-2.1": 200000,
    "claude-2": 100000,
    "claude-instant-1.2": 100000,
    # ── Google Gemini (direct API names) ────────────────────────────────
    "gemini-2.0-flash": 1048576,
    "gemini-2.0-flash-lite": 1048576,
    "gemini-2.5-pro": 1048576,
    "gemini-1.5-pro": 1048576,
    "gemini-1.5-flash": 1048576,
    "gemini-1.5-flash-8b": 1048576,
    "gemini-1.0-pro": 32760,
    "gemini-pro": 32760,
    # ── Mistral (direct API names) ───────────────────────────────────────
    "mistral-large": 128000,
    "mistral-large-latest": 128000,
    "mistral-medium": 32768,
    "mistral-small": 32768,
    "mistral-7b-instruct": 32768,
    "mixtral-8x7b-instruct": 32768,
    "mixtral-8x22b-instruct": 65536,
    # ── Meta Llama (direct API names) ───────────────────────────────────
    "llama-3-8b-instruct": 8192,
    "llama-3-70b-instruct": 8192,
    "llama-3.1-8b-instruct": 131072,
    "llama-3.1-70b-instruct": 131072,
    "llama-3.1-405b-instruct": 131072,
    "llama-3.2-11b-vision-instruct": 131072,
    "llama-3.2-90b-vision-instruct": 131072,
    "llama-3.3-70b-instruct": 131072,
    # ── Cohere ───────────────────────────────────────────────────────────
    "command-r-plus": 128000,
    "command-r": 128000,
    "command": 4096,
}
MODEL_CONTEXT_LIMIT_PREFIXES: dict[str, int] = {
    # OpenAI — more specific first
    "gpt-4.1-": 1047576,
    "gpt-4o-": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4-32k": 32768,
    "gpt-3.5-turbo-": 16385,
    "o3-": 200000,
    "o4-": 200000,
    # OpenRouter namespaced prefixes (provider/model format)
    "deepseek/": 65536,
    "anthropic/claude-3": 200000,
    "anthropic/claude-2": 200000,
    "anthropic/claude-instant": 100000,
    "google/gemini-2.5": 1048576,
    "google/gemini-2.0": 1048576,
    "google/gemini-1.5": 1048576,
    "google/gemini-pro": 32760,
    "google/gemini-1.0": 32760,
    "meta-llama/llama-3.3-": 131072,
    "meta-llama/llama-3.2-": 131072,
    "meta-llama/llama-3.1-": 131072,
    "meta-llama/llama-3-": 8192,
    "mistralai/mixtral-8x22b": 65536,
    "mistralai/mixtral-8x7b": 32768,
    "mistralai/mistral-large": 128000,
    "mistralai/mistral-medium": 32768,
    "mistralai/mistral-small": 32768,
    "mistralai/mistral-7b": 32768,
    "mistralai/mistral-": 32768,
    "cohere/command-r": 128000,
    "cohere/command": 4096,
}
MODEL_CONTEXT_LIMIT_CATALOG_VERSION = "model_context_limits_2026_05_06"
MODEL_CONTEXT_LIMIT_CATALOG_UPDATED_AT = "2026-05-06"
MODEL_CONTEXT_LIMIT_CATALOG_STALE_AFTER_DAYS = 180
TOKEN_RULES_VERSION = "token_rules_v2"
TOKEN_OVERFLOW_ERROR_PATTERNS = (
    "maximum context length",
    "max context length",
    "context length exceeded",
    "context length",
    "token limit exceeded",
    "token limit",
    "maximum tokens",
    "max tokens",
    "too many tokens",
    "input is too long",
    "prompt is too long",
    "request too large",
    "context window",
)

_warned_override_issues: set[str] = set()


@dataclass(frozen=True)
class ModelContextLimitResolution:
    model: str | None
    normalized_model: str
    limit: int | None
    source: str
    source_detail: str | None
    confidence: float
    catalog_version: str
    catalog_updated_at: str
    catalog_stale: bool
    catalog_stale_after_days: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "normalized_model": self.normalized_model,
            "limit": self.limit,
            "source": self.source,
            "source_detail": self.source_detail,
            "confidence": self.confidence,
            "catalog_version": self.catalog_version,
            "catalog_updated_at": self.catalog_updated_at,
            "catalog_stale": self.catalog_stale,
            "catalog_stale_after_days": self.catalog_stale_after_days,
        }


def resolve_model_context_limit(model: str | None) -> ModelContextLimitResolution:
    raw_model = _as_text(model).strip()
    normalized = raw_model.lower()
    if not normalized:
        return _build_model_context_resolution(
            model=None,
            normalized_model="",
            limit=None,
            source="unknown",
            source_detail="missing_model",
            confidence=0.0,
        )

    override = model_context_limit_overrides().get(normalized)
    if override is not None:
        return _build_model_context_resolution(
            model=raw_model,
            normalized_model=normalized,
            limit=override,
            source="env_override",
            source_detail="ZROKY_MODEL_CONTEXT_LIMITS",
            confidence=1.0,
        )

    exact = MODEL_CONTEXT_LIMITS.get(normalized)
    if exact is not None:
        return _build_model_context_resolution(
            model=raw_model,
            normalized_model=normalized,
            limit=exact,
            source="catalog_exact",
            source_detail=normalized,
            confidence=0.95,
        )

    for prefix, limit in MODEL_CONTEXT_LIMIT_PREFIXES.items():
        if normalized.startswith(prefix):
            return _build_model_context_resolution(
                model=raw_model,
                normalized_model=normalized,
                limit=limit,
                source="catalog_prefix",
                source_detail=prefix,
                confidence=0.86,
            )

    return _build_model_context_resolution(
        model=raw_model,
        normalized_model=normalized,
        limit=None,
        source="unknown",
        source_detail="not_in_catalog",
        confidence=0.0,
    )


def known_model_context_limit(model: str | None) -> int | None:
    return resolve_model_context_limit(model).limit


def model_context_limit_catalog_metadata() -> dict[str, Any]:
    return {
        "catalog_version": MODEL_CONTEXT_LIMIT_CATALOG_VERSION,
        "catalog_updated_at": MODEL_CONTEXT_LIMIT_CATALOG_UPDATED_AT,
        "catalog_stale": _catalog_stale(),
        "catalog_stale_after_days": MODEL_CONTEXT_LIMIT_CATALOG_STALE_AFTER_DAYS,
    }


def token_rules_version() -> str:
    return TOKEN_RULES_VERSION


def model_context_limit_overrides(raw_value: str | None = None) -> dict[str, int]:
    raw_text = os.environ.get("ZROKY_MODEL_CONTEXT_LIMITS", "") if raw_value is None else raw_value
    raw_text = raw_text.strip()
    if not raw_text:
        return {}

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = None
    else:
        if isinstance(parsed, Mapping):
            return _coerce_model_limit_map(parsed)

        _warn_invalid_override(
            reason="expected a JSON object or comma-separated model=limit pairs",
            value=raw_text,
        )
        return {}

    entries: dict[str, int] = {}
    saw_pair = False
    for pair in raw_text.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" in pair:
            model, limit = pair.split("=", 1)
        elif ":" in pair:
            model, limit = pair.split(":", 1)
        else:
            _warn_invalid_override(reason="expected model=limit", value=pair)
            continue

        saw_pair = True
        model_key = model.strip().lower()
        if not model_key:
            _warn_invalid_override(reason="model name is empty", value=pair)
            continue
        try:
            limit_value = int(limit.strip())
        except ValueError:
            _warn_invalid_override(reason="limit is not an integer", value=pair)
            continue
        if limit_value <= 0:
            _warn_invalid_override(reason="limit must be greater than zero", value=pair)
            continue
        entries[model_key] = limit_value

    if not saw_pair and not entries:
        _warn_invalid_override(
            reason="expected JSON object or comma-separated model=limit pairs",
            value=raw_text,
        )

    return entries


def match_token_overflow_error_pattern(error_message: Any) -> str | None:
    message = normalize_error_text(error_message)
    if not message:
        return None

    for pattern in TOKEN_OVERFLOW_ERROR_PATTERNS:
        normalized_pattern = normalize_error_text(pattern)
        if normalized_pattern and normalized_pattern in message:
            return pattern

    if "token" in message and "exceed" in message:
        return "token_exceed"

    return None


def normalize_error_text(value: Any) -> str:
    return (
        _as_text(value)
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )


def _build_model_context_resolution(
    *,
    model: str | None,
    normalized_model: str,
    limit: int | None,
    source: str,
    source_detail: str | None,
    confidence: float,
) -> ModelContextLimitResolution:
    catalog_based = source in {"catalog_exact", "catalog_prefix", "unknown"}
    return ModelContextLimitResolution(
        model=model,
        normalized_model=normalized_model,
        limit=limit,
        source=source,
        source_detail=source_detail,
        confidence=round(max(0.0, min(confidence, 1.0)), 2),
        catalog_version=MODEL_CONTEXT_LIMIT_CATALOG_VERSION,
        catalog_updated_at=MODEL_CONTEXT_LIMIT_CATALOG_UPDATED_AT,
        catalog_stale=_catalog_stale() if catalog_based else False,
        catalog_stale_after_days=MODEL_CONTEXT_LIMIT_CATALOG_STALE_AFTER_DAYS,
    )


def _catalog_stale(*, today: date | None = None) -> bool:
    try:
        updated_at = date.fromisoformat(MODEL_CONTEXT_LIMIT_CATALOG_UPDATED_AT)
    except ValueError:
        return True
    current_day = today or date.today()
    return (current_day - updated_at).days > MODEL_CONTEXT_LIMIT_CATALOG_STALE_AFTER_DAYS


def _coerce_model_limit_map(values: Mapping[str, Any]) -> dict[str, int]:
    entries: dict[str, int] = {}
    for raw_model, raw_limit in values.items():
        model_key = _as_text(raw_model).strip().lower()
        if not model_key:
            _warn_invalid_override(reason="model name is empty", value=str(raw_model))
            continue
        try:
            limit_value = int(raw_limit)
        except (TypeError, ValueError):
            _warn_invalid_override(
                reason="limit is not an integer",
                value=f"{model_key}={raw_limit}",
            )
            continue
        if limit_value <= 0:
            _warn_invalid_override(
                reason="limit must be greater than zero",
                value=f"{model_key}={raw_limit}",
            )
            continue
        entries[model_key] = limit_value
    return entries


def _warn_invalid_override(*, reason: str, value: str) -> None:
    safe_value = value[:160]
    signature = f"{reason}|{safe_value}"
    if signature in _warned_override_issues:
        return

    _warned_override_issues.add(signature)
    logger.warning(
        "[ZROKY] Ignoring invalid ZROKY_MODEL_CONTEXT_LIMITS entry: %s (%s)",
        safe_value,
        reason,
    )


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""
