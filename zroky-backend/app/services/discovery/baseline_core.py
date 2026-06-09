"""Pure baseline math for the Discovery engine (NO ORM / NO DB).

This is the single source of truth for how a behavioral baseline is computed
from a stream of traces. Both the production builder (`baseline.py`, which
persists) and the offline harness import from here, so the two can never
drift apart.
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from app.services.discovery.features import (
    BehavioralFeatures,
    behavior_key,
    sequence_key,
    status_is_failure,
)

DEFAULT_WARMUP_MIN_TRACES = 200
DEFAULT_WARMUP_MIN_DAYS = 3
DEFAULT_CRITICAL_TOOL_PCT = 0.90
SUSPECT_ERROR_RATE = 0.20


@dataclass
class NumericStats:
    """Online mean/variance via Welford (log-scaled inputs upstream)."""

    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, value: float) -> None:
        if not math.isfinite(value):
            return
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    @property
    def stdev(self) -> float:
        if self.count < 2:
            return 0.0
        return math.sqrt(max(self.m2 / (self.count - 1), 0.0))

    def to_dict(self) -> dict[str, float]:
        return {"count": self.count, "mean": self.mean, "stdev": self.stdev}


@dataclass
class BaselineConfig:
    warmup_min_traces: int = DEFAULT_WARMUP_MIN_TRACES
    warmup_min_days: int = DEFAULT_WARMUP_MIN_DAYS
    critical_tool_pct: float = DEFAULT_CRITICAL_TOOL_PCT


@dataclass
class _Accumulator:
    project_id: str
    agent_name: str | None
    workflow_name: str | None
    specificity: str
    sample_count: int = 0
    failures: int = 0
    days: set[str] = field(default_factory=set)
    tool_counts: Counter = field(default_factory=Counter)
    tool_sequences: Counter = field(default_factory=Counter)
    output_shapes: Counter = field(default_factory=Counter)
    statuses: Counter = field(default_factory=Counter)
    finish_reasons: Counter = field(default_factory=Counter)
    outcome_categories: Counter = field(default_factory=Counter)
    output_len: NumericStats = field(default_factory=NumericStats)
    latency_log: NumericStats = field(default_factory=NumericStats)
    cost_log: NumericStats = field(default_factory=NumericStats)
    window_start: datetime | None = None
    window_end: datetime | None = None

    def add(self, features: BehavioralFeatures, occurred_at: datetime | None) -> None:
        self.sample_count += 1
        if occurred_at is not None:
            self.days.add(occurred_at.date().isoformat())
            if self.window_start is None or occurred_at < self.window_start:
                self.window_start = occurred_at
            if self.window_end is None or occurred_at > self.window_end:
                self.window_end = occurred_at
        for tool in set(features.tool_names):
            self.tool_counts[tool] += 1
        self.tool_sequences[sequence_key(features.tool_names)] += 1
        self.output_shapes[features.output_shape] += 1
        self.statuses[features.status] += 1
        if features.finish_reason:
            self.finish_reasons[features.finish_reason] += 1
        if features.outcome_category:
            self.outcome_categories[features.outcome_category] += 1
        self.output_len.add(math.log1p(max(features.output_len, 0)))
        if features.latency_ms is not None and features.latency_ms >= 0:
            self.latency_log.add(math.log1p(features.latency_ms))
        if features.cost_usd >= 0:
            self.cost_log.add(math.log1p(features.cost_usd))
        if status_is_failure(features.status, features.error_code, features.outcome_category):
            self.failures += 1


def build_features_payload(acc: _Accumulator, config: BaselineConfig) -> dict:
    """Serialize an accumulator into the scorer-consumable features dict."""
    sample_count = max(acc.sample_count, 1)
    error_rate = acc.failures / sample_count
    status = "learning"
    if acc.sample_count >= config.warmup_min_traces and len(acc.days) >= config.warmup_min_days:
        status = "suspect" if error_rate >= SUSPECT_ERROR_RATE else "active"
    critical_tools = {
        tool: count / sample_count
        for tool, count in acc.tool_counts.items()
        if count / sample_count >= config.critical_tool_pct
    }
    payload = {
        "status": status,
        "specificity": acc.specificity,
        "low_specificity": acc.specificity != "exact",
        "sample_count": acc.sample_count,
        "distinct_days": len(acc.days),
        "error_rate": round(error_rate, 6),
        "warmup_min_traces": config.warmup_min_traces,
        "warmup_min_days": config.warmup_min_days,
        "critical_tools": critical_tools,
        "tool_sequences": dict(acc.tool_sequences),
        "output_shapes": dict(acc.output_shapes),
        "statuses": dict(acc.statuses),
        "finish_reasons": dict(acc.finish_reasons),
        "outcome_categories": dict(acc.outcome_categories),
        "output_len": acc.output_len.to_dict(),
        "latency_log": acc.latency_log.to_dict(),
        "cost_log": acc.cost_log.to_dict(),
    }
    if acc.window_start is not None:
        payload["window_start_at"] = acc.window_start.isoformat()
    if acc.window_end is not None:
        payload["window_end_at"] = acc.window_end.isoformat()
    return payload


def build_baselines_in_memory(
    traces: Iterable[tuple[BehavioralFeatures, datetime | None]],
    config: BaselineConfig | None = None,
) -> dict[str, dict]:
    """Group traces by behavior key → {behavior_key: features_payload}.

    Pure (no DB). Shared by `baseline.refresh` (production) and the harness.
    """
    config = config or BaselineConfig()
    accumulators: dict[str, _Accumulator] = {}
    for features, occurred_at in traces:
        key, specificity = behavior_key(features)
        acc = accumulators.get(key)
        if acc is None:
            acc = _Accumulator(
                project_id=features.project_id,
                agent_name=features.agent_name,
                workflow_name=features.workflow_name,
                specificity=specificity,
            )
            accumulators[key] = acc
        acc.add(features, occurred_at)
    return {key: build_features_payload(acc, config) for key, acc in accumulators.items()}
