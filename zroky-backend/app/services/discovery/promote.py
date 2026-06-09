"""Anomaly → Failure promotion + false-positive suppression.

THE core of the Discovery engine (plan §4.5 / §7.4). It operationalizes the
governing principle **Anomaly ≠ Failure**: a scored deviation is only promoted
to a customer-visible `surfaced` finding when corroborated. Default is
`watching` (hidden). Suspect baselines and below-floor confidence are
`dismissed`. Precision over recall: promote slow, demote fast.

Pure decision logic so it is unit-testable and identical to the harness.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.services.discovery.scorer import AnomalyCandidate

TIER_WATCHING = "watching"
TIER_SURFACED = "surfaced"
TIER_DISMISSED = "dismissed"

DEFAULT_SURFACE_MIN_CONFIDENCE = 0.80
DEFAULT_WATCHING_MIN_CONFIDENCE = 0.55
DEFAULT_RECURRENCE_K = 3


@dataclass(frozen=True)
class PromotionInputs:
    """Aggregated evidence for one signature cluster + tunables."""

    occurrence_count: int
    max_confidence: float
    has_outcome: bool
    has_strong_structural: bool
    has_multi_dim: bool
    baseline_suspect: bool
    dismissed_before: bool = False
    surface_min_confidence: float = DEFAULT_SURFACE_MIN_CONFIDENCE
    watching_min_confidence: float = DEFAULT_WATCHING_MIN_CONFIDENCE
    recurrence_k: int = DEFAULT_RECURRENCE_K


def decide_tier(inputs: PromotionInputs) -> str:
    """Return the tier for a signature cluster.

    Gates, in order:
      1. Suspect baseline OR below the watching floor → dismissed.
      2. Feedback gate: dismissed-before raises the bar (needs outcome).
      3. Surface gate: confidence ≥ floor AND (outcome corroboration OR
         (recurrence ≥ k AND structural/multi-dim corroboration)) → surfaced.
      4. Otherwise → watching (default).
    """
    if inputs.baseline_suspect or inputs.max_confidence < inputs.watching_min_confidence:
        return TIER_DISMISSED

    recurring_structural = inputs.occurrence_count >= inputs.recurrence_k and (
        inputs.has_strong_structural or inputs.has_multi_dim
    )
    corroborated = inputs.has_outcome or recurring_structural

    # Feedback gate: if this signature was previously dismissed by a human,
    # only outcome corroboration (the strongest, label-free signal) may
    # re-surface it. Recurrence alone is not enough after a human "no".
    if inputs.dismissed_before and not inputs.has_outcome:
        return TIER_WATCHING

    if inputs.max_confidence >= inputs.surface_min_confidence and corroborated:
        return TIER_SURFACED

    return TIER_WATCHING


def aggregate_cluster(candidates: Sequence[AnomalyCandidate]) -> dict:
    """Aggregate a list of candidates sharing one signature into the
    evidence fields `decide_tier` needs, plus presentation fields.
    """
    if not candidates:
        raise ValueError("aggregate_cluster requires at least one candidate")

    representative = max(candidates, key=lambda c: (c.confidence, c.anomaly_score))
    occurrence_count = len(candidates)
    max_confidence = min(
        1.0,
        representative.confidence + min(0.12, max(0, occurrence_count - 1) * 0.03),
    )
    return {
        "signature": representative.signature,
        "primary_dimension": representative.primary_dimension,
        "reason": representative.reason,
        "corroboration": list(representative.corroboration),
        "anomaly_score": max(c.anomaly_score for c in candidates),
        "max_confidence": max_confidence,
        "occurrence_count": occurrence_count,
        "call_ids": [c.call_id for c in candidates],
        "has_outcome": any(c.outcome_corroborated for c in candidates),
        "has_strong_structural": any(c.strong_structural for c in candidates),
        "has_multi_dim": any(len(c.dimensions) >= 2 for c in candidates),
    }
