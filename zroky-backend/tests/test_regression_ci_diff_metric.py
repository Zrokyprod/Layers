"""Tests for `app.services.regression_ci.diff_metric`.

Coverage:
  - Tier 1 (Jaccard): identical, disjoint, partial, empty edge cases.
  - Tier 1 short-circuits: near-identical → PASS, near-disjoint → FAIL.
  - Tier 2 (cosine): pass-band, fail-band, borderline pass-through.
  - Tier 3 (judge): pass / fail / inconclusive / error mapping.
  - Graceful degradation: embedder failure, judge failure, no embedder/judge.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pytest

from app.services.regression_ci.diff_metric import (
    COSINE_FAIL_THRESHOLD,
    COSINE_PASS_THRESHOLD,
    JACCARD_FAIL_FAST_THRESHOLD,
    JACCARD_PASS_FAST_THRESHOLD,
    ScoreInputs,
    cosine_similarity,
    jaccard,
    score,
    tokenize,
)
from app.services.regression_ci.models import DiffVerdict


# ── tokenize / jaccard ──────────────────────────────────────────────────────


class TestTokenize:
    def test_lowercase(self) -> None:
        assert tokenize("Hello World") == {"hello", "world"}

    def test_drops_short_tokens(self) -> None:
        # Single-letter tokens (a, I) are excluded — they bias Jaccard.
        toks = tokenize("a I am running")
        assert "a" not in toks
        assert "i" not in toks
        assert "am" in toks
        assert "running" in toks

    def test_handles_none(self) -> None:
        assert tokenize("") == set()

    def test_preserves_numbers(self) -> None:
        toks = tokenize("ticket 12345 resolved in 30 minutes")
        assert "12345" in toks
        assert "30" in toks


class TestJaccard:
    def test_identical_strings(self) -> None:
        assert jaccard("hello world", "hello world") == 1.0

    def test_completely_disjoint(self) -> None:
        assert jaccard("apple banana", "carrot daikon") == 0.0

    def test_partial_overlap(self) -> None:
        # tokens A: {hello, world, refund}, B: {hello, world, payment}
        # intersection = {hello, world} = 2;  union = 4 → 0.5
        assert jaccard("hello world refund", "hello world payment") == 0.5

    def test_both_empty(self) -> None:
        assert jaccard("", "") == 1.0  # both empty == identical (defensive)

    def test_one_empty(self) -> None:
        assert jaccard("anything", "") == 0.0

    def test_word_order_invariant(self) -> None:
        # token-set Jaccard is order-independent
        assert jaccard("the quick fox", "fox quick the") == 1.0


# ── cosine_similarity ───────────────────────────────────────────────────────


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_opposite_vectors_clamped_to_zero(self) -> None:
        # raw cosine = -1; we clamp to [0, 1] for verdict thresholds
        assert cosine_similarity([1.0, 2.0], [-1.0, -2.0]) == 0.0

    def test_empty_vectors(self) -> None:
        assert cosine_similarity([], [1.0]) == 0.0
        assert cosine_similarity([1.0], []) == 0.0

    def test_dimension_mismatch(self) -> None:
        # Defensive: don't crash on mismatched dims; return 0.0
        assert cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


# ── 3-tier cascade — `score()` ──────────────────────────────────────────────


@dataclass
class _StubEmbedder:
    """Returns hand-crafted vectors based on the input text. Deterministic."""

    text_to_vec: dict[str, list[float] | None]

    def generate_embedding(self, text: str) -> list[float] | None:
        return self.text_to_vec.get(text)


@dataclass
class _StubJudge:
    """Returns a configurable verdict; raises if `raise_on_evaluate=True`."""

    verdict_str: str = "pass"
    confidence: float = 0.9
    raise_on_evaluate: bool = False

    def evaluate(
        self,
        actual: str,
        expected: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Any:
        if self.raise_on_evaluate:
            raise RuntimeError("simulated judge failure")

        @dataclass
        class _V:
            verdict: str
            confidence: float
        return _V(verdict=self.verdict_str, confidence=self.confidence)


class TestTier1ShortCircuits:
    def test_identical_pass_no_embedder_call(self) -> None:
        # If Tier 1 short-circuits, embedder/judge MUST NOT be invoked.
        embedder = _StubEmbedder(text_to_vec={})  # would return None for any input
        judge = _StubJudge(raise_on_evaluate=True)
        out = score(
            ScoreInputs(baseline_output="hello world refund policy",
                        candidate_output="hello world refund policy"),
            embedder=embedder, judge=judge,
        )
        assert out.verdict == DiffVerdict.PASS
        assert out.reason == "tier1:near_identical"
        assert out.judge_used is False
        assert out.cosine is None
        assert out.jaccard >= JACCARD_PASS_FAST_THRESHOLD

    def test_disjoint_fail_no_embedder_call(self) -> None:
        embedder = _StubEmbedder(text_to_vec={})
        judge = _StubJudge(raise_on_evaluate=True)
        out = score(
            ScoreInputs(baseline_output="apple orange grapes",
                        candidate_output="carrot daikon spinach"),
            embedder=embedder, judge=judge,
        )
        assert out.verdict == DiffVerdict.FAIL
        assert out.reason == "tier1:near_disjoint"
        assert out.judge_used is False


# Test inputs designed to land in Tier 2 — they share enough tokens to
# keep Jaccard in (JACCARD_FAIL_FAST_THRESHOLD, JACCARD_PASS_FAST_THRESHOLD)
# so the cascade flows past Tier 1 short-circuits.
_TIER2_BASE = "the system processed refund request for customer 42"
_TIER2_CAND = "the system rejected refund request from customer 99"
# tokens base: {the, system, processed, refund, request, for, customer, 42}
# tokens cand: {the, system, rejected, refund, request, from, customer, 99}
# intersection = 5, union = 11  ->  Jaccard ~= 0.45  -> proceeds to Tier 2.


class TestTier2Cosine:
    def _mk_score(self, vec_a: list[float] | None, vec_b: list[float] | None,
                  judge: _StubJudge | None = None) -> Any:
        embedder = _StubEmbedder(text_to_vec={
            _TIER2_BASE: vec_a,  # type: ignore[dict-item]
            _TIER2_CAND: vec_b,  # type: ignore[dict-item]
        })
        return score(
            ScoreInputs(
                baseline_output=_TIER2_BASE,
                candidate_output=_TIER2_CAND,
            ),
            embedder=embedder,
            judge=judge,
        )

    def test_cosine_above_pass_threshold(self) -> None:
        # Both vectors very close → cosine ≈ 1.0 → PASS via tier 2
        out = self._mk_score([1.0, 0.0], [0.999, 0.001])
        assert out.verdict == DiffVerdict.PASS
        assert out.reason == "tier2:cosine_above_pass"
        assert out.cosine is not None
        assert out.cosine >= COSINE_PASS_THRESHOLD
        assert out.judge_used is False

    def test_cosine_below_fail_threshold(self) -> None:
        # Orthogonal → cosine 0.0 → FAIL via tier 2
        out = self._mk_score([1.0, 0.0], [0.0, 1.0])
        assert out.verdict == DiffVerdict.FAIL
        assert out.reason == "tier2:cosine_below_fail"
        assert out.cosine is not None
        assert out.cosine < COSINE_FAIL_THRESHOLD

    def test_embedder_returns_none_inconclusive(self) -> None:
        # Embedder unavailable → INCONCLUSIVE (don't pretend to know).
        out = self._mk_score(None, None)
        assert out.verdict == DiffVerdict.INCONCLUSIVE
        assert out.reason == "tier2:embedder_unavailable"
        assert out.cosine is None

    def test_no_embedder_provided_returns_inconclusive(self) -> None:
        # Use the shared mid-Jaccard inputs so we get past Tier 1.
        out = score(
            ScoreInputs(baseline_output=_TIER2_BASE, candidate_output=_TIER2_CAND),
            embedder=None, judge=None,
        )
        assert out.verdict == DiffVerdict.INCONCLUSIVE
        assert out.reason == "tier2:embedder_unavailable"


class TestTier3Judge:
    def _mk_borderline_inputs(self) -> tuple[ScoreInputs, _StubEmbedder]:
        # Construct vectors yielding cosine ~0.85 (borderline band).
        # Need text inputs with Jaccard in (0.05, 0.95) too so we don't
        # short-circuit at Tier 1.
        import math
        v_a = [1.0, 0.0]
        v_b = [0.85, math.sqrt(1 - 0.85 ** 2)]
        emb = _StubEmbedder(text_to_vec={_TIER2_BASE: v_a, _TIER2_CAND: v_b})
        inputs = ScoreInputs(baseline_output=_TIER2_BASE, candidate_output=_TIER2_CAND)
        return inputs, emb

    def test_judge_pass(self) -> None:
        inputs, emb = self._mk_borderline_inputs()
        judge = _StubJudge(verdict_str="pass", confidence=0.92)
        out = score(inputs, embedder=emb, judge=judge)
        assert out.verdict == DiffVerdict.PASS
        assert out.reason == "tier3:judge_pass"
        assert out.judge_used is True
        assert out.judge_confidence == 0.92

    def test_judge_fail(self) -> None:
        inputs, emb = self._mk_borderline_inputs()
        judge = _StubJudge(verdict_str="fail", confidence=0.8)
        out = score(inputs, embedder=emb, judge=judge)
        assert out.verdict == DiffVerdict.FAIL
        assert out.reason == "tier3:judge_fail"
        assert out.judge_used is True

    def test_judge_inconclusive(self) -> None:
        inputs, emb = self._mk_borderline_inputs()
        judge = _StubJudge(verdict_str="inconclusive", confidence=0.5)
        out = score(inputs, embedder=emb, judge=judge)
        assert out.verdict == DiffVerdict.INCONCLUSIVE
        assert out.reason == "tier3:judge_inconclusive"
        assert out.judge_used is True

    def test_judge_error_returns_inconclusive(self) -> None:
        inputs, emb = self._mk_borderline_inputs()
        judge = _StubJudge(raise_on_evaluate=True)
        out = score(inputs, embedder=emb, judge=judge)
        assert out.verdict == DiffVerdict.INCONCLUSIVE
        assert out.reason == "tier3:judge_error"
        assert out.judge_used is True  # we tried, mark it for cost audit

    def test_no_judge_in_borderline_returns_inconclusive(self) -> None:
        inputs, emb = self._mk_borderline_inputs()
        out = score(inputs, embedder=emb, judge=None)
        assert out.verdict == DiffVerdict.INCONCLUSIVE
        assert out.reason == "tier3:judge_unavailable"
        assert out.judge_used is False
