"""Tests for `app/services/judge_calibration_metrics.py`.

Coverage:
  - _normalize_verdict: canonical mapping + unknown bucket
  - build_confusion_matrix: shape, counts, zero matrix, defensive
  - accuracy / matrix_total / diagonal_total
  - per_class_metrics: precision / recall / F1 / support
  - cohens_kappa: perfect, single-class, below-chance, empty
  - low_confidence_pct: percentage below threshold
  - compute_all: end-to-end derivation
"""
from __future__ import annotations

import pytest

from app.services.judge_calibration_metrics import (
    VERDICT_CLASSES,
    _normalize_verdict,
    accuracy,
    build_confusion_matrix,
    cohens_kappa,
    compute_all,
    diagonal_total,
    low_confidence_pct,
    matrix_total,
    per_class_metrics,
)


# ── verdict normalization ─────────────────────────────────────────────────────


class TestNormalizeVerdict:
    def test_canonical_passthrough(self) -> None:
        assert _normalize_verdict("pass") == "pass"
        assert _normalize_verdict("fail") == "fail"
        assert _normalize_verdict("inconclusive") == "inconclusive"

    def test_case_and_whitespace(self) -> None:
        assert _normalize_verdict("  PASS ") == "pass"
        assert _normalize_verdict("Fail") == "fail"

    def test_unknown_bucketed(self) -> None:
        assert _normalize_verdict("banana") == "inconclusive"
        assert _normalize_verdict("") == "inconclusive"
        assert _normalize_verdict(None) == "inconclusive"  # type: ignore[arg-type]


# ── confusion matrix ──────────────────────────────────────────────────────────


def _pairs(judge: list[str], truth: list[str]) -> list[tuple[str, str]]:
    return list(zip(judge, truth))


class TestBuildConfusionMatrix:
    def test_shape_always_3x3(self) -> None:
        m = build_confusion_matrix([])
        assert set(m.keys()) == set(VERDICT_CLASSES)
        for row in m.values():
            assert set(row.keys()) == set(VERDICT_CLASSES)
        assert all(c == 0 for row in m.values() for c in row.values())

    def test_perfect_agreement(self) -> None:
        m = build_confusion_matrix(_pairs(["pass", "fail", "pass"], ["pass", "fail", "pass"]))
        assert m["pass"]["pass"] == 2
        assert m["fail"]["fail"] == 1
        assert matrix_total(m) == 3

    def test_mixed(self) -> None:
        # judge=pass,fail,fail,pass  truth=pass,pass,fail,fail
        m = build_confusion_matrix(
            _pairs(["pass", "fail", "fail", "pass"], ["pass", "pass", "fail", "fail"])
        )
        assert m["pass"]["pass"] == 1
        assert m["fail"]["pass"] == 1
        assert m["fail"]["fail"] == 1
        assert m["pass"]["fail"] == 1

    def test_unknown_routed_to_inconclusive(self) -> None:
        m = build_confusion_matrix([("banana", "fail"), ("pass", "weird")])
        assert m["inconclusive"]["fail"] == 1
        assert m["pass"]["inconclusive"] == 1


# ── accuracy ──────────────────────────────────────────────────────────────────


class TestAccuracy:
    def test_perfect(self) -> None:
        m = build_confusion_matrix(_pairs(["pass", "fail"], ["pass", "fail"]))
        assert accuracy(m) == 1.0

    def test_zero(self) -> None:
        m = build_confusion_matrix(_pairs(["pass", "pass"], ["fail", "fail"]))
        assert accuracy(m) == 0.0

    def test_50_percent(self) -> None:
        m = build_confusion_matrix(_pairs(["pass", "pass"], ["pass", "fail"]))
        assert accuracy(m) == 0.5

    def test_empty(self) -> None:
        assert accuracy(build_confusion_matrix([])) == 0.0

    def test_diagonal_helpers(self) -> None:
        m = build_confusion_matrix(_pairs(["pass", "pass", "fail"], ["pass", "fail", "fail"]))
        assert matrix_total(m) == 3
        assert diagonal_total(m) == 2


# ── per-class metrics ────────────────────────────────────────────────────────


class TestPerClassMetrics:
    def test_perfect(self) -> None:
        m = build_confusion_matrix(_pairs(["pass", "fail", "pass"], ["pass", "fail", "pass"]))
        out = per_class_metrics(m)
        for cm in out:
            if cm.support == 0 and cm.predicted == 0:
                continue
            assert cm.precision == 1.0
            assert cm.recall == 1.0
            assert cm.f1 == 1.0

    def test_precision_recall_balance(self) -> None:
        # truth all pass; judge predicts pass,pass,fail
        m = build_confusion_matrix(_pairs(["pass", "pass", "fail"], ["pass", "pass", "pass"]))
        by_v = {cm.verdict: cm for cm in per_class_metrics(m)}
        # pass: TP=2 (judge=pass, truth=pass), FP=0, FN=1 (judge=fail, truth=pass)
        assert by_v["pass"].true_positive == 2
        assert by_v["pass"].false_positive == 0
        assert by_v["pass"].false_negative == 1
        assert by_v["pass"].precision == 1.0
        assert pytest.approx(by_v["pass"].recall, rel=1e-3) == 2 / 3
        assert pytest.approx(by_v["pass"].f1, rel=1e-3) == 4 / 5

    def test_returns_one_per_class(self) -> None:
        m = build_confusion_matrix([])
        out = per_class_metrics(m)
        assert len(out) == len(VERDICT_CLASSES)
        assert {cm.verdict for cm in out} == set(VERDICT_CLASSES)

    def test_to_dict_contains_support(self) -> None:
        m = build_confusion_matrix(_pairs(["pass"], ["pass"]))
        for cm in per_class_metrics(m):
            d = cm.to_dict()
            assert "support" in d
            assert "precision" in d
            assert "recall" in d
            assert "f1" in d


# ── cohen's kappa ────────────────────────────────────────────────────────────


class TestCohensKappa:
    def test_perfect_agreement(self) -> None:
        m = build_confusion_matrix(_pairs(["pass", "fail", "pass", "fail"], ["pass", "fail", "pass", "fail"]))
        assert cohens_kappa(m) == 1.0

    def test_empty(self) -> None:
        assert cohens_kappa(build_confusion_matrix([])) == 0.0

    def test_single_class_returns_zero(self) -> None:
        # everything pass → pe == 1 → guard returns 0.0
        m = build_confusion_matrix(_pairs(["pass", "pass", "pass"], ["pass", "pass", "pass"]))
        assert cohens_kappa(m) == 0.0

    def test_below_zero(self) -> None:
        # complete inversion: judge always wrong on a balanced set
        m = build_confusion_matrix(_pairs(["fail", "fail", "pass", "pass"], ["pass", "pass", "fail", "fail"]))
        assert cohens_kappa(m) == pytest.approx(-1.0, abs=1e-9)


# ── low confidence percentage ────────────────────────────────────────────────


class TestLowConfidencePct:
    def test_none_below(self) -> None:
        assert low_confidence_pct([0.9, 0.85, 0.92], threshold=0.8) == 0.0

    def test_all_below(self) -> None:
        assert low_confidence_pct([0.3, 0.5], threshold=0.8) == 1.0

    def test_mixed(self) -> None:
        assert low_confidence_pct([0.9, 0.7, 0.6], threshold=0.8) == pytest.approx(2 / 3)

    def test_empty(self) -> None:
        assert low_confidence_pct([], threshold=0.8) == 0.0

    def test_clamps_out_of_range(self) -> None:
        # -0.5 clamped to 0.0 (below); 1.5 clamped to 1.0 (above)
        assert low_confidence_pct([-0.5, 1.5], threshold=0.5) == 0.5

    def test_skips_non_numeric(self) -> None:
        assert low_confidence_pct([0.1, "bad", None, 0.9], threshold=0.5) == 0.5  # type: ignore[list-item]


# ── compute_all end-to-end ──────────────────────────────────────────────────


class TestComputeAll:
    def test_returns_metrics_and_low_conf(self) -> None:
        pairs = _pairs(["pass", "fail", "pass"], ["pass", "fail", "fail"])
        metrics, low = compute_all(pairs, [0.9, 0.4, 0.95])
        assert metrics.sample_count == 3
        assert metrics.agreement_count == 2
        assert metrics.accuracy == pytest.approx(2 / 3)
        assert low == pytest.approx(1 / 3)
