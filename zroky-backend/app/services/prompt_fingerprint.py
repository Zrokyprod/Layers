from __future__ import annotations

import hashlib
import re
from typing import Any

_SPACE_RE = re.compile(r"\s+")
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    flags=re.IGNORECASE,
)
_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[ t]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:z|[+-]\d{2}:\d{2})?)?\b",
    flags=re.IGNORECASE,
)
_LONG_HEX_RE = re.compile(r"\b[a-f0-9]{32,}\b", flags=re.IGNORECASE)
_KEY_RE = re.compile(r"\b(?:sk|pk|rk|api|key|token)[_-][a-z0-9_-]{16,}\b", flags=re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_FALLBACK_FINGERPRINT = hashlib.sha256(b"zroky:fingerprint:fallback:v1").hexdigest()


def _stable_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(_stable_to_text(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            f"{_stable_to_text(key)}:{_stable_to_text(value.get(key))}"
            for key in sorted(value.keys(), key=lambda item: str(item))
        ) + "}"
    return str(value)


def normalize_text(value: Any) -> str:
    try:
        normalized = _stable_to_text(value).strip().lower()
        normalized = _SPACE_RE.sub(" ", normalized)
        normalized = _TIMESTAMP_RE.sub("<time>", normalized)
        normalized = _UUID_RE.sub("<id>", normalized)
        normalized = _KEY_RE.sub("<secret>", normalized)
        normalized = _LONG_HEX_RE.sub("<secret>", normalized)
        normalized = _NUMBER_RE.sub("<num>", normalized)
        return _SPACE_RE.sub(" ", normalized).strip()
    except Exception:
        return ""


def normalize_messages(messages: list[dict[str, Any]]) -> str:
    try:
        if not messages:
            return "messages:none"
        parts: list[str] = []
        for raw_message in messages[-3:]:
            if isinstance(raw_message, dict):
                role_raw = raw_message.get("role", "unknown")
                content_raw = raw_message.get("content", "")
            else:
                role_raw = "unknown"
                content_raw = raw_message
            role = normalize_text(role_raw) or "unknown"
            content = normalize_text(content_raw)
            parts.append(f"{role}:{content}"[:500])
        return "|".join(parts) if parts else "messages:none"
    except Exception:
        return "messages:none"


def normalize_tools(tools: list[dict[str, Any]] | None) -> str:
    try:
        if not tools:
            return "tools:none"
        names: set[str] = set()
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            name = tool.get("name")
            if not name and isinstance(tool.get("function"), dict):
                name = tool["function"].get("name")
            normalized = normalize_text(name)
            if normalized:
                names.add(normalized)
        return "tools:" + "|".join(sorted(names)) if names else "tools:none"
    except Exception:
        return "tools:none"


def generate_prompt_fingerprint(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    model: str,
) -> str:
    try:
        canonical = "|".join(
            (
                normalize_messages(messages),
                normalize_tools(tools),
                f"model:{normalize_text(model) or 'unknown'}",
            )
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except Exception:
        return _FALLBACK_FINGERPRINT
