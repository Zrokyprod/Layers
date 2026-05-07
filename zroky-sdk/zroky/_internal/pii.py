"""Deterministic PII masking applied before any telemetry leaves the SDK."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]{80,}={0,2}$")
_DATA_URL_RE = re.compile(r"^data:[^;,\s]+;base64,", re.IGNORECASE)
_STREET_SUFFIXES = (
    "street",
    "st",
    "avenue",
    "ave",
    "road",
    "rd",
    "drive",
    "dr",
    "lane",
    "ln",
    "boulevard",
    "blvd",
    "court",
    "ct",
    "place",
    "pl",
    "way",
    "circle",
    "cir",
    "highway",
    "hwy",
)
_NAME_CONTEXT_RE = re.compile(
    r"(?i)\b("
    r"name|full name|customer|patient|employee|contact|user|applicant|recipient"
    r")\s*(?:is|=|:)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b"
)
_ADDRESS_RE = re.compile(
    r"(?i)\b\d{1,6}\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){0,5}\s+"
    rf"(?:{'|'.join(_STREET_SUFFIXES)})\.?"
    r"(?:\s*(?:,\s*)?(?:apt|apartment|suite|ste|unit|floor|fl)\.?\s*[A-Za-z0-9-]+)?"
    r"(?:\s*,\s*[A-Za-z .'-]+)?"
    r"(?:\s*,\s*[A-Z]{2})?"
    r"(?:\s+\d{5}(?:-\d{4})?)?\b"
)
_NATURAL_SECRET_RE = re.compile(
    r"(?i)\b("
    r"password|passcode|access code|recovery code|verification code|otp|secret phrase|"
    r"private key|seed phrase|client secret"
    r")\s*(?:is|=|:)\s*([^\s,;]{4,}|.{8,80}?)(?=$|[.;,\n])"
)

# Replacement tokens are intentionally irreversible and stable across SDK/backend.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE),
        "[REDACTED_EMAIL]",
    ),
    (
        re.compile(
            r"(?<!\w)(\+?1[\s\-.]?)?"
            r"\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"
            r"(?!\d)",
        ),
        "[REDACTED_PHONE]",
    ),
    (
        re.compile(
            r"(?<!\d)"
            r"(?:4[0-9]{12}(?:[0-9]{3})?|"
            r"5[1-5][0-9]{14}|"
            r"3[47][0-9]{13}|"
            r"6(?:011|5[0-9]{2})[0-9]{12})"
            r"(?!\d)",
        ),
        "[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)(?:sk|pk|api[_-]?key|token|secret|bearer)\s*[=:\"']?\s*"
            r"[a-zA-Z0-9\-_]{20,}",
        ),
        "[REDACTED_KEY]",
    ),
    (
        re.compile(r"sk-(?:proj-)?[a-zA-Z0-9]{20,}"),
        "[REDACTED_KEY]",
    ),
    (
        re.compile(r"sk-ant-[a-zA-Z0-9\-]{20,}"),
        "[REDACTED_KEY]",
    ),
    (
        re.compile(r"(?<!\d)\d{3}[-\s]?\d{2}[-\s]?\d{4}(?!\d)"),
        "[REDACTED]",
    ),
    (_ADDRESS_RE, "[REDACTED_ADDRESS]"),
    (_NAME_CONTEXT_RE, r"\1: [REDACTED_NAME]"),
    (_NATURAL_SECRET_RE, r"\1: [REDACTED]"),
]


def mask_text(text: str) -> str:
    """Apply all PII patterns to a single string."""
    stripped = text.strip()
    if _DATA_URL_RE.match(stripped) or _BASE64_RE.match(stripped):
        return "[REDACTED]"
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def mask_value(value: Any) -> Any:
    """Recursively mask strings in JSON-like telemetry values."""
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, list):
        return [mask_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_value(item) for item in value)
    if isinstance(value, dict):
        return {key: mask_value(item) for key, item in value.items()}
    return deepcopy(value)


def mask_error_message(error: Any, *, max_length: int = 512) -> str:
    """Render and mask provider errors without preserving raw stack details."""
    try:
        rendered = str(error)
    except Exception:
        rendered = type(error).__name__
    rendered = " ".join(rendered.split())
    return mask_text(rendered)[:max_length]


def hash_identifier(value: Any) -> str | None:
    """Deterministically pseudonymize user/customer identifiers."""
    if value is None:
        return None
    rendered = str(value).strip()
    if not rendered:
        return None
    if mask_text(rendered) != rendered:
        return mask_text(rendered)
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:24]
    return f"hash:{digest}"


def mask_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Return a deep copy of messages with PII masked in content fields.
    Handles string content and nested multipart content.
    """
    masked = deepcopy(messages)
    for msg in masked:
        content = msg.get("content")
        if isinstance(content, str):
            msg["content"] = mask_text(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        part["text"] = mask_text(part.get("text", ""))
                    else:
                        for key, value in list(part.items()):
                            if key != "type":
                                part[key] = mask_value(value)
        else:
            msg["content"] = mask_value(content)
    return masked


def mask_json_string(value: str) -> str:
    """Mask a JSON string while preserving valid JSON when possible."""
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return mask_text(value)
    return json.dumps(mask_value(parsed), separators=(",", ":"))
