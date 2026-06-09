"""Anomaly scorer for the Discovery engine.

Pure scoring: `(BehavioralFeatures, baseline-stats) → AnomalyCandidate | None`.
The baseline stats are passed as a plain dict (decoded from
`BehavioralBaseline.features_json`) so the scorer has no DB dependency and is
identical in production and in the offline harness.

Hard rule: every candidate carries a concrete, human-readable `reason`. If we
cannot explain *why* a trace is anomalous, we return None (no finding).
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.services.discovery.features import BehavioralFeatures, sequence_key

DEFAULT_Z_WEAK = 3.0
_MIN_STATS_SAMPLES = 20


@dataclass(frozen=True)
class AnomalyCandidate:
    """A scored deviation for one trace (pre-promotion)."""

    call_id: str
    signature: str
    primary_dimension: str
    anomaly_score: float
    confidence: float
    reason: str
    corroboration: tuple[str, ...]
    dimensions: tuple[str, ...]
    strong_structural: bool
    outcome_corroborated: bool


def _z_score(stats: Mapping[str, float], value: float) -> float | None:
    count = int(stats.get("count", 0) or 0)
    if count < _MIN_STATS_SAMPLES or not math.isfinite(value):
        return None
    mean = float(stats.get("mean", 0.0) or 0.0)
    stdev = float(stats.get("stdev", 0.0) or 0.0)
    spread = max(stdev, 0.05)
    return abs((value - mean) / spread)


def _weighted_score(dimensions: Mapping[str, float]) -> float:
    if not dimensions:
        return 0.0
    squared_mean = sum(v * v for v in dimensions.values()) / len(dimensions)
    recurrence_bonus = min(0.12, max(0, len(dimensions) - 1) * 0.04)
    return min(1.0, math.sqrt(squared_mean) + recurrence_bonus)


def make_signature(*parts: str) -> str:
    raw = "|".join(parts).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:24]


def _build_reason(
    features: BehavioralFeatures,
    label: str,
    corroboration: Sequence[str],
) -> str:
    prefix = f"On {label}, trace {features.call_id}"
    if not corroboration:
        return f"{prefix} deviated from baseline."
    if len(corroboration) == 1:
        return f"{prefix} deviated: {corroboration[0]}."
    return f"{prefix} deviated: " + "; ".join(corroboration[:4]) + "."


def score(
    features: BehavioralFeatures,
    baseline: Mapping,
    *,
    behavior_key: str,
    z_weak: float = DEFAULT_Z_WEAK,
) -> AnomalyCandidate | None:
    """Score one trace against a decoded baseline.

    `baseline` is a mapping with keys:
        status, specificity, low_specificity, sample_count, distinct_days,
        warmup_min_traces, warmup_min_days,
        critical_tools {name: pct}, tool_sequences {seq: count},
        output_shapes {shape: count}, statuses {status: count},
        finish_reasons {reason: count}, outcome_categories {cat: count},
        output_len {count,mean,stdev}, latency_log {...}, cost_log {...}
    Returns None if the baseline is not active or nothing is anomalous.
    """
    if str(baseline.get("status")) == "learning":
        return None

    dimensions: dict[str, float] = {}
    corroboration: list[str] = []
    strong_structural = False
    outcome_corroborated = False

    critical_tools: Mapping[str, float] = baseline.get("critical_tools", {}) or {}
    seen_tools = set(features.tool_names)
    missing_critical = [name for name in critical_tools if name not in seen_tools]
    if missing_critical:
        dimensions["missing_critical_tool"] = 1.0
        strong_structural = True
        details = ", ".join(
            f"{name} ({critical_tools[name]:.0%})" for name in missing_critical[:3]
        )
        corroboration.append(f"missing critical tool(s): {details}")

    tool_sequences: Mapping[str, int] = baseline.get("tool_sequences", {}) or {}
    seq = sequence_key(features.tool_names)
    if features.tool_names and tool_sequences and seq not in tool_sequences:
        dimensions["tool_sequence_unseen"] = max(dimensions.get("tool_sequence_unseen", 0.0), 0.72)
        corroboration.append("tool sequence was not seen during warmup")

    output_shapes: Mapping[str, int] = baseline.get("output_shapes", {}) or {}
    shape_total = sum(output_shapes.values())
    if shape_total >= _MIN_STATS_SAMPLES:
        shape_count = int(output_shapes.get(features.output_shape, 0))
        shape_surprise = 1.0 - (shape_count / shape_total)
        if shape_count == 0:
            dimensions["output_shape"] = 0.90
            strong_structural = True
            corroboration.append(f"output shape changed to {features.output_shape}")
        elif shape_surprise >= 0.85:
            dimensions["output_shape"] = shape_surprise
            corroboration.append(f"rare output shape {features.output_shape}")

    output_z = _z_score(baseline.get("output_len", {}), math.log1p(features.output_len))
    if output_z is not None and output_z >= z_weak:
        dimensions["output_length"] = min(1.0, output_z / 6.0)
        corroboration.append(f"output length z-score {output_z:.1f}")

    if features.latency_ms is not None and features.latency_ms >= 0:
        latency_z = _z_score(baseline.get("latency_log", {}), math.log1p(features.latency_ms))
        if latency_z is not None and latency_z >= z_weak:
            dimensions["latency"] = min(1.0, latency_z / 6.0)
            corroboration.append(f"latency z-score {latency_z:.1f}")

    cost_z = _z_score(baseline.get("cost_log", {}), math.log1p(max(features.cost_usd, 0.0)))
    if cost_z is not None and cost_z >= z_weak:
        dimensions["cost"] = min(1.0, cost_z / 6.0)
        corroboration.append(f"cost z-score {cost_z:.1f}")

    statuses: Mapping[str, int] = baseline.get("statuses", {}) or {}
    if sum(statuses.values()) >= _MIN_STATS_SAMPLES:
        if features.error_code or int(statuses.get(features.status, 0)) == 0:
            dimensions["status_error"] = 0.95
            corroboration.append(
                f"unusual status/error: {features.status}"
                + (f" / {features.error_code}" if features.error_code else "")
            )

    finish_reasons: Mapping[str, int] = baseline.get("finish_reasons", {}) or {}
    if features.finish_reason and finish_reasons:
        if sum(finish_reasons.values()) >= _MIN_STATS_SAMPLES and int(
            finish_reasons.get(features.finish_reason, 0)
        ) == 0:
            dimensions["finish_reason"] = 0.65
            corroboration.append(f"new finish reason {features.finish_reason}")

    outcomes: Mapping[str, int] = baseline.get("outcome_categories", {}) or {}
    if features.outcome_category and outcomes:
        total = sum(outcomes.values())
        dominant, dominant_count = max(outcomes.items(), key=lambda kv: kv[1])
        dominant_pct = dominant_count / max(total, 1)
        if dominant == "success" and dominant_pct >= 0.80 and features.outcome_category == "failure":
            dimensions["outcome_mismatch"] = 1.0
            outcome_corroborated = True
            corroboration.append("outcome changed from baseline success to failure")

    if not dimensions:
        return None

    anomaly_score = _weighted_score(dimensions)
    sample_count = int(baseline.get("sample_count", 0) or 0)
    distinct_days = int(baseline.get("distinct_days", 0) or 0)
    warmup_min_traces = max(int(baseline.get("warmup_min_traces", 200) or 200), 1)
    warmup_min_days = max(int(baseline.get("warmup_min_days", 3) or 3), 1)

    maturity = min(1.0, sample_count / max(warmup_min_traces * 2, 1))
    day_maturity = min(1.0, distinct_days / warmup_min_days)
    corroboration_score = min(1.0, len(dimensions) / 3.0)
    confidence = (anomaly_score * 0.62) + (corroboration_score * 0.23) + (maturity * day_maturity * 0.15)
    if bool(baseline.get("low_specificity")):
        confidence -= 0.15
    if str(baseline.get("status")) == "suspect":
        confidence -= 0.30
    if not features.outcome_category and not strong_structural:
        confidence -= 0.10
    confidence = max(0.0, min(1.0, confidence))

    primary = max(dimensions, key=dimensions.get)
    signature = make_signature(
        behavior_key,
        primary,
        ",".join(sorted(missing_critical)) or features.output_shape or features.status,
    )
    label = features.workflow_name or features.agent_name or features.project_id
    reason = _build_reason(features, label, corroboration)

    return AnomalyCandidate(
        call_id=features.call_id,
        signature=signature,
        primary_dimension=primary,
        anomaly_score=anomaly_score,
        confidence=confidence,
        reason=reason,
        corroboration=tuple(corroboration),
        dimensions=tuple(dimensions.keys()),
        strong_structural=strong_structural,
        outcome_corroborated=outcome_corroborated,
    )
