"""Prompt fingerprint generation for LOOP_DETECTED pattern grouping.

The fingerprint intentionally captures logical intent rather than exact raw text.
It normalizes dynamic values and request formatting noise before hashing.
"""

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
_KEY_RE = re.compile(
    r"\b(?:sk|pk|rk|api|key|token)[_-][a-z0-9_-]{16,}\b",
    flags=re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")

_FALLBACK_FINGERPRINT = hashlib.sha256(b"zroky:fingerprint:fallback:v1").hexdigest()


def _stable_to_text(value: Any) -> str:
    """Create a deterministic textual representation for nested values."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(_stable_to_text(item) for item in value) + "]"
    if isinstance(value, dict):
        parts: list[str] = []
        for key in sorted(value.keys(), key=lambda item: str(item)):
            parts.append(f"{_stable_to_text(key)}:{_stable_to_text(value.get(key))}")
        return "{" + ",".join(parts) + "}"
    return str(value)


def normalize_text(text: str) -> str:
    """Normalize request text so equivalent intents hash to the same fingerprint."""
    try:
        normalized = _stable_to_text(text).strip().lower()
        normalized = _SPACE_RE.sub(" ", normalized)

        normalized = _TIMESTAMP_RE.sub("<time>", normalized)
        normalized = _UUID_RE.sub("<id>", normalized)
        normalized = _KEY_RE.sub("<secret>", normalized)
        normalized = _LONG_HEX_RE.sub("<secret>", normalized)
        normalized = _NUMBER_RE.sub("<num>", normalized)

        return _SPACE_RE.sub(" ", normalized).strip()
    except Exception:
        # Fail-safe: return an empty normalized block and let caller hash fallback-safe string.
        return ""


def normalize_messages(messages: list[dict]) -> str:
    """Normalize the last three messages only to avoid long conversation drift."""
    try:
        if not messages:
            return "messages:none"

        normalized_parts: list[str] = []
        for raw_message in messages[-3:]:
            if isinstance(raw_message, dict):
                role_raw = raw_message.get("role", "unknown")
                content_raw = raw_message.get("content", "")
            else:
                role_raw = "unknown"
                content_raw = raw_message

            role = normalize_text(_stable_to_text(role_raw)) or "unknown"
            content = normalize_text(_stable_to_text(content_raw))
            combined = f"{role}:{content}"[:500]
            normalized_parts.append(combined)

        return "|".join(normalized_parts) if normalized_parts else "messages:none"
    except Exception:
        return "messages:none"


def normalize_tools(tools: list[dict] | None) -> str:
    """Normalize tool definitions to sorted tool names only."""
    try:
        if not tools:
            return "tools:none"

        tool_names: set[str] = set()
        for tool in tools:
            if not isinstance(tool, dict):
                continue

            name = tool.get("name")
            if not name and isinstance(tool.get("function"), dict):
                name = tool["function"].get("name")

            normalized_name = normalize_text(_stable_to_text(name))
            if normalized_name:
                tool_names.add(normalized_name)

        if not tool_names:
            return "tools:none"

        return "tools:" + "|".join(sorted(tool_names))
    except Exception:
        return "tools:none"


def generate_prompt_fingerprint(
    messages: list[dict],
    tools: list[dict] | None,
    model: str,
) -> str:
    """Generate deterministic SHA-256 prompt fingerprint for logical request intent."""
    try:
        messages_part = normalize_messages(messages)
        tools_part = normalize_tools(tools)
        model_part = f"model:{normalize_text(model) or 'unknown'}"

        canonical = "|".join((messages_part, tools_part, model_part))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except Exception:
        return _FALLBACK_FINGERPRINT


if __name__ == "__main__":
    # Unit-test-like examples:
    # 1) Same prompt with different numbers -> same fingerprint.
    ex_a = generate_prompt_fingerprint(
        messages=[{"role": "user", "content": "summarize report id 123"}],
        tools=[{"name": "search"}],
        model="gpt-4o",
    )
    ex_b = generate_prompt_fingerprint(
        messages=[{"role": "user", "content": "summarize report id 999"}],
        tools=[{"name": "search"}],
        model="gpt-4o",
    )
    assert ex_a == ex_b

    # 2) Same prompt with extra whitespace -> same fingerprint.
    ex_c = generate_prompt_fingerprint(
        messages=[{"role": "user", "content": "  summarize    report id   123  "}],
        tools=[{"name": "search"}],
        model="gpt-4o",
    )
    assert ex_a == ex_c

    # 3) Different intent -> different fingerprint.
    ex_d = generate_prompt_fingerprint(
        messages=[{"role": "user", "content": "delete all reports"}],
        tools=[{"name": "search"}],
        model="gpt-4o",
    )
    assert ex_a != ex_d
