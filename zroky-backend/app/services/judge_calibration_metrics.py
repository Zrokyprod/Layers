"""Pure-functional metrics for judge calibration.

This module contains zero I/O, zero DB access, zero settings reads.
Every function is a pure transformation over inputs so unit tests can
exhaustively cover edge cases (empty inputs, all-agree, all-disagree,
imbalanced classes, single-class, etc.) without fixtures.

Public surface:
  - VERDICT_CLASSES: canonical verdict vocabulary (pass / fail / inconclusive).
  - build_confusion_matrix(pairs): list[(judge, truth)] -> dict[judge][truth] = count
  - accuracy(matrix): diagonal / total
  - per_class_metrics(matrix): per-verdict precision/recall/F1
  - cohens_kappa(matrix): chance-adjusted agreement
  - low_confidence_pct(confidences, threshold=0.5): fraction below threshold

Why these specific metrics:
  - Accuracy alone is misleading on imbalanced label sets (95% pass / 5%
    fail looks 95% accurate by always predicting pass).
  - Cohen's kappa subtracts expected-by-chance agreement, giving an
    honest signal even when one class dominates. Public scoreboard
    surfaces both numbers so customers see the unflattering one.
  - Per-class F1 surfaces the asymmetric cost of FP vs FN. False-fail
    rolls back a good deploy; false-pass ships a bad one. Both must be
    visible.
  - low_confidence_pct flags when the judge is hedging too often — a
    leading indicator that calibration is about to drop.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence


VERDICT_CLASSES: tuple[str, ...] = ("pass", "fail", "inconclusive")


# ── primary types ─────────────────────────────────────────────────────────


ConfusionMatrix = dict[str, dict[str, int]]
"""Nested dict keyed [judge_verdict][truth_verdict] -> count.

Always populated for every cell in VERDICT_CLASSES x VERDICT_CLASSES,
even when zero, so consumers can iterate without KeyError handling.
"""


@dataclass(frozen=True)
class ClassMetrics:
    """Per-verdict precision / recall / F1.

    A class is "positive" for one row of the confusion matrix; the rest
    is "negative". Standard binary-classification math applied per class
    and averaged in `accuracy()` (micro-avg = accuracy for multi-class).
    """

    verdict: str
    support: int  # ground-truth count for this verdict
    predicted: int  # judge predictions of this verdict
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "support": self.support,
            "predicted": self.predicted,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "f1": round(self.f1, 6),
        }


@dataclass(frozen=True)
class CalibrationMetrics:
    """Full calibration snapshot."""

    sample_count: int
    agreement_count: int
    accuracy: float
    kappa: float
    per_class: tuple[ClassMetrics, ...] = field(default_factory=tuple)
    confusion_matrix: ConfusionMatrix = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sample_count": self.sample_count,
            "agreement_count": self.agreement_count,
            "accuracy": round(self.accuracy, 6),
            "kappa": round(self.kappa, 6),
            "per_class": [m.to_dict() for m in self.per_class],
            "confusion_matrix": {
                jv: dict(tv_counts) for jv, tv_counts in self.confusion_matrix.items()
            },
        }


# ── core computations ─────────────────────────────────────────────────────


def _empty_matrix() -> ConfusionMatrix:
    return {jv: {tv: 0 for tv in VERDICT_CLASSES} for jv in VERDICT_CLASSES}


def _normalize_verdict(v: str) -> str:
    """Map any string to the canonical class set; unknowns -> 'inconclusive'.

    Defensive: judge LLMs occasionally emit 'unsure' / 'uncertain' / etc.
    Normalising here means upstream parsers don't have to.
    """
    s = (v or "").strip().lower()
    if s in VERDICT_CLASSES:
        return s
    return "inconclusive"


def build_confusion_matrix(
    pairs: Iterable[tuple[str, str]],
) -> ConfusionMatrix:
    """Build a 3x3 confusion matrix from (judge_verdict, truth_verdict) pairs.

    Empty or malformed verdicts are bucketed into 'inconclusive' so a
    single bad row never crashes a calibration run. Every cell is
    initialised to 0 so consumers can iterate freely.
    """
    matrix = _empty_matrix()
    for judge_v, truth_v in pairs:
        jv = _normalize_verdict(judge_v)
        tv = _normalize_verdict(truth_v)
        matrix[jv][tv] += 1
    return matrix


def matrix_total(matrix: ConfusionMatrix) -> int:
    return sum(c for row in matrix.values() for c in row.values())


def diagonal_total(matrix: ConfusionMatrix) -> int:
    return sum(matrix[v][v] for v in VERDICT_CLASSES if v in matrix)


def accuracy(matrix: ConfusionMatrix) -> float:
    """diagonal / total. Returns 0.0 when total == 0."""
    total = matrix_total(matrix)
    if total <= 0:
        return 0.0
    return diagonal_total(matrix) / total


def per_class_metrics(matrix: ConfusionMatrix) -> tuple[ClassMetrics, ...]:
    """Compute precision/recall/F1 for every verdict class.

    Returns one ClassMetrics per VERDICT_CLASSES entry, in canonical order.
    """
    out: list[ClassMetrics] = []
    for v in VERDICT_CLASSES:
        tp = matrix[v][v]
        # FP: judge said `v` but truth said something else.
        fp = sum(matrix[v][t] for t in VERDICT_CLASSES if t != v)
        # FN: truth was `v` but judge said something else.
        fn = sum(matrix[j][v] for j in VERDICT_CLASSES if j != v)
        support = tp + fn  # total ground-truth=v
        predicted = tp + fp  # total judge predicted v

        precision = tp / predicted if predicted > 0 else 0.0
        recall = tp / support if support > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        out.append(
            ClassMetrics(
                verdict=v,
                support=support,
                predicted=predicted,
                true_positive=tp,
                false_positive=fp,
                false_negative=fn,
                precision=precision,
                recall=recall,
                f1=f1,
            )
        )
    return tuple(out)


def cohens_kappa(matrix: ConfusionMatrix) -> float:
    """Cohen's kappa: agreement above chance.

    kappa = (po - pe) / (1 - pe)
      po = observed agreement = accuracy
      pe = expected agreement = sum_v (P(judge=v) * P(truth=v))

    Returns 0.0 when:
      - total samples == 0
      - pe == 1.0 (perfect class imbalance — division by zero)

    Range: typically -1..1. Negative kappa => worse than chance, which
    is rare but useful to surface honestly.
    """
    total = matrix_total(matrix)
    if total <= 0:
        return 0.0

    po = diagonal_total(matrix) / total

    # Marginals for chance agreement.
    pe = 0.0
    for v in VERDICT_CLASSES:
        p_judge_v = sum(matrix[v][t] for t in VERDICT_CLASSES) / total
        p_truth_v = sum(matrix[j][v] for j in VERDICT_CLASSES) / total
        pe += p_judge_v * p_truth_v

    denominator = 1.0 - pe
    if abs(denominator) < 1e-12:
        # Pure-chance baseline already perfect; observed agreement
        # provides no additional information.
        return 0.0
    return (po - pe) / denominator


def low_confidence_pct(
    confidences: Sequence[float],
    threshold: float = 0.5,
) -> float:
    """Fraction of confidences strictly below `threshold`.

    Returns 0.0 on empty input. Out-of-range values are clamped to
    [0,1] before comparison so a single malformed score doesn't throw
    off the metric.
    """
    if not confidences:
        return 0.0
    n_below = 0
    n_total = 0
    for raw in confidences:
        try:
            c = float(raw)
        except (TypeError, ValueError):
            continue
        if c < 0.0:
            c = 0.0
        elif c > 1.0:
            c = 1.0
        n_total += 1
        if c < threshold:
            n_below += 1
    if n_total == 0:
        return 0.0
    return n_below / n_total


def compute_all(
    pairs: Iterable[tuple[str, str]],
    confidences: Sequence[float] | None = None,
) -> tuple[CalibrationMetrics, float]:
    """Convenience: build matrix + compute every metric in one pass.

    Returns ``(CalibrationMetrics, low_conf_pct)``.

    Tests use this to assert the entire derivation chain matches
    expectations from a small fixture set.
    """
    pair_list = list(pairs)
    matrix = build_confusion_matrix(pair_list)
    total = matrix_total(matrix)
    diag = diagonal_total(matrix)
    metrics = CalibrationMetrics(
        sample_count=total,
        agreement_count=diag,
        accuracy=accuracy(matrix),
        kappa=cohens_kappa(matrix),
        per_class=per_class_metrics(matrix),
        confusion_matrix=matrix,
    )
    return metrics, low_confidence_pct(confidences or [])


__all__ = [
    "VERDICT_CLASSES",
    "ConfusionMatrix",
    "ClassMetrics",
    "CalibrationMetrics",
    "build_confusion_matrix",
    "matrix_total",
    "diagonal_total",
    "accuracy",
    "per_class_metrics",
    "cohens_kappa",
    "low_confidence_pct",
    "compute_all",
]
