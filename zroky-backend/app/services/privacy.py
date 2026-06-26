from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping

_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]{80,}={0,2}$")
_DATA_URL_RE = re.compile(r"^data:[^;,\s]+;base64,", re.IGNORECASE)
_SENSITIVE_KEY_MARKERS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "credential",
)
_IDENTIFIER_KEYS = {
    "user_id",
    "customer_id",
    "account_id",
    "external_id",
    "email",
    "phone",
}
_NON_SECRET_TOKEN_KEYS = {
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "total_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "estimated_prompt_tokens",
    "token_estimator_version",
    "token_rules_version",
    "token_unit",
}
_PASSTHROUGH_KEYS = {
    "approval_scope_hash",
    "event_digest",
    "evidence_hash",
    "intent_digest",
    "plan_digest",
    "prompt_fingerprint",
    "receipt_digest",
    "schema_digest",
    "output_fingerprint",
}
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

# ── India-specific identifier patterns (DPDP Act / Aadhaar Act compliance) ────
# Mirrors the SDK-side patterns in zroky-sdk/zroky/_internal/pii.py for
# defense-in-depth: redact at the backend boundary even when an SDK build
# predates these rules.
_AADHAAR_FORMATTED_RE = re.compile(
    r"(?<!\d)\d{4}[\s-]\d{4}[\s-]\d{4}(?!\d)"
)
_AADHAAR_CONTEXT_RE = re.compile(
    r"(?i)\b(aadhaar|aadhar|uidai)\b"
    r"\s*(?:no\.?|number|#|:|is|=)?\s*"
    r"\d{4}[\s-]?\d{4}[\s-]?\d{4}"
)
_PAN_RE = re.compile(r"(?i)\b[A-Z]{5}\d{4}[A-Z]\b")
_GSTIN_RE = re.compile(r"(?i)\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]\b")
_IFSC_RE = re.compile(r"(?i)\b[A-Z]{4}0[A-Z0-9]{6}\b")
_INDIAN_PHONE_RE = re.compile(
    r"(?<!\d)\+?91[\s\-.]?[6-9]\d{9}(?!\d)"
)

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE),
        "[REDACTED_EMAIL]",
    ),
    # India: PAN / GSTIN / IFSC — strict alphanumeric formats, very low FP risk.
    (_GSTIN_RE, "[REDACTED_GSTIN]"),
    (_IFSC_RE, "[REDACTED_IFSC]"),
    (_PAN_RE, "[REDACTED_PAN]"),
    # India: Aadhaar — context-cued first (preserves label), then formatted.
    (_AADHAAR_CONTEXT_RE, "[REDACTED_AADHAAR]"),
    (_AADHAAR_FORMATTED_RE, "[REDACTED_AADHAAR]"),
    # India: +91-prefixed mobile — must precede the US phone regex so that
    # the country code is not partially consumed by the generic pattern.
    (_INDIAN_PHONE_RE, "[REDACTED_PHONE]"),
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
    (re.compile(r"sk-(?:proj-)?[a-zA-Z0-9]{20,}"), "[REDACTED_KEY]"),
    (re.compile(r"sk-ant-[a-zA-Z0-9\-]{20,}"), "[REDACTED_KEY]"),
    (re.compile(r"(?<!\d)\d{3}[-\s]?\d{2}[-\s]?\d{4}(?!\d)"), "[REDACTED]"),
    (_ADDRESS_RE, "[REDACTED_ADDRESS]"),
    (_NAME_CONTEXT_RE, r"\1: [REDACTED_NAME]"),
    (_NATURAL_SECRET_RE, r"\1: [REDACTED]"),
]


def _compile_custom_patterns(patterns: list[str] | tuple[str, ...] | None) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for raw_pattern in patterns or ():
        if not isinstance(raw_pattern, str) or not raw_pattern.strip():
            continue
        try:
            compiled.append(re.compile(raw_pattern.strip(), re.IGNORECASE))
        except re.error:
            continue
    return compiled


def mask_text(value: str, *, custom_patterns: list[str] | tuple[str, ...] | None = None) -> str:
    stripped = value.strip()
    if _DATA_URL_RE.match(stripped) or _BASE64_RE.match(stripped):
        return "[REDACTED]"
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    for pattern in _compile_custom_patterns(custom_patterns):
        value = pattern.sub("[REDACTED]", value)
    return value


def hash_identifier(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    if not rendered:
        return None
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:24]
    return f"hash:{digest}"


def _mask_keyed_value(
    key: str,
    value: Any,
    *,
    custom_patterns: list[str] | tuple[str, ...] | None,
) -> Any:
    normalized_key = key.strip().lower()
    if normalized_key in _PASSTHROUGH_KEYS:
        return deepcopy(value)
    if normalized_key in _NON_SECRET_TOKEN_KEYS:
        return mask_value(value, custom_patterns=custom_patterns)
    if any(marker in normalized_key for marker in _SENSITIVE_KEY_MARKERS):
        return "[REDACTED_KEY]" if value not in (None, "") else value
    if normalized_key in _IDENTIFIER_KEYS:
        if isinstance(value, str):
            stripped_value = value.strip()
            if stripped_value.startswith("[REDACTED") and stripped_value.endswith("]"):
                return stripped_value
            if stripped_value.startswith("hash:"):
                return stripped_value

            masked = mask_text(value, custom_patterns=custom_patterns)
            if masked != value:
                return masked
        return hash_identifier(value)
    return mask_value(value, custom_patterns=custom_patterns)


def mask_value(value: Any, *, custom_patterns: list[str] | tuple[str, ...] | None = None) -> Any:
    if isinstance(value, str):
        return mask_text(value, custom_patterns=custom_patterns)
    if isinstance(value, list):
        return [mask_value(item, custom_patterns=custom_patterns) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_value(item, custom_patterns=custom_patterns) for item in value)
    if isinstance(value, Mapping):
        return {
            str(key): _mask_keyed_value(
                str(key),
                item,
                custom_patterns=custom_patterns,
            )
            for key, item in value.items()
        }
    return deepcopy(value)


def mask_payload(
    payload: Mapping[str, Any] | None,
    *,
    custom_patterns: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    return mask_value(dict(payload), custom_patterns=custom_patterns)


def mask_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    custom_patterns: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        return {}
    return mask_value(dict(metadata), custom_patterns=custom_patterns)


def mask_error_message(
    error: Any,
    *,
    max_length: int = 512,
    custom_patterns: list[str] | tuple[str, ...] | None = None,
) -> str:
    try:
        rendered = str(error)
    except Exception:
        rendered = type(error).__name__
    rendered = " ".join(rendered.split())
    return mask_text(rendered, custom_patterns=custom_patterns)[:max_length]


def mask_json_string(
    raw: str | None,
    *,
    custom_patterns: list[str] | tuple[str, ...] | None = None,
) -> str | None:
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return mask_text(str(raw), custom_patterns=custom_patterns)
    return json.dumps(mask_value(parsed, custom_patterns=custom_patterns), separators=(",", ":"))
