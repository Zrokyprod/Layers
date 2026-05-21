"""Axis confidence scorer — statistical separation between failing and control.

For each Axis, this module computes:

  confidence(A) = statistical_separation(A_value_in_fail, A_distribution_in_control)

The separation metric is a blend of:
  1. Value mismatch rate — fraction of control traces with a DIFFERENT axis value
     than the failing trace.  High mismatch = axis is likely causal.
  2. Population signal (when available) — compare fail rate among calls with
     this axis value vs. the broader population.

Final confidence is in [0.0, 1.0].  Axes are sorted descending by confidence
so the first axis is the most likely root cause.

No LLM calls.  No external API calls.  Pure computation.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any

from app.services.ablation.axis_extractor import Axis
from app.services.ablation.control_group import ControlTrace

logger = logging.getLogger(__name__)


@dataclass
class ScoredAxis:
    axis: Axis
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)


def score_axes(
    failing_call_axes: list[Axis],
    control_group: list[ControlTrace],
) -> list[ScoredAxis]:
    """Score each axis against the control group.

    Returns axes sorted by confidence descending.

    Parameters
    ----------
    failing_call_axes:  Extracted axes from the failing call.
    control_group:      Control traces found by control_group.py.
    """
    if not control_group:
        return [ScoredAxis(ax, confidence=0.0, evidence={"reason": "no_control_group"})
                for ax in failing_call_axes]

    scored = []
    for ax in failing_call_axes:
        conf, evidence = _score_single_axis(ax, control_group)
        scored.append(ScoredAxis(ax, confidence=round(min(1.0, max(0.0, conf)), 4), evidence=evidence))

    scored.sort(key=lambda s: -s.confidence)
    return scored


# ── Per-axis scorers ────────────────────────────────────────────────────────────


def _score_single_axis(
    ax: Axis,
    control: list[ControlTrace],
) -> tuple[float, dict[str, Any]]:
    dispatch = {
        "model_version": _score_model_version,
        "prompt_template": _score_prompt_template,
        "tool_behavior": _score_tool_behavior,
        "latency_env": _score_latency_env,
        "input_class": _score_input_class,
        "retry_pattern": _score_retry_pattern,
    }
    scorer = dispatch.get(ax.axis_type, _score_generic)
    return scorer(ax, control)


def _score_model_version(ax: Axis, control: list[ControlTrace]) -> tuple[float, dict]:
    failing_model = ax.raw.get("model", "unknown")
    ctrl_models = [c.model for c in control]
    ctrl_dominant = _mode(ctrl_models)
    matching = sum(1 for m in ctrl_models if m == failing_model)
    mismatch_rate = 1.0 - (matching / len(ctrl_models))
    evidence = {
        "failing_model": failing_model,
        "control_dominant_model": ctrl_dominant,
        "control_group_size": len(ctrl_models),
        "matching_fraction": round(matching / len(ctrl_models), 4),
        "mismatch_rate": round(mismatch_rate, 4),
    }
    # If failing model matches most of the control, model version isn't the cause
    # If failing model is rare in control (or absent), it's suspicious
    confidence = mismatch_rate * 0.9
    return confidence, evidence


def _score_prompt_template(ax: Axis, control: list[ControlTrace]) -> tuple[float, dict]:
    failing_fp = ax.raw.get("prompt_fingerprint")
    ctrl_fps = [c.prompt_fingerprint for c in control]
    if failing_fp is None:
        return 0.0, {"reason": "no_prompt_fingerprint_recorded"}

    matching = sum(1 for fp in ctrl_fps if fp == failing_fp)
    mismatch_rate = 1.0 - (matching / len(ctrl_fps))
    ctrl_dominant = _mode([fp for fp in ctrl_fps if fp is not None])
    evidence = {
        "failing_fingerprint": failing_fp,
        "control_dominant_fingerprint": ctrl_dominant,
        "control_group_size": len(ctrl_fps),
        "matching_fraction": round(matching / len(ctrl_fps), 4),
        "mismatch_rate": round(mismatch_rate, 4),
    }
    # High mismatch means successful calls use a DIFFERENT prompt — this prompt revision is suspect
    confidence = mismatch_rate * 0.85
    return confidence, evidence


def _score_tool_behavior(ax: Axis, control: list[ControlTrace]) -> tuple[float, dict]:
    failing_count = ax.raw.get("tool_count", 0)
    failing_timeout = ax.raw.get("timeout_triggered", False)
    ctrl_counts = [c.tool_count for c in control]
    ctrl_timeouts = [1 for c in control if _control_timeout(c)]

    avg_ctrl_count = sum(ctrl_counts) / len(ctrl_counts) if ctrl_counts else 0
    ctrl_timeout_rate = len(ctrl_timeouts) / len(control)

    diff_tools = abs(failing_count - avg_ctrl_count) / (max(avg_ctrl_count, 1))
    timeout_signal = 0.9 if failing_timeout and ctrl_timeout_rate < 0.15 else 0.0

    evidence = {
        "failing_tool_count": failing_count,
        "failing_timeout": failing_timeout,
        "control_avg_tool_count": round(avg_ctrl_count, 2),
        "control_timeout_rate": round(ctrl_timeout_rate, 4),
        "tool_count_divergence": round(diff_tools, 4),
    }
    confidence = min(1.0, diff_tools * 0.5 + timeout_signal)
    return confidence, evidence


def _score_latency_env(ax: Axis, control: list[ControlTrace]) -> tuple[float, dict]:
    failing_ms = ax.raw.get("latency_ms", 0.0)
    ctrl_latencies = [c.latency_ms for c in control if c.latency_ms is not None]
    if not ctrl_latencies:
        return 0.0, {"reason": "no_control_latency_data"}

    ctrl_mean = sum(ctrl_latencies) / len(ctrl_latencies)
    ctrl_stddev = _stddev(ctrl_latencies)
    z_score = (failing_ms - ctrl_mean) / max(ctrl_stddev, 1.0)

    # z > 2.0 → failure is a latency outlier → environmental
    confidence = min(1.0, max(0.0, (z_score - 1.0) / 3.0)) if z_score > 1.0 else 0.0
    evidence = {
        "failing_latency_ms": failing_ms,
        "control_mean_ms": round(ctrl_mean, 2),
        "control_stddev_ms": round(ctrl_stddev, 2),
        "z_score": round(z_score, 3),
        "control_group_size": len(ctrl_latencies),
    }
    return confidence, evidence


def _score_input_class(ax: Axis, control: list[ControlTrace]) -> tuple[float, dict]:
    failing_bucket = ax.raw.get("token_bucket", "unknown")
    ctrl_buckets = _token_buckets(control)
    if not ctrl_buckets:
        return 0.0, {"reason": "no_token_data"}
    ctrl_dominant_bucket = _mode(ctrl_buckets)
    mismatch = int(failing_bucket != ctrl_dominant_bucket)
    evidence = {
        "failing_token_bucket": failing_bucket,
        "control_dominant_bucket": ctrl_dominant_bucket,
        "control_bucket_counts": dict(_counter(ctrl_buckets)),
    }
    # Token bucket mismatch is weak signal — cap at 0.35
    confidence = mismatch * 0.35
    return confidence, evidence


def _score_retry_pattern(ax: Axis, control: list[ControlTrace]) -> tuple[float, dict]:
    failing_fb = ax.raw.get("fallback_len", 0)
    failing_retry = ax.raw.get("has_retry_meta", False)
    ctrl_fb_lens = [c.fallback_len for c in control]
    avg_ctrl_fb = sum(ctrl_fb_lens) / len(ctrl_fb_lens) if ctrl_fb_lens else 0
    fb_divergence = (failing_fb - avg_ctrl_fb) / max(avg_ctrl_fb, 0.5)
    evidence = {
        "failing_fallback_len": failing_fb,
        "failing_has_retry_meta": failing_retry,
        "control_avg_fallback_len": round(avg_ctrl_fb, 2),
        "fallback_divergence": round(fb_divergence, 4),
    }
    confidence = min(1.0, max(0.0, fb_divergence * 0.6))
    return confidence, evidence


def _score_generic(ax: Axis, control: list[ControlTrace]) -> tuple[float, dict]:
    return 0.0, {"reason": "no_scorer_for_axis_type", "axis_type": ax.axis_type}


# ── Utility ────────────────────────────────────────────────────────────────────


def _mode(values: list) -> Any:
    if not values:
        return None
    counts = _counter(values)
    return max(counts, key=lambda k: counts[k])


def _counter(values: list) -> dict:
    c: dict = {}
    for v in values:
        c[v] = c.get(v, 0) + 1
    return c


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def _token_buckets(control: list[ControlTrace]) -> list[str]:
    buckets = []
    for c in control:
        t = c.output_tokens
        if t == 0:
            b = "empty"
        elif t < 50:
            b = "tiny"
        elif t < 200:
            b = "small"
        elif t < 800:
            b = "medium"
        else:
            b = "large"
        buckets.append(b)
    return buckets


def _control_timeout(c: ControlTrace) -> bool:
    return bool(c.payload.get("timeout_triggered", False))
