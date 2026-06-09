"""Discovery pillar — unknown-failure discovery (Discover → Prove → Guard).

The engine learns per-workflow behavioral baselines from production traffic,
scores new traces for deviation, and promotes a deviation to a customer-visible
*failure* ONLY when corroborated (outcome / recurrence / replay / human).
Governing principle: **Anomaly ≠ Failure**, precision over recall.

This package root exports only the PURE logic (no DB/ORM imports), so the
offline harness (`scripts/discovery_harness.py`) can reuse the exact same
math without pulling in the database layer. The DB-touching pieces are imported
by their full path where needed:

    app.services.discovery.baseline   — baseline persistence (ORM)
    app.services.discovery.sink       — surfaced candidates → anomalies table
    app.services.discovery.runtime    — orchestration (refresh + scan)

Pipeline (pure):
    features.extract_features(call)         -> BehavioralFeatures
    baseline_core.build_baselines_in_memory -> {key: features_payload}
    scorer.score(features, baseline)        -> AnomalyCandidate
    promote.decide_tier(inputs)             -> tier
"""
from __future__ import annotations

from app.services.discovery.features import (
    BehavioralFeatures,
    behavior_key,
    extract_features,
    output_shape_of,
    sequence_key,
    status_is_failure,
)
from app.services.discovery.baseline_core import (
    BaselineConfig,
    NumericStats,
    build_baselines_in_memory,
    build_features_payload,
)
from app.services.discovery.scorer import (
    AnomalyCandidate,
    make_signature,
    score,
)
from app.services.discovery.promote import (
    TIER_DISMISSED,
    TIER_SURFACED,
    TIER_WATCHING,
    PromotionInputs,
    aggregate_cluster,
    decide_tier,
)

__all__ = [
    "BehavioralFeatures",
    "behavior_key",
    "extract_features",
    "output_shape_of",
    "sequence_key",
    "status_is_failure",
    "BaselineConfig",
    "NumericStats",
    "build_baselines_in_memory",
    "build_features_payload",
    "AnomalyCandidate",
    "make_signature",
    "score",
    "TIER_DISMISSED",
    "TIER_SURFACED",
    "TIER_WATCHING",
    "PromotionInputs",
    "aggregate_cluster",
    "decide_tier",
]
