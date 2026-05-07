from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from zroky._internal.pii import mask_text, mask_value

_ISO_TS_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[tT ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b",
)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_LONG_TOKEN_RE = re.compile(r"\b[a-z0-9_-]{16,}\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_PUNCT_RE = re.compile(r"[^\w\s\[\]:-]+")
_STATIC_OUTPUTS = {"ok", "okay", "done", "yes", "no", "thanks", "thank you", "success"}
DEFAULT_LOOP_WINDOW_SIZE = 8


def normalize_loop_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        except TypeError:
            value = str(value)
    text = mask_text(value).lower()
    text = _ISO_TS_RE.sub(" ", text)
    text = _UUID_RE.sub(" ", text)
    text = _LONG_TOKEN_RE.sub(" ", text)
    text = _NUMBER_RE.sub(" ", text)
    text = _PUNCT_RE.sub(" ", text)
    return " ".join(text.split())


def output_signal(value: Any) -> dict[str, str | None]:
    normalized = normalize_loop_text(value)
    if not normalized or normalized in _STATIC_OUTPUTS or len(normalized) < 12:
        return {"normalized_output": normalized or None, "output_fingerprint": None}
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return {"normalized_output": normalized[:240], "output_fingerprint": digest}


def generate_output_fingerprint(output_content: str | None, provider: str, model: str) -> str | None:
    """Generate a deterministic fingerprint for an LLM output."""
    if not output_content:
        return None
    normalized = normalize_loop_text(output_content)
    if not normalized or normalized in _STATIC_OUTPUTS or len(normalized) < 12:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def output_similarity_score(left: Any, right: Any) -> float:
    left_tokens = set(normalize_loop_text(left).split())
    right_tokens = set(normalize_loop_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens.intersection(right_tokens))
    union = len(left_tokens.union(right_tokens))
    return round(overlap / max(union, 1), 3)


def signature_for_value(value: Any) -> str | None:
    normalized = normalize_loop_text(mask_value(value))
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def summarize_tool_lifecycle(
    tool_calls: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if not tool_calls:
        return None

    summary: list[dict[str, Any]] = []
    for item in tool_calls:
        if not isinstance(item, Mapping):
            continue
        function = item.get("function") if isinstance(item.get("function"), Mapping) else {}
        tool_name = item.get("name") or function.get("name") or item.get("tool_name")
        arguments = item.get("args") or item.get("arguments") or function.get("arguments")
        output = item.get("output") or item.get("result") or item.get("content")
        status = str(item.get("status") or "").strip().lower()
        success_raw = item.get("success")
        success = (
            bool(success_raw)
            if isinstance(success_raw, bool)
            else status in {"success", "ok", "completed"}
        )
        duration = item.get("duration_ms") or item.get("tool_duration_ms") or item.get("duration")
        state_changed_raw = item.get("state_changed")
        summary.append(
            {
                "tool_called": True,
                "tool_name": str(tool_name or "unknown")[:120],
                "tool_input_signature": signature_for_value(arguments),
                "tool_output_signature": signature_for_value(output),
                "tool_success": success,
                "tool_duration_ms": duration if isinstance(duration, (int, float)) else None,
                "state_changed": state_changed_raw if isinstance(state_changed_raw, bool) else None,
            }
        )
    return summary or None


def normalize_retry_metadata(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    retry_count = int(value.get("retry_count") or value.get("sdk_attempts") or 0)
    retry_reason = str(value.get("retry_reason") or value.get("reason") or "").strip()
    retry_interval = value.get("retry_interval") or value.get("retry_interval_ms")
    return {
        "retry_count": max(0, retry_count),
        "retry_reason": mask_text(retry_reason)[:120] if retry_reason else None,
        "retry_interval": retry_interval if isinstance(retry_interval, (int, float)) else None,
        "backoff_pattern": str(value.get("backoff_pattern") or "")[:64] or None,
        "max_steps_reached": bool(value.get("max_steps_reached")),
    }
