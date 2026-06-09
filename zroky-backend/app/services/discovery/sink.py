"""Discovery → Anomalies sink (Option A).

The discovery engine does NOT own a parallel findings table. Surfaced
deviations are written to the EXISTING `anomalies` table via the
`BEHAVIORAL_DRIFT` detector source, so Zroky keeps one internal Issue
concept instead of a parallel findings table. Customer `/v1/issues`
visibility remains separately blocked by `DISCOVERY_CUSTOMER_SURFACE_ENABLED`
until the real-trace precision gate passes.

Only `surfaced`-tier clusters become anomaly rows. `watching` / `dismissed`
clusters are intentionally NOT written — they must never reach the customer
inbox (the Anomaly ≠ Failure rule).
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import Anomaly
from app.services.anomalies import upsert_anomaly
from app.services.discovery.promote import (
    PromotionInputs,
    TIER_SURFACED,
    aggregate_cluster,
    decide_tier,
)
from app.services.discovery.scorer import AnomalyCandidate

logger = logging.getLogger(__name__)

# Discovery writes a single canonical detector code into anomalies. The
# specific deviation dimension (missing_critical_tool, output_shape, …) is
# preserved in evidence_json for the dashboard / root-cause text.
DISCOVERY_DETECTOR = "BEHAVIORAL_DRIFT"


def sink_candidates(
    db: Session,
    *,
    project_id: str,
    candidates: Sequence[AnomalyCandidate],
    suspect_signatures: set[str] | None = None,
    dismissed_signatures: set[str] | None = None,
    surface_min_confidence: float = 0.80,
    recurrence_k: int = 3,
    now: datetime | None = None,
) -> list[Anomaly]:
    """Cluster candidates, decide tier, and upsert SURFACED clusters into
    `anomalies` via the shared `upsert_anomaly` path.

    Returns the upserted Anomaly rows (surfaced only). watching/dismissed are
    skipped by design.
    """
    now = now or datetime.now(timezone.utc)
    suspect = suspect_signatures or set()
    dismissed = dismissed_signatures or set()

    clustered: dict[str, list[AnomalyCandidate]] = {}
    for candidate in candidates:
        clustered.setdefault(candidate.signature, []).append(candidate)

    written: list[Anomaly] = []
    for signature, group in clustered.items():
        agg = aggregate_cluster(group)
        tier = decide_tier(
            PromotionInputs(
                occurrence_count=agg["occurrence_count"],
                max_confidence=agg["max_confidence"],
                has_outcome=agg["has_outcome"],
                has_strong_structural=agg["has_strong_structural"],
                has_multi_dim=agg["has_multi_dim"],
                baseline_suspect=signature in suspect,
                dismissed_before=signature in dismissed,
                surface_min_confidence=surface_min_confidence,
                recurrence_k=recurrence_k,
            )
        )
        if tier != TIER_SURFACED:
            continue  # watching / dismissed never reach the customer surface

        sample = group[0]
        evidence = {
            "source": "discovery",
            "primary_dimension": agg["primary_dimension"],
            "summary": agg["reason"],
            "confidence": round(float(agg["max_confidence"]), 4),
            "anomaly_score": round(float(agg["anomaly_score"]), 4),
            "corroboration": agg["corroboration"],
            "discovery_signature": signature,
        }
        anomaly = upsert_anomaly(
            db,
            project_id=project_id,
            detector=DISCOVERY_DETECTOR,
            prompt_fingerprint=None,
            agent_name=None,
            call_id=str(agg["call_ids"][0]) if agg["call_ids"] else None,
            occurred_at=now,
            evidence=evidence,
            fingerprint_extra=signature,
        )
        if anomaly is not None:
            written.append(anomaly)
    logger.info(
        "discovery_sink project=%s candidates=%d surfaced_anomalies=%d",
        project_id, len(candidates), len(written),
    )
    return written
