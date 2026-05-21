"""Axis extractor — derive 6 variable axes from a Call record.

Each axis represents one "knob" that could explain a failure.
Extraction is pure-Python (zero LLM calls) and works from the fields
already stored on a Call row.

Axis types
----------
model_version    — call.model identifier; provider-model version string.
prompt_template  — call.prompt_fingerprint; stable hash of the prompt
                   template used.  None = no fingerprint recorded.
tool_behavior    — tool_calls_made count + timeout_triggered flag.
latency_env      — latency_ms; proxy for environment / backend health.
input_class      — normalized_output embedding cluster (approximated
                   by output token count bucket and error class here;
                   embedding NN is done in control_group.py).
retry_pattern    — fallback_chain length + retry_metadata presence.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Axis dataclass ─────────────────────────────────────────────────────────────


@dataclass
class Axis:
    axis_type: str
    axis_label: str
    failing_value: str | None
    raw: dict[str, Any] = field(default_factory=dict)


# ── Public function ────────────────────────────────────────────────────────────


def extract_axes(call) -> list[Axis]:
    """Return one Axis per variable dimension extracted from a Call ORM row.

    Parameters
    ----------
    call:
        A ``Call`` ORM instance (or duck-typed object with the same fields).
    """
    payload = _parse_payload(call.payload_json or "{}")
    axes: list[Axis] = []

    # 1. model_version
    model = str(call.model or "unknown")
    axes.append(Axis(
        axis_type="model_version",
        axis_label=f"Model: {model}",
        failing_value=model,
        raw={"model": model, "resolved_model": payload.get("resolved_model")},
    ))

    # 2. prompt_template
    fp = call.prompt_fingerprint if hasattr(call, "prompt_fingerprint") else payload.get("prompt_fingerprint")
    axes.append(Axis(
        axis_type="prompt_template",
        axis_label=f"Prompt fingerprint: {fp or 'not recorded'}",
        failing_value=fp,
        raw={"prompt_fingerprint": fp, "agent_name": call.agent_name},
    ))

    # 3. tool_behavior
    tool_calls = payload.get("tool_calls_made") or []
    tool_count = len(tool_calls) if isinstance(tool_calls, list) else 0
    timeout = bool(payload.get("timeout_triggered", False))
    tool_names = sorted({
        tc.get("name") or tc.get("function", {}).get("name", "unknown")
        for tc in (tool_calls if isinstance(tool_calls, list) else [])
    })
    axes.append(Axis(
        axis_type="tool_behavior",
        axis_label=f"Tool calls: {tool_count}, timeout: {timeout}, tools: {', '.join(tool_names) or 'none'}",
        failing_value=json.dumps({"count": tool_count, "timeout": timeout, "tools": tool_names}),
        raw={"tool_count": tool_count, "timeout_triggered": timeout, "tool_names": tool_names},
    ))

    # 4. latency_env
    latency = float(call.latency_ms or 0)
    axes.append(Axis(
        axis_type="latency_env",
        axis_label=f"Latency: {latency:.0f}ms",
        failing_value=str(latency),
        raw={"latency_ms": latency, "error_code": call.error_code},
    ))

    # 5. input_class (approximated without embeddings)
    output_tokens = int(call.output_tokens or 0)
    error_code = str(call.error_code or "none")
    bucket = _token_bucket(output_tokens)
    axes.append(Axis(
        axis_type="input_class",
        axis_label=f"Output: {bucket} tokens, error: {error_code}",
        failing_value=json.dumps({"token_bucket": bucket, "error_code": error_code}),
        raw={"output_tokens": output_tokens, "error_code": error_code, "token_bucket": bucket},
    ))

    # 6. retry_pattern
    fallback_chain = payload.get("fallback_chain") or []
    fallback_len = len(fallback_chain) if isinstance(fallback_chain, list) else 0
    has_retry_meta = bool(payload.get("retry_metadata"))
    axes.append(Axis(
        axis_type="retry_pattern",
        axis_label=f"Fallbacks: {fallback_len}, retry metadata: {has_retry_meta}",
        failing_value=json.dumps({"fallback_len": fallback_len, "has_retry_meta": has_retry_meta}),
        raw={"fallback_len": fallback_len, "has_retry_meta": has_retry_meta},
    ))

    return axes


# ── Helpers ────────────────────────────────────────────────────────────────────


def _parse_payload(payload_json: str) -> dict[str, Any]:
    try:
        return json.loads(payload_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def _token_bucket(tokens: int) -> str:
    if tokens == 0:
        return "empty"
    if tokens < 50:
        return "tiny"
    if tokens < 200:
        return "small"
    if tokens < 800:
        return "medium"
    return "large"
