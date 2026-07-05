"""
Shared payload accessor utilities for all detector modules.

All functions are pure (no I/O, no state) and accept a Mapping[str, Any].
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.token_overflow_rules import (
    resolve_model_context_limit,
    token_rules_version,
)
from app.services.privacy import mask_text


# ---------------------------------------------------------------------------
# Core accessor primitives
# ---------------------------------------------------------------------------

def _pick(payload: Mapping[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current: Any = payload
        for segment in path:
            if not isinstance(current, Mapping) or segment not in current:
                current = None
                break
            current = current[segment]
        if current is not None:
            return current
    return None


def _as_int(value: Any, *, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback
        try:
            return int(float(text))
        except ValueError:
            return fallback
    return fallback


def _as_float(value: Any, *, fallback: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback
        try:
            return float(text)
        except ValueError:
            return fallback
    return fallback


def _as_str(value: Any, *, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _as_bool(value: Any, *, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return fallback


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Error field helpers
# ---------------------------------------------------------------------------

def _normalize_error_code(value: str) -> str:
    return value.strip().upper().replace("-", "_")


def _error_message_from_payload(payload: Mapping[str, Any]) -> str:
    return _as_str(
        _pick(
            payload,
            ("error_message",),
            ("error", "message"),
            ("failure_reason", "message"),
            ("failure_reason", "provider_error", "message"),
            ("failure_reason", "provider_error_body", "message"),
        )
    )


def _failure_reason(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _pick(payload, ("failure_reason",))
    return dict(value) if isinstance(value, Mapping) else {}


def _error_snippet(error_message: str) -> str | None:
    text = error_message.strip()
    if not text:
        return None
    return mask_text(text)[:240]


def _estimate_detection_allowed(payload: Mapping[str, Any]) -> bool:
    status = _as_str(_pick(payload, ("status",), ("call_status",))).strip().lower()
    if status in {
        "partial", "partial_success", "incomplete",
        "streaming", "cancelled", "canceled",
    }:
        return False
    if status in {"success", "completed", "complete", "ok", "succeeded"}:
        return False
    return True


# ---------------------------------------------------------------------------
# Model context limit resolution
# ---------------------------------------------------------------------------

def _resolve_model_context_limit(payload: Mapping[str, Any]) -> int:
    return _as_int(_resolve_model_context_limit_details(payload).get("limit"))


def _resolve_model_context_limit_details(payload: Mapping[str, Any]) -> dict[str, Any]:
    model = _as_str(_pick(payload, ("model",), ("request", "model")))

    explicit_limit = _as_int(
        _pick(
            payload,
            ("model_limit_tokens",),
            ("context_limit",),
            ("usage", "model_limit_tokens"),
            ("usage", "context_limit"),
            ("token_usage", "model_limit_tokens"),
            ("token_usage", "context_limit"),
        ),
    )
    if explicit_limit > 0:
        return _payload_model_context_limit_resolution(
            payload, model=model, limit=explicit_limit,
            source="payload_explicit", source_detail="model_limit_tokens/context_limit", confidence=1.0,
        )

    sdk_limit = _as_int(_pick(payload, ("model_context_limit",)))
    if sdk_limit > 0:
        source = _as_str(_pick(payload, ("model_context_limit_source",)), fallback="sdk_payload")
        source_detail = _as_str(
            _pick(payload, ("model_context_limit_source_detail",)), fallback="model_context_limit",
        )
        confidence = _as_float(_pick(payload, ("model_context_limit_confidence",)), fallback=0.88)
        return _payload_model_context_limit_resolution(
            payload, model=model, limit=sdk_limit,
            source=source, source_detail=source_detail, confidence=confidence,
        )

    return resolve_model_context_limit(model).to_dict()


def _payload_model_context_limit_resolution(
    payload: Mapping[str, Any],
    *,
    model: str,
    limit: int,
    source: str,
    source_detail: str,
    confidence: float,
) -> dict[str, Any]:
    fallback = resolve_model_context_limit(model).to_dict()
    normalized_model = _as_str(fallback.get("normalized_model")) or model.strip().lower()
    return {
        "model": model or None,
        "normalized_model": normalized_model,
        "limit": limit,
        "source": source,
        "source_detail": source_detail,
        "confidence": round(max(0.0, min(confidence, 1.0)), 2),
        "catalog_version": _as_str(
            _pick(payload, ("model_context_limit_catalog_version",)),
            fallback=_as_str(fallback.get("catalog_version")),
        ),
        "catalog_updated_at": _as_str(
            _pick(payload, ("model_context_limit_catalog_updated_at",)),
            fallback=_as_str(fallback.get("catalog_updated_at")),
        ),
        "catalog_stale": (
            False if source == "payload_explicit"
            else _as_bool(
                _pick(payload, ("model_context_limit_catalog_stale",)),
                fallback=bool(fallback.get("catalog_stale", False)),
            )
        ),
        "catalog_stale_after_days": _as_int(
            _pick(payload, ("model_context_limit_catalog_stale_after_days",)),
            fallback=_as_int(fallback.get("catalog_stale_after_days"), fallback=180),
        ),
    }
