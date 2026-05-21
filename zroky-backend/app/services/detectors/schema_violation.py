"""SCHEMA_VIOLATION fast-rule detector.

Fires when the caller declared an expected output format / schema but
the model's textual output does not satisfy it.

Two activation paths:

  1. expected_format == "json" (or "yaml") — verifies parseability.
  2. expected_schema present (dict)         — performs a *light-weight*
     structural check (top-level type + required keys + key types).

We deliberately avoid a hard `jsonschema` dependency: the goal of this
detector is to surface the most common 90% of contract violations
(invalid JSON, missing required field, wrong top-level type) without
requiring an additional package install. Customers who need full JSON
Schema draft-7 validation can enable a richer detector via the plugin
entry-point system.
"""
from __future__ import annotations

import json
from collections.abc import Mapping as MappingABC
from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_str,
    _pick,
)

_RULE_CONFIDENCE_SCHEMA_VIOLATION = 0.95
_OUTPUT_PATHS: tuple[tuple[str, ...], ...] = (
    ("output_text",),
    ("response_text",),
    ("completion_text",),
    ("response", "content"),
    ("response", "text"),
    ("completion",),
    ("output",),
)
_PARSEABLE_FORMATS = frozenset({"json", "yaml"})
_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "object": MappingABC,
    "dict": MappingABC,
    "array": list,
    "list": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect_schema_violation(payload)


def _extract_output_text(payload: Mapping[str, Any]) -> str | None:
    for path in _OUTPUT_PATHS:
        value = _pick(payload, path)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _try_parse_json(text: str) -> tuple[Any, str | None]:
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        # Truncate the error to keep evidence stable across runtimes.
        return None, f"{exc.msg} (line {exc.lineno}, col {exc.colno})"


def _check_top_level_type(value: Any, expected: str) -> str | None:
    target = _TYPE_MAP.get(expected.lower().strip())
    if target is None:
        return None  # Unknown expected type — don't fail
    if isinstance(value, target):
        return None
    return f"top-level type expected {expected}, got {type(value).__name__}"


def _check_required_keys(
    value: Any, required: list[Any]
) -> str | None:
    if not isinstance(value, MappingABC):
        return f"required keys cannot be checked on non-object output (got {type(value).__name__})"
    missing = [str(k) for k in required if str(k) not in value]
    if not missing:
        return None
    return f"missing required keys: {sorted(missing)}"


def _check_key_types(
    value: Any, key_types: Mapping[str, str]
) -> str | None:
    if not isinstance(value, MappingABC):
        return None
    mismatches: list[str] = []
    for key, type_name in key_types.items():
        if key not in value:
            continue
        target = _TYPE_MAP.get(str(type_name).lower().strip())
        if target is None:
            continue
        if not isinstance(value[key], target):
            mismatches.append(
                f"{key} expected {type_name}, got {type(value[key]).__name__}"
            )
    if not mismatches:
        return None
    return "key type mismatch: " + "; ".join(mismatches)


def _validate_against_schema(
    value: Any, schema: Mapping[str, Any]
) -> str | None:
    """Light-weight structural validator. Returns a violation message or None."""
    expected_type = _as_str(schema.get("type"))
    if expected_type:
        violation = _check_top_level_type(value, expected_type)
        if violation:
            return violation

    required = schema.get("required")
    if isinstance(required, list) and required:
        violation = _check_required_keys(value, required)
        if violation:
            return violation

    properties = schema.get("properties")
    if isinstance(properties, MappingABC) and properties:
        key_types: dict[str, str] = {}
        for key, prop in properties.items():
            if isinstance(prop, MappingABC):
                prop_type = prop.get("type")
                if isinstance(prop_type, str):
                    key_types[str(key)] = prop_type
        if key_types:
            violation = _check_key_types(value, key_types)
            if violation:
                return violation

    return None


def _detect_schema_violation(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    expected_format = _as_str(
        _pick(
            payload,
            ("expected_format",),
            ("output", "expected_format"),
            ("contract", "expected_format"),
        ),
    ).lower()
    expected_schema = _pick(
        payload,
        ("expected_schema",),
        ("output", "expected_schema"),
        ("contract", "expected_schema"),
    )
    has_schema = isinstance(expected_schema, MappingABC) and bool(expected_schema)

    if expected_format not in _PARSEABLE_FORMATS and not has_schema:
        return None  # No contract declared — nothing to validate

    output_text = _extract_output_text(payload)
    if output_text is None:
        return None  # No output to validate (EMPTY_OUTPUT detector handles that)

    violation: str | None = None
    parsed: Any = None

    # Stage 1: parseability check
    if expected_format in _PARSEABLE_FORMATS or has_schema:
        # We use JSON parser even when format is yaml/unspecified — for
        # lightweight check, JSON is the dominant contract format. YAML
        # parsing is intentionally out-of-scope for the no-dep detector.
        parsed, parse_err = _try_parse_json(output_text)
        if parse_err is not None:
            violation = f"output is not valid JSON: {parse_err}"

    # Stage 2: schema structural check
    if violation is None and has_schema and parsed is not None:
        violation = _validate_against_schema(parsed, expected_schema)  # type: ignore[arg-type]

    if violation is None:
        return None

    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")
    model = _as_str(_pick(payload, ("model",), ("request", "model")), fallback="unknown")

    return {
        "category": "SCHEMA_VIOLATION",
        "speed_class": "fast",
        "confidence": _RULE_CONFIDENCE_SCHEMA_VIOLATION,
        "root_cause": (
            f"Model {model} produced output that does not satisfy the declared "
            f"contract: {violation}."
        ),
        "fix": {
            "primary": (
                "Add explicit format instructions to the system prompt and "
                "enable the provider's structured-output / JSON-mode flag "
                "(response_format={'type': 'json_object'} for OpenAI, "
                "tool_choice for Anthropic)."
            ),
            "code": (
                "client.chat.completions.create(\n"
                "    model=...,\n"
                "    response_format={'type': 'json_object'},\n"
                "    messages=[...]\n"
                ")"
            ),
            "alternative": (
                "Wrap the call with a Pydantic / jsonschema validator that "
                "retries once on parse failure with a self-correction prompt "
                "containing the validator's error message."
            ),
        },
        "evidence": {
            "provider": provider,
            "model": model,
            "expected_format": expected_format or None,
            "expected_schema_top_level_type": (
                _as_str(expected_schema.get("type")) if has_schema else None  # type: ignore[union-attr]
            ),
            "violation": violation,
            "trigger_rule": "expected_format_or_schema_with_violation",
        },
    }
