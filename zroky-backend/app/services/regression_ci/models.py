"""
Frozen data shapes for the regression-CI pipeline.

Design notes:
  - Every dataclass is `frozen=True` and JSON-serializable via `to_dict()`.
    Frozen-ness eliminates a class of bugs where a downstream stage
    mutates an upstream artifact and we lose audit-ability.
  - `SCHEMA_VERSION` is bumped only on breaking changes to
    `RegressionCIReport`. Additive fields keep the version. Customer
    parsers (the GitHub Action) pin on this version.
  - No DB coupling. These dataclasses are produced and consumed by
    pure-functional code; the orchestrator persists them to
    ReplayRun.summary_json as a serialized dict.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

# Bump on BREAKING changes only. Adding fields = same version.
SCHEMA_VERSION: str = "v1"


# ── Blast radius ────────────────────────────────────────────────────────────


class BlastRadiusCategory:
    """Canonical categories. Locked set — adding a category is a breaking change.

    Six categories cover ~95% of real PR shapes. Anything we can't classify
    falls back to UNKNOWN with a conservative sample size.
    """

    SYSTEM_PROMPT = "system_prompt"
    MODEL_SWAP = "model_swap"
    MODEL_PARAMS = "model_params"
    RETRIEVAL_CONFIG = "retrieval_config"
    TOOL_DEFINITION = "tool_definition"
    TOOL_PROMPT = "tool_prompt"
    UNKNOWN = "unknown"


class BlastRadiusSource:
    """How was the blast radius determined.

    `DECLARED` always wins over `AUTO_DETECTED` when both are present —
    customer intent beats heuristic. `OVERRIDE` is for manual operator
    re-runs from the dashboard.
    """

    DECLARED = "declared"           # parsed from .zroky.yml or PR body
    AUTO_DETECTED = "auto_detected"  # heuristic from changed files/hunks
    OVERRIDE = "override"            # operator-set in dashboard


VALID_CATEGORIES: frozenset[str] = frozenset({
    BlastRadiusCategory.SYSTEM_PROMPT,
    BlastRadiusCategory.MODEL_SWAP,
    BlastRadiusCategory.MODEL_PARAMS,
    BlastRadiusCategory.RETRIEVAL_CONFIG,
    BlastRadiusCategory.TOOL_DEFINITION,
    BlastRadiusCategory.TOOL_PROMPT,
    BlastRadiusCategory.UNKNOWN,
})

VALID_SOURCES: frozenset[str] = frozenset({
    BlastRadiusSource.DECLARED,
    BlastRadiusSource.AUTO_DETECTED,
    BlastRadiusSource.OVERRIDE,
})

# Default sample size per category. Tunable per-project via SampleSpec
# overrides; these are the floors used when no override is supplied.
# Locked rationale (do not casually edit):
#   SYSTEM_PROMPT / MODEL_SWAP — both touch every call. Need broad coverage.
#   MODEL_PARAMS / RETRIEVAL_CONFIG — affect distribution shape; mid sample.
#   TOOL_DEFINITION — affects only tool-using calls; small sample OK.
#   TOOL_PROMPT — narrowest scope; tiny sample sufficient.
#   UNKNOWN — middle ground; we can't reason, be conservative.
DEFAULT_SAMPLE_SIZES: Mapping[str, int] = {
    BlastRadiusCategory.SYSTEM_PROMPT: 5000,
    BlastRadiusCategory.MODEL_SWAP: 5000,
    BlastRadiusCategory.MODEL_PARAMS: 2000,
    BlastRadiusCategory.RETRIEVAL_CONFIG: 2000,
    BlastRadiusCategory.TOOL_DEFINITION: 500,
    BlastRadiusCategory.TOOL_PROMPT: 200,
    BlastRadiusCategory.UNKNOWN: 1000,
}


@dataclass(frozen=True)
class BlastRadius:
    """The classification of what a PR touches.

    Attributes
    ----------
    category
        One of `BlastRadiusCategory.*`.
    source
        One of `BlastRadiusSource.*` — provenance of the classification.
    files
        Subset of changed files that drove the classification. Used for
        the PR comment evidence section. Empty when source=OVERRIDE.
    target
        Optional sub-scope identifier (e.g. tool name for TOOL_PROMPT).
        None for category-wide changes.
    confidence
        Float in [0.0, 1.0]. Always 1.0 for DECLARED/OVERRIDE; varies
        for AUTO_DETECTED.
    """

    category: str
    source: str
    files: tuple[str, ...] = field(default_factory=tuple)
    target: str | None = None
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.category not in VALID_CATEGORIES:
            raise ValueError(f"invalid blast radius category: {self.category!r}")
        if self.source not in VALID_SOURCES:
            raise ValueError(f"invalid blast radius source: {self.source!r}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "source": self.source,
            "files": list(self.files),
            "target": self.target,
            "confidence": round(self.confidence, 4),
        }


# ── Sampling ────────────────────────────────────────────────────────────────


class SampleStratum:
    """Stratification labels for the sampler.

    The four-stratum mix is the single most important choice in this
    pipeline. Random sampling misses long-tail regressions; this mix
    guarantees we hit known-pass, known-fail, rare, and recent traces.
    """

    PASS_HISTORY = "pass_history"
    FAIL_HISTORY = "fail_history"
    RARE_CLUSTER = "rare_cluster"
    RECENT_24H = "recent_24h"


# Default mix (must sum to 1.0). Override per-project via SampleSpec.
DEFAULT_STRATIFICATION: Mapping[str, float] = {
    SampleStratum.PASS_HISTORY: 0.50,
    SampleStratum.FAIL_HISTORY: 0.30,
    SampleStratum.RARE_CLUSTER: 0.10,
    SampleStratum.RECENT_24H: 0.10,
}


@dataclass(frozen=True)
class StratificationCounts:
    """Realised counts per stratum after sampling.

    `realised_total` may be < target_total when the project has
    insufficient history (e.g. brand-new project with no fail_history).
    The orchestrator does NOT pad with random samples — under-sampling
    is honest, padding is dishonest.
    """

    pass_history: int = 0
    fail_history: int = 0
    rare_cluster: int = 0
    recent_24h: int = 0

    @property
    def realised_total(self) -> int:
        return self.pass_history + self.fail_history + self.rare_cluster + self.recent_24h

    def to_dict(self) -> dict[str, int]:
        return {
            "pass_history": self.pass_history,
            "fail_history": self.fail_history,
            "rare_cluster": self.rare_cluster,
            "recent_24h": self.recent_24h,
            "realised_total": self.realised_total,
        }


@dataclass(frozen=True)
class SampleSpec:
    """Plan for which traces to replay, derived from BlastRadius.

    Built by `sampler.build_spec(blast_radius, project_overrides=...)`.
    Consumed by `sampler.sample(spec, db_session)` which returns
    a list of trace IDs.
    """

    target_total: int
    stratification: Mapping[str, float]  # stratum → fraction (sums to 1.0)
    blast_radius: BlastRadius

    def __post_init__(self) -> None:
        if self.target_total <= 0:
            raise ValueError(f"target_total must be > 0, got {self.target_total}")
        s = sum(self.stratification.values())
        if not 0.99 <= s <= 1.01:  # allow float fuzz
            raise ValueError(f"stratification must sum to 1.0, got {s}")
        for k in self.stratification:
            if k not in {
                SampleStratum.PASS_HISTORY,
                SampleStratum.FAIL_HISTORY,
                SampleStratum.RARE_CLUSTER,
                SampleStratum.RECENT_24H,
            }:
                raise ValueError(f"unknown stratum: {k!r}")

    def per_stratum_target(self) -> dict[str, int]:
        """Integer target count per stratum, rounded down. Caller should
        accept that sum(targets) <= target_total due to flooring."""
        return {
            stratum: int(self.target_total * fraction)
            for stratum, fraction in self.stratification.items()
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_total": self.target_total,
            "stratification": dict(self.stratification),
            "per_stratum_target": self.per_stratum_target(),
            "blast_radius": self.blast_radius.to_dict(),
        }


# ── Diff scoring ────────────────────────────────────────────────────────────


class DiffVerdict:
    """Per-trace verdict produced by diff_metric.score()."""

    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"


VALID_VERDICTS: frozenset[str] = frozenset({
    DiffVerdict.PASS,
    DiffVerdict.FAIL,
    DiffVerdict.INCONCLUSIVE,
    DiffVerdict.ERROR,
})


@dataclass(frozen=True)
class DiffScore:
    """Output of the 3-tier diff cascade.

    Attributes
    ----------
    verdict
        One of `DiffVerdict.*`.
    cosine
        Embedding cosine similarity in [0.0, 1.0]. None when Tier 2 was
        skipped (Tier 1 already decisive) or the embedding service failed.
    jaccard
        Token-set Jaccard in [0.0, 1.0]. Always populated (Tier 1 always runs).
    judge_used
        True when Tier 3 (LLM judge) was invoked. Used for cost auditing
        and to surface "judge load" in the report.
    judge_confidence
        Self-reported judge confidence when judge_used=True. None otherwise.
    reason
        Short string identifying which tier produced the verdict, e.g.
        "tier1:identical", "tier2:cosine_below_threshold", "tier3:judge_fail".
        Used by the dashboard's per-trace inspector.
    """

    verdict: str
    jaccard: float
    cosine: float | None = None
    judge_used: bool = False
    judge_confidence: float | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in VALID_VERDICTS:
            raise ValueError(f"invalid verdict: {self.verdict!r}")
        if not 0.0 <= self.jaccard <= 1.0:
            raise ValueError(f"jaccard must be in [0,1], got {self.jaccard}")
        if self.cosine is not None and not 0.0 <= self.cosine <= 1.0:
            raise ValueError(f"cosine must be in [0,1] or None, got {self.cosine}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "jaccard": round(self.jaccard, 4),
            "cosine": round(self.cosine, 4) if self.cosine is not None else None,
            "judge_used": self.judge_used,
            "judge_confidence": (
                round(self.judge_confidence, 4)
                if self.judge_confidence is not None else None
            ),
            "reason": self.reason,
        }


# ── Per-trace and run-level result ──────────────────────────────────────────


@dataclass(frozen=True)
class TraceResult:
    """One row in the regression-CI run.

    Attributes
    ----------
    trace_id
        Source Call.id that we replayed.
    stratum
        Which sampler stratum produced this trace.
    baseline_output
        Original recorded output (truncated to ~2 KB for storage).
    candidate_output
        Re-execution output under the PR's prompt/model (truncated).
    diff_score
        Output of `diff_metric.score()`.
    cost_usd
        Real-LLM cost incurred for this single re-execution. 0.0 in
        stub mode. Aggregated upward into `RegressionCIReport.cost_usd`.
    latency_ms
        Wall-clock for this re-execution. Useful for capacity planning.
    error_message
        Populated only when verdict=ERROR (network / timeout / provider 5xx).
    """

    trace_id: str
    stratum: str
    baseline_output: str
    candidate_output: str
    diff_score: DiffScore
    cost_usd: float = 0.0
    latency_ms: int = 0
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "stratum": self.stratum,
            "baseline_output": self.baseline_output,
            "candidate_output": self.candidate_output,
            "diff_score": self.diff_score.to_dict(),
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class RegressionCluster:
    """A cluster of regressed traces sharing semantic intent.

    Produced by `cluster.cluster_regressions()`. Capped at top-5 in
    the PR comment to keep the report skimmable.
    """

    label: str           # human-readable, e.g. "refund_policy_de"
    keywords: tuple[str, ...]  # top-3 TF-IDF terms
    size: int            # number of regressed traces in cluster
    sample_trace_id: str  # one representative trace
    sample_input: str    # truncated input for the comment

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "keywords": list(self.keywords),
            "size": self.size,
            "sample_trace_id": self.sample_trace_id,
            "sample_input": self.sample_input,
        }


@dataclass(frozen=True)
class RegressionCIReport:
    """The frozen output schema returned to the GitHub Action.

    THIS IS A PUBLIC API CONTRACT. Adding fields = same SCHEMA_VERSION.
    Renaming, removing, or changing a field's type = bump SCHEMA_VERSION.

    Attributes
    ----------
    schema_version
        Pinned to module-level `SCHEMA_VERSION`. Customer parsers branch
        on this.
    run_id
        ReplayRun.id — joins to dashboard for full per-trace inspection.
    project_id
        For multi-tenant safety; the GitHub Action verifies this matches
        its configured project before parsing the rest.
    git_sha
        Commit SHA that was replayed. Echoed back for audit.
    blast_radius
        Resolved BlastRadius (declared / auto-detected).
    sample_spec
        The plan used by the sampler.
    stratification_realised
        Actual counts achieved per stratum (may underflow target).
    trace_count
        Total traces replayed (= stratification_realised.realised_total).
    regressed_count
        Traces with diff_score.verdict == FAIL.
    regression_rate
        regressed_count / trace_count, rounded to 4 places. 0.0 when
        trace_count == 0 (defensive).
    threshold
        Customer-configured pass/fail threshold for regression_rate.
    verdict
        "pass" iff regression_rate <= threshold AND error_rate < 0.05.
        "fail" otherwise.
    error_count
        Traces with diff_score.verdict == ERROR (network / provider).
    error_rate
        error_count / trace_count.
    judge_used_count
        How many traces escalated to Tier 3 judge. For cost transparency.
    cost_usd
        Total real-LLM spend for this run, including embeddings + judge.
    duration_seconds
        Wall-clock end-to-end (sampler+replay+score+cluster). Excludes
        queue wait.
    clusters
        Top-5 regression clusters (may be fewer if <5 found).
    judge_calibration
        Optional snapshot of the judge's recent accuracy on this project's
        golden labels. None when no calibration data exists.
    notes
        Operator-readable notes (e.g. "stub mode active",
        "sample under-filled: insufficient fail_history"). Surfaced in
        the PR comment.
    """

    schema_version: str
    run_id: str
    project_id: str
    git_sha: str | None
    blast_radius: BlastRadius
    sample_spec: SampleSpec
    stratification_realised: StratificationCounts
    trace_count: int
    regressed_count: int
    regression_rate: float
    threshold: float
    verdict: str
    error_count: int = 0
    error_rate: float = 0.0
    judge_used_count: int = 0
    cost_usd: float = 0.0
    duration_seconds: int = 0
    clusters: tuple[RegressionCluster, ...] = field(default_factory=tuple)
    judge_calibration: Mapping[str, Any] | None = None
    # Wedge 4 — Cost-of-failure attribution snapshot. Optional because
    # projects with no outcome events should not see a misleading "$0"
    # tag on every PR. Populated by the orchestrator from
    # `outcome_attribution.compute_pr_savings()` when project has any
    # OutcomeEvent rows in the last 30 days. Shape:
    #   {
    #     "outcome_cost_30d_usd": 11840.0,   # actual past 30d outcome cost
    #     "failed_call_count_30d": 247,      # past failed calls in 30d
    #     "regressed_in_pr": 12,             # this run's regressed_count
    #     "estimated_monthly_risk_usd": 290.4,  # PR risk if merged as-is
    #     "method": "linear_extrapolation",  # so a UI can show provenance
    #   }
    outcome_attribution: Mapping[str, Any] | None = None
    failed_goldens: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    warn_goldens: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    not_verified_reasons: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.verdict not in {"pass", "warn", "fail", "not_verified", "error"}:
            raise ValueError(f"invalid run verdict: {self.verdict!r}")
        if not 0.0 <= self.regression_rate <= 1.0:
            raise ValueError(f"regression_rate out of range: {self.regression_rate}")
        if not 0.0 <= self.error_rate <= 1.0:
            raise ValueError(f"error_rate out of range: {self.error_rate}")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(f"threshold out of range: {self.threshold}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "git_sha": self.git_sha,
            "blast_radius": self.blast_radius.to_dict(),
            "sample_spec": self.sample_spec.to_dict(),
            "stratification_realised": self.stratification_realised.to_dict(),
            "trace_count": self.trace_count,
            "regressed_count": self.regressed_count,
            "regression_rate": round(self.regression_rate, 4),
            "threshold": round(self.threshold, 4),
            "verdict": self.verdict,
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 4),
            "judge_used_count": self.judge_used_count,
            "cost_usd": round(self.cost_usd, 4),
            "duration_seconds": self.duration_seconds,
            "clusters": [c.to_dict() for c in self.clusters],
            "judge_calibration": (
                dict(self.judge_calibration) if self.judge_calibration else None
            ),
            "outcome_attribution": (
                dict(self.outcome_attribution) if self.outcome_attribution else None
            ),
            "failed_goldens": [dict(item) for item in self.failed_goldens],
            "warn_goldens": [dict(item) for item in self.warn_goldens],
            "not_verified_reasons": list(self.not_verified_reasons),
            "notes": list(self.notes),
        }
