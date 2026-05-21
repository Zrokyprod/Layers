"""
Aggregator (Layer 5) — pulls probes from DB, runs the drift detector for
every (model, category, current_date), and idempotently upserts alert
rows.

Idempotency:
  Alerts are unique on `(model_id, category, current_date)`. Re-running
  the aggregator for the same date overwrites the existing row's
  fields (severity, headline, evidence) but never duplicates. This
  means it's safe to re-run after the daily probe run finishes late
  on a day, or to back-fill a historical date.

Headline format (deterministic, locale-en):
    "{ModelDisplayName} behavior shifted on {YYYY-MM-DD} — {category}: {±N.Npp}"
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ProviderDriftAlert,
    ProviderDriftModel,
    ProviderDriftProbe,
    ProviderDriftPrompt,
)
from app.services.provider_drift.categories import CATEGORIES
from app.services.provider_drift.drift_detector import (
    DEFAULT_BASELINE_DAYS,
    DEFAULT_MIN_COVERAGE,
    ProbeRow,
    classify,
    compute_drift,
)
from app.services.provider_drift.models import DriftAlertSpec, DriftMetric

logger = logging.getLogger(__name__)


# ── result type ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AggregatorOutcome:
    """Summary the scheduler logs."""

    current_date: date
    metrics_evaluated: int
    alerts_published: int
    candidates_recorded: int
    skipped_for_coverage: int


# ── public entry point ──────────────────────────────────────────────────────


def run_aggregator(
    *,
    db: Session,
    current_date: date,
    model_ids: Sequence[str] | None = None,
    categories: Sequence[str] = CATEGORIES,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> AggregatorOutcome:
    """Compute drift metrics for every (model, category) and persist alerts.

    `model_ids` defaults to all active models. `categories` defaults to
    the canonical 8.
    """
    models = _load_models(db, model_ids=model_ids)
    if not models:
        return AggregatorOutcome(current_date, 0, 0, 0, 0)

    category_sizes = _category_sizes(db)

    metrics_evaluated = 0
    alerts_published = 0
    candidates_recorded = 0
    skipped = 0

    for model in models:
        for category in categories:
            cat_size = category_sizes.get(category, 0)
            if cat_size == 0:
                skipped += 1
                continue

            probes = _load_probes(
                db,
                model_id=model.id,
                category=category,
                start_date=current_date.fromordinal(
                    current_date.toordinal() - baseline_days
                ),
                end_date=current_date,
            )

            metric = compute_drift(
                model_id=model.id,
                category=category,
                current_date=current_date,
                probes=probes,
                category_size=cat_size,
                baseline_days=baseline_days,
                min_coverage=min_coverage,
            )
            if metric is None:
                skipped += 1
                continue

            metrics_evaluated += 1
            verdict = classify(metric)
            if verdict is None:
                continue

            alert_spec = build_alert_spec(
                metric=metric,
                model_display_name=model.display_name,
                severity=verdict.severity,
                is_candidate=verdict.is_candidate,
            )
            _upsert_alert(db, alert_spec)
            if verdict.publish:
                alerts_published += 1
            else:
                candidates_recorded += 1

    db.flush()
    return AggregatorOutcome(
        current_date=current_date,
        metrics_evaluated=metrics_evaluated,
        alerts_published=alerts_published,
        candidates_recorded=candidates_recorded,
        skipped_for_coverage=skipped,
    )


# ── headline + evidence builders ────────────────────────────────────────────


def build_alert_spec(
    *,
    metric: DriftMetric,
    model_display_name: str,
    severity: str,
    is_candidate: bool,
) -> DriftAlertSpec:
    """Compose a `DriftAlertSpec` with a deterministic headline + evidence."""
    direction = "regressed" if metric.delta_pp < 0 else "improved"
    sign = "" if metric.delta_pp >= 0 else "−"
    headline = (
        f"{model_display_name} {direction} on {metric.category} "
        f"({sign}{abs(metric.delta_pp):.1f}pp) on "
        f"{metric.current_date.isoformat()}"
    )
    if len(headline) > 255:
        headline = headline[:252] + "..."

    evidence = {
        "pass_rate_current": round(metric.pass_rate_current, 4),
        "pass_rate_baseline": round(metric.pass_rate_baseline, 4),
        "pass_rate_stddev": round(metric.pass_rate_stddev, 4),
        "judge_z": round(metric.judge_z, 3),
        "embedding_z": round(metric.embedding_z, 3),
        "delta_pp": round(metric.delta_pp, 2),
        "coverage_current": round(metric.coverage_current, 3),
        "coverage_baseline_min": round(metric.coverage_baseline_min, 3),
        "sample_size_current": metric.sample_size_current,
        "sample_size_baseline": metric.sample_size_baseline,
    }

    return DriftAlertSpec(
        model_id=metric.model_id,
        category=metric.category,
        current_date=metric.current_date,
        baseline_start=metric.baseline_start,
        baseline_end=metric.baseline_end,
        pass_rate_current=metric.pass_rate_current,
        pass_rate_baseline=metric.pass_rate_baseline,
        judge_z=metric.judge_z,
        embedding_z=metric.embedding_z,
        delta_pp=metric.delta_pp,
        severity=severity,
        headline=headline,
        is_candidate=is_candidate,
        evidence=evidence,
        published_at=datetime.now(timezone.utc),
    )


# ── DB helpers ──────────────────────────────────────────────────────────────


def _load_models(
    db: Session, *, model_ids: Sequence[str] | None
) -> list[ProviderDriftModel]:
    stmt = select(ProviderDriftModel).where(ProviderDriftModel.active == True)
    if model_ids:
        stmt = stmt.where(ProviderDriftModel.id.in_(list(model_ids)))
    return list(db.execute(stmt).scalars().all())


def _category_sizes(db: Session) -> dict[str, int]:
    rows = (
        db.execute(
            select(ProviderDriftPrompt).where(ProviderDriftPrompt.active == True)
        )
        .scalars()
        .all()
    )
    sizes: dict[str, int] = {}
    for r in rows:
        sizes[r.category] = sizes.get(r.category, 0) + 1
    return sizes


def _load_probes(
    db: Session,
    *,
    model_id: str,
    category: str,
    start_date: date,
    end_date: date,
) -> list[ProbeRow]:
    rows = (
        db.execute(
            select(ProviderDriftProbe)
            .where(
                ProviderDriftProbe.model_id == model_id,
                ProviderDriftProbe.category == category,
                ProviderDriftProbe.run_date >= start_date,
                ProviderDriftProbe.run_date <= end_date,
            )
        )
        .scalars()
        .all()
    )

    out: list[ProbeRow] = []
    for r in rows:
        embedding: tuple[float, ...] | None = None
        if r.output_embedding:
            try:
                parsed = json.loads(r.output_embedding)
                if isinstance(parsed, list):
                    embedding = tuple(float(x) for x in parsed)
            except (ValueError, TypeError):
                embedding = None
        out.append(
            ProbeRow(
                prompt_id=r.prompt_id,
                run_date=r.run_date,
                outcome=r.outcome,
                judge_pass=r.judge_pass,
                embedding=embedding,
            )
        )
    return out


def _upsert_alert(db: Session, spec: DriftAlertSpec) -> None:
    """Insert or update the alert row keyed by (model, category, date)."""
    existing = db.execute(
        select(ProviderDriftAlert).where(
            ProviderDriftAlert.model_id == spec.model_id,
            ProviderDriftAlert.category == spec.category,
            ProviderDriftAlert.current_date == spec.current_date,
        )
    ).scalar_one_or_none()

    if existing is None:
        from uuid import uuid4
        db.add(
            ProviderDriftAlert(
                id=str(uuid4()),
                model_id=spec.model_id,
                category=spec.category,
                current_date=spec.current_date,
                baseline_start=spec.baseline_start,
                baseline_end=spec.baseline_end,
                pass_rate_current=spec.pass_rate_current,
                pass_rate_baseline=spec.pass_rate_baseline,
                judge_z=spec.judge_z,
                embedding_z=spec.embedding_z,
                delta_pp=spec.delta_pp,
                severity=spec.severity,
                headline=spec.headline,
                evidence_json=spec.evidence_json(),
                is_candidate=spec.is_candidate,
                published_at=spec.published_at,
            )
        )
        return

    existing.baseline_start = spec.baseline_start
    existing.baseline_end = spec.baseline_end
    existing.pass_rate_current = spec.pass_rate_current
    existing.pass_rate_baseline = spec.pass_rate_baseline
    existing.judge_z = spec.judge_z
    existing.embedding_z = spec.embedding_z
    existing.delta_pp = spec.delta_pp
    existing.severity = spec.severity
    existing.headline = spec.headline
    existing.evidence_json = spec.evidence_json()
    existing.is_candidate = spec.is_candidate
    existing.published_at = spec.published_at
