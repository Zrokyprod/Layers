"""
3-tier diff cascade for regression-CI.

Replaces the buggy Jaccard-char-set metric in `zroky-replay-worker/app/runner.py`
(bug B2). For each (baseline_output, candidate_output) pair we run:

  Tier 1 — Token-set Jaccard.  Always. ~0 cost. Decides obvious cases:
                identical strings → PASS, totally disjoint → FAIL.
                Token-level (not char-level) so word-order changes
                still register similarity.

  Tier 2 — Embedding cosine.   Always (when Tier 1 inconclusive).
                Uses `app.services.embedding_service.EmbeddingService`
                (text-embedding-3-small, 1536 dims). $0.0001/pair.

  Tier 3 — LLM judge.          Only when cosine ∈ (low_judge_band,
                high_judge_band) — i.e. ambiguous similarity.
                Uses `app.services.judge_engine.get_evaluator(...)`.
                $0.001/pair. Final arbiter.

Design rationale:
  - Pure-functional `score()` — accepts injected embedder + evaluator.
    Tests pass deterministic stubs. Production wires the real ones.
  - Verdict thresholds are NAMED CONSTANTS, not magic numbers.
    Tunable, but document any change in the commit message — these
    drive customer-facing pass/fail outcomes.
  - Cost is auditable: `judge_used` flag lets the orchestrator total
    Tier-3 invocations and surface them in the report.
  - Error path: if any tier fails (embedding API down, judge error),
    we degrade gracefully to the previous tier's verdict (don't crash
    the whole run).

Locked thresholds (do not casually edit; calibrate via judge_calibration):
  COSINE_PASS_THRESHOLD       = 0.95
  COSINE_FAIL_THRESHOLD       = 0.70
  JACCARD_PASS_FAST_THRESHOLD = 0.95   (Tier 1 short-circuit on near-identical)
  JACCARD_FAIL_FAST_THRESHOLD = 0.05   (Tier 1 short-circuit on near-disjoint)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from app.services.regression_ci.models import DiffScore, DiffVerdict

logger = logging.getLogger(__name__)


# ── locked thresholds ──────────────────────────────────────────────────────

COSINE_PASS_THRESHOLD: float = 0.95
COSINE_FAIL_THRESHOLD: float = 0.70

JACCARD_PASS_FAST_THRESHOLD: float = 0.95
JACCARD_FAIL_FAST_THRESHOLD: float = 0.05


# ── Tier 1: token-set Jaccard ───────────────────────────────────────────────

# Tokenizer chosen for stability across LLM outputs:
#   - lowercase
#   - split on non-alphanum runs (preserves numbers as tokens)
#   - drop tokens length < 2 (eliminates a/I/. noise that inflates Jaccard)
_TOKEN_RE = re.compile(r"[A-Za-z0-9]{2,}")


def tokenize(text: str) -> set[str]:
    """Return a token set for Jaccard. Idempotent. Handles None safely."""
    if not text:
        return set()
    return {tok.lower() for tok in _TOKEN_RE.findall(text)}


def jaccard(a: str, b: str) -> float:
    """Token-set Jaccard similarity in [0.0, 1.0]. 1.0 == identical token bag."""
    set_a = tokenize(a)
    set_b = tokenize(b)
    if not set_a and not set_b:
        return 1.0  # both empty → semantically identical
    if not set_a or not set_b:
        return 0.0  # one empty, other not → maximally different
    inter = set_a & set_b
    union = set_a | set_b
    return len(inter) / len(union)


# ── Tier 2: embedding cosine ────────────────────────────────────────────────


class Embedder(Protocol):
    """Minimal embedding interface — our prod EmbeddingService satisfies it."""

    def generate_embedding(self, text: str) -> list[float] | None: ...


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Cosine similarity between two vectors. Returns value in [0.0, 1.0].

    The raw cosine is in [-1, 1]; for embeddings of natural-language
    outputs negative cosines are extremely rare, so we clamp to [0, 1]
    to stay aligned with the verdict threshold semantics.
    """
    if not vec_a or not vec_b:
        return 0.0
    if len(vec_a) != len(vec_b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(vec_a, vec_b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    raw = dot / ((norm_a ** 0.5) * (norm_b ** 0.5))
    if raw < 0.0:
        return 0.0
    if raw > 1.0:
        return 1.0
    return raw


# ── Tier 3: judge ───────────────────────────────────────────────────────────


class JudgeEvaluator(Protocol):
    """Subset of `judge_engine.Evaluator` interface we depend on."""

    def evaluate(
        self,
        actual: str,
        expected: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Any: ...  # returns judge_engine.Verdict


# ── public API ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScoreInputs:
    """Per-trace inputs to `score()`. Bundled to keep the call site clean.

    `prompt_context` is optional — judge benefits from knowing what
    question produced these two outputs, but we don't always have it
    (e.g. when running on legacy traces that don't store the full prompt).
    """

    baseline_output: str
    candidate_output: str
    prompt_context: str | None = None


def score(
    inputs: ScoreInputs,
    *,
    embedder: Embedder | None = None,
    judge: JudgeEvaluator | None = None,
) -> DiffScore:
    """Run the 3-tier cascade and return a DiffScore.

    Behavior:
      - Tier 1 (Jaccard) always runs.
      - Tier 1 short-circuits if jaccard >= JACCARD_PASS_FAST_THRESHOLD
        (verdict PASS) or jaccard <= JACCARD_FAIL_FAST_THRESHOLD
        (verdict FAIL).
      - Tier 2 (cosine) runs when an embedder is provided AND Tier 1
        didn't short-circuit. If embedder fails, we keep Tier 1's
        jaccard as the primary signal and return INCONCLUSIVE.
      - Tier 3 (judge) runs when a judge is provided AND cosine landed
        in the borderline band [COSINE_FAIL_THRESHOLD, COSINE_PASS_THRESHOLD].

    `embedder=None` and `judge=None` are valid (e.g. for tests, free-tier
    customers without API keys, or graceful degradation). The cascade
    just stops at whichever tier has a decisive verdict.
    """
    j = jaccard(inputs.baseline_output, inputs.candidate_output)

    # Tier 1 short-circuits.
    if j >= JACCARD_PASS_FAST_THRESHOLD:
        return DiffScore(
            verdict=DiffVerdict.PASS,
            jaccard=j,
            cosine=None,
            judge_used=False,
            reason="tier1:near_identical",
        )
    if j <= JACCARD_FAIL_FAST_THRESHOLD:
        return DiffScore(
            verdict=DiffVerdict.FAIL,
            jaccard=j,
            cosine=None,
            judge_used=False,
            reason="tier1:near_disjoint",
        )

    # Tier 2: embedding cosine.
    cos: float | None = None
    if embedder is not None:
        try:
            vec_a = embedder.generate_embedding(inputs.baseline_output)
            vec_b = embedder.generate_embedding(inputs.candidate_output)
            if vec_a and vec_b:
                cos = cosine_similarity(vec_a, vec_b)
        except Exception as exc:
            logger.warning("regression_ci.diff_metric embedder failed: %s", exc)
            cos = None

    if cos is None:
        # No embedding available → fall back to Jaccard with INCONCLUSIVE
        # verdict so the orchestrator surfaces it (don't silently pass).
        return DiffScore(
            verdict=DiffVerdict.INCONCLUSIVE,
            jaccard=j,
            cosine=None,
            judge_used=False,
            reason="tier2:embedder_unavailable",
        )

    if cos >= COSINE_PASS_THRESHOLD:
        return DiffScore(
            verdict=DiffVerdict.PASS,
            jaccard=j,
            cosine=cos,
            judge_used=False,
            reason="tier2:cosine_above_pass",
        )
    if cos < COSINE_FAIL_THRESHOLD:
        return DiffScore(
            verdict=DiffVerdict.FAIL,
            jaccard=j,
            cosine=cos,
            judge_used=False,
            reason="tier2:cosine_below_fail",
        )

    # Tier 3: judge for borderline cases.
    if judge is None:
        # No judge available — we have a borderline cosine but can't escalate.
        # Be honest and return INCONCLUSIVE.
        return DiffScore(
            verdict=DiffVerdict.INCONCLUSIVE,
            jaccard=j,
            cosine=cos,
            judge_used=False,
            reason="tier3:judge_unavailable",
        )

    try:
        verdict_obj = judge.evaluate(
            actual=inputs.candidate_output,
            expected=inputs.baseline_output,
            context={
                "prompt_context": inputs.prompt_context or "",
                "purpose": "regression_ci_diff",
                "tier1_jaccard": round(j, 4),
                "tier2_cosine": round(cos, 4),
            },
        )
    except Exception as exc:
        logger.warning("regression_ci.diff_metric judge failed: %s", exc)
        return DiffScore(
            verdict=DiffVerdict.INCONCLUSIVE,
            jaccard=j,
            cosine=cos,
            judge_used=True,
            reason="tier3:judge_error",
        )

    judge_verdict = getattr(verdict_obj, "verdict", None)
    judge_conf = getattr(verdict_obj, "confidence", None)

    if judge_verdict == "pass":
        mapped = DiffVerdict.PASS
        reason = "tier3:judge_pass"
    elif judge_verdict == "fail":
        mapped = DiffVerdict.FAIL
        reason = "tier3:judge_fail"
    else:
        mapped = DiffVerdict.INCONCLUSIVE
        reason = "tier3:judge_inconclusive"

    return DiffScore(
        verdict=mapped,
        jaccard=j,
        cosine=cos,
        judge_used=True,
        judge_confidence=float(judge_conf) if isinstance(judge_conf, (int, float)) else None,
        reason=reason,
    )
