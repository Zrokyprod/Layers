"""
Frozen dataclasses for Provider Drift Watch.

These are pure value types — no I/O, no DB, no external deps. They form
the contract surface between layers (suite loader → runner → drift
detector → aggregator → API). Frozen + slot-friendly for cheap copies
and to prevent accidental mutation in the middle of a pipeline.

JSON serialization mirrors the on-the-wire shape. `to_dict()` keeps the
schema explicit so adding fields cannot accidentally leak via dict
unpacking elsewhere.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Final


class ProbeOutcome:
    """The five terminal outcomes a probe can land in."""

    OK: Final[str] = "ok"
    RATE_LIMITED: Final[str] = "rate_limited"
    TIMEOUT: Final[str] = "timeout"
    CONTENT_FILTERED: Final[str] = "content_filtered"
    BUDGET_EXCEEDED: Final[str] = "budget_exceeded"
    ERROR: Final[str] = "error"

    ALL: Final[tuple[str, ...]] = (
        OK,
        RATE_LIMITED,
        TIMEOUT,
        CONTENT_FILTERED,
        BUDGET_EXCEEDED,
        ERROR,
    )


_VALID_OUTCOMES = frozenset(ProbeOutcome.ALL)


@dataclass(frozen=True)
class PromptSpec:
    """One prompt in the deterministic suite.

    `expected_signal` carries judge instructions in a JSON-serializable
    dict. Schema (intentionally informal — the judge layer is the only
    consumer):
        - kind: 'must_contain' | 'must_refuse' | 'must_match_regex' |
                'json_schema' | 'numeric_equals' | 'free_form'
        - value: any                  # depends on kind
        - case_sensitive: bool        # for must_contain / must_match_regex
        - notes: str                  # human-only

    `version` lets us change wording without throwing away history —
    bump it; the runner only ever samples `active=True` rows; the
    aggregator joins by `prompt_id` so old probes remain queryable.
    """

    id: str
    category: str
    prompt_text: str
    expected_signal: dict[str, Any]
    system_prompt: str | None = None
    max_tokens: int = 512
    version: int = 1
    active: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("PromptSpec.id required")
        if self.category not in {
            "math", "refusal", "code", "summarization",
            "multi_turn", "tool_use", "factuality",
            "instruction_following",
        }:
            raise ValueError(f"PromptSpec.category invalid: {self.category}")
        if self.max_tokens <= 0 or self.max_tokens > 8192:
            raise ValueError("PromptSpec.max_tokens out of range (1..8192)")
        if self.version < 1:
            raise ValueError("PromptSpec.version must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "prompt_text": self.prompt_text,
            "system_prompt": self.system_prompt,
            "max_tokens": self.max_tokens,
            "expected_signal": dict(self.expected_signal),
            "version": self.version,
            "active": self.active,
        }


@dataclass(frozen=True)
class ModelSpec:
    """One LLM under continuous observation.

    `family` groups variants (e.g. all `gpt-4o-*` snapshots). UI groups
    by family for compact display.
    """

    id: str
    provider: str
    model_id: str
    display_name: str
    family: str
    active: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("ModelSpec.id required")
        if self.provider not in {
            "openai", "anthropic", "google", "meta",
            "mistral", "xai", "other",
        }:
            raise ValueError(f"ModelSpec.provider invalid: {self.provider}")
        if not self.model_id:
            raise ValueError("ModelSpec.model_id required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProbeResult:
    """The runner's output for a single (prompt, model) pair.

    `output_embedding` is None when the embedder is unavailable or the
    outcome is not 'ok'. The drift detector treats a missing embedding
    as a coverage hole (not a regression).
    """

    prompt_id: str
    model_id: str
    outcome: str
    output_text: str | None = None
    output_embedding: tuple[float, ...] | None = None
    embedding_model: str | None = None
    judge_pass: bool | None = None
    judge_score: float | None = None
    latency_ms: int | None = None
    cost_usd: float = 0.0
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in _VALID_OUTCOMES:
            raise ValueError(f"ProbeResult.outcome invalid: {self.outcome}")
        if self.outcome != ProbeOutcome.OK:
            # Defensive: error rows must not carry judge verdicts.
            if self.judge_pass is not None:
                object.__setattr__(self, "judge_pass", None)
            if self.judge_score is not None:
                object.__setattr__(self, "judge_score", None)

    @property
    def is_ok(self) -> bool:
        return self.outcome == ProbeOutcome.OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "model_id": self.model_id,
            "outcome": self.outcome,
            "output_text": self.output_text,
            "output_embedding": (
                list(self.output_embedding)
                if self.output_embedding is not None
                else None
            ),
            "embedding_model": self.embedding_model,
            "judge_pass": self.judge_pass,
            "judge_score": self.judge_score,
            "latency_ms": self.latency_ms,
            "cost_usd": float(self.cost_usd),
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class DriftMetric:
    """One (model, category, day) drift computation.

    The aggregator wraps this in a `DriftAlertSpec` only when the
    publishing rules fire. Standalone consumers (UI time-series) read
    the metric directly from the probes table; this dataclass is the
    in-memory representation.
    """

    model_id: str
    category: str
    current_date: date
    baseline_start: date
    baseline_end: date
    pass_rate_current: float
    pass_rate_baseline: float
    pass_rate_stddev: float
    judge_z: float
    embedding_z: float
    coverage_current: float          # fraction of category prompts with outcome=ok
    coverage_baseline_min: float     # min coverage across baseline days
    sample_size_current: int
    sample_size_baseline: int

    def __post_init__(self) -> None:
        if not (0.0 <= self.coverage_current <= 1.0):
            raise ValueError("coverage_current out of range")
        if not (0.0 <= self.coverage_baseline_min <= 1.0):
            raise ValueError("coverage_baseline_min out of range")

    @property
    def delta_pp(self) -> float:
        """Signed percentage-point delta (current minus baseline)."""
        return (self.pass_rate_current - self.pass_rate_baseline) * 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "category": self.category,
            "current_date": self.current_date.isoformat(),
            "baseline_start": self.baseline_start.isoformat(),
            "baseline_end": self.baseline_end.isoformat(),
            "pass_rate_current": self.pass_rate_current,
            "pass_rate_baseline": self.pass_rate_baseline,
            "pass_rate_stddev": self.pass_rate_stddev,
            "judge_z": self.judge_z,
            "embedding_z": self.embedding_z,
            "delta_pp": self.delta_pp,
            "coverage_current": self.coverage_current,
            "coverage_baseline_min": self.coverage_baseline_min,
            "sample_size_current": self.sample_size_current,
            "sample_size_baseline": self.sample_size_baseline,
        }


@dataclass(frozen=True)
class DriftAlertSpec:
    """Persisted, publishable alert.

    `is_candidate=True` means only one of (judge_z, embedding_z) crossed
    the threshold; we keep the row for forensics but exclude it from
    the public banner and RSS feed.
    """

    model_id: str
    category: str
    current_date: date
    baseline_start: date
    baseline_end: date
    pass_rate_current: float
    pass_rate_baseline: float
    judge_z: float
    embedding_z: float
    delta_pp: float
    severity: str
    headline: str
    is_candidate: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    published_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        if self.severity not in {"info", "warn", "critical"}:
            raise ValueError(f"DriftAlertSpec.severity invalid: {self.severity}")
        if not self.headline:
            raise ValueError("DriftAlertSpec.headline required")
        if len(self.headline) > 255:
            raise ValueError("DriftAlertSpec.headline must be <=255 chars")

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "category": self.category,
            "current_date": self.current_date.isoformat(),
            "baseline_start": self.baseline_start.isoformat(),
            "baseline_end": self.baseline_end.isoformat(),
            "pass_rate_current": self.pass_rate_current,
            "pass_rate_baseline": self.pass_rate_baseline,
            "judge_z": self.judge_z,
            "embedding_z": self.embedding_z,
            "delta_pp": self.delta_pp,
            "severity": self.severity,
            "headline": self.headline,
            "is_candidate": self.is_candidate,
            "evidence": dict(self.evidence),
            "published_at": self.published_at.isoformat(),
        }

    def evidence_json(self) -> str:
        """Serialize evidence dict to a JSON string (DB column format)."""
        return json.dumps(self.evidence, sort_keys=True, separators=(",", ":"))
