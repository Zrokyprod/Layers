"""
Drift detector (Layer 4) — pure-functional.

Given a list of probe rows for a single (model, category), where each row
carries a `run_date`, an `outcome`, optionally a `judge_pass`, and
optionally an `output_embedding`, compute a `DriftMetric` for the
target `current_date` against a 7-day baseline.

Strict rules:

  1. Coverage gate. The detector returns `None` when *either* the
     current day or any single baseline day has fewer than
     `min_coverage` fraction of OK probes. Sparse data is silently
     dropped, never alerted on.
  2. Standard-deviation floor. When baseline pass-rates are nearly
     constant (e.g. all 1.0), the raw stddev is ~0 and the z-score
     blows up. We clamp `stddev = max(stddev, STDDEV_FLOOR)` so a
     0.05 deviation in any direction maps to z ≈ 1, which is below
     the alert threshold and prevents false positives.
  3. Embedding centroid. The 7-day centroid is the unweighted mean of
     all OK embeddings for that (prompt_id, baseline window). Cosine
     today is compared against the centroid for the *same prompt_id*;
     we then average across the category's prompts to get a category-
     level cosine that has a per-day series.
  4. Combined verdict (used by aggregator):
        - Single-metric → candidate (not public)
        - Both judge_z AND embedding_z cross threshold AND agree in
          sign → publish.

The function is dependency-free (imports only stdlib + value types).
This makes it trivial to test exhaustively and avoids any DB at this
layer.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Mapping, Sequence

from app.services.provider_drift.models import DriftMetric

# ── tunables ────────────────────────────────────────────────────────────────

#: Minimum fraction of category prompts that must have outcome=ok on a
#: given day for that day to count toward pass-rate / cosine math.
DEFAULT_MIN_COVERAGE: float = 0.80

#: Standard-deviation floor (clamps near-zero variance).
STDDEV_FLOOR: float = 0.02

#: Default baseline window length (days, exclusive of current_date).
DEFAULT_BASELINE_DAYS: int = 7

#: Z-score thresholds (absolute value, applied independently to judge & embedding).
Z_INFO: float = 2.0
Z_WARN: float = 3.0
Z_CRITICAL: float = 4.0

#: Pass-rate drop in percentage points that escalates to critical regardless of z.
CRITICAL_DELTA_PP: float = 15.0


# ── input DTO ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProbeRow:
    """Minimal projection of a `provider_drift_probes` row.

    The aggregator builds these from ORM rows. Defining a separate value
    type keeps the detector decoupled from SQLAlchemy.
    """

    prompt_id: str
    run_date: date
    outcome: str
    judge_pass: bool | None
    embedding: tuple[float, ...] | None


# ── public entry point ──────────────────────────────────────────────────────


def compute_drift(
    *,
    model_id: str,
    category: str,
    current_date: date,
    probes: Iterable[ProbeRow],
    category_size: int,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> DriftMetric | None:
    """Compute a DriftMetric for one (model, category, day).

    `category_size` is the count of *active* prompts in the category;
    used to compute coverage. Pass it from the suite, not from the
    probes list (probes may be missing entirely on a given day).

    Returns None when:
      - no probes exist for current_date
      - coverage on current_date or any baseline day is below threshold
      - the baseline window has zero usable days
    """
    if category_size <= 0:
        return None

    baseline_start = current_date - timedelta(days=baseline_days)
    baseline_end = current_date - timedelta(days=1)

    by_day = _group_by_day(probes)

    # Coverage on current day
    current_probes = by_day.get(current_date, [])
    current_ok = [p for p in current_probes if p.outcome == "ok"]
    coverage_current = len(current_ok) / float(category_size)
    if coverage_current < min_coverage:
        return None

    # Coverage on each baseline day must clear gate.
    baseline_pass_rates: list[float] = []
    baseline_centroids_by_prompt: dict[str, tuple[float, ...]] = {}
    coverages: list[float] = []
    baseline_sample_total = 0

    for offset in range(baseline_days):
        d = baseline_start + timedelta(days=offset)
        day_probes = by_day.get(d, [])
        day_ok = [p for p in day_probes if p.outcome == "ok"]
        cov = len(day_ok) / float(category_size)
        coverages.append(cov)
        if cov < min_coverage:
            return None
        baseline_sample_total += len(day_ok)
        # pass-rate
        rate = _safe_pass_rate(day_ok)
        if rate is not None:
            baseline_pass_rates.append(rate)

    if not baseline_pass_rates:
        return None

    coverage_baseline_min = min(coverages) if coverages else 0.0

    # Build per-prompt centroid across baseline window using OK probes only.
    embeddings_by_prompt: dict[str, list[tuple[float, ...]]] = defaultdict(list)
    for d_probes in by_day.values():
        for p in d_probes:
            if (
                p.outcome == "ok"
                and p.embedding is not None
                and baseline_start <= p.run_date <= baseline_end
            ):
                embeddings_by_prompt[p.prompt_id].append(p.embedding)
    for pid, vecs in list(embeddings_by_prompt.items()):
        baseline_centroids_by_prompt[pid] = _mean_vector(vecs)

    # ── pass-rate math ──
    pass_rate_current = _safe_pass_rate(current_ok) or 0.0
    pass_rate_baseline = _mean(baseline_pass_rates)
    pass_rate_stddev = max(_stddev(baseline_pass_rates), STDDEV_FLOOR)
    judge_z = (pass_rate_current - pass_rate_baseline) / pass_rate_stddev

    # ── embedding cosine math ──
    embedding_z = _embedding_zscore(
        current_probes=current_ok,
        by_day=by_day,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        centroids=baseline_centroids_by_prompt,
    )

    return DriftMetric(
        model_id=model_id,
        category=category,
        current_date=current_date,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        pass_rate_current=pass_rate_current,
        pass_rate_baseline=pass_rate_baseline,
        pass_rate_stddev=pass_rate_stddev,
        judge_z=judge_z,
        embedding_z=embedding_z,
        coverage_current=coverage_current,
        coverage_baseline_min=coverage_baseline_min,
        sample_size_current=len(current_ok),
        sample_size_baseline=baseline_sample_total,
    )


# ── verdict logic ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DriftVerdict:
    publish: bool         # True → public banner / RSS
    is_candidate: bool    # True → DB row only (one-metric trip)
    severity: str         # info | warn | critical


def classify(metric: DriftMetric) -> DriftVerdict | None:
    """Decide whether to alert.

    Rules:
      1. Both metrics must cross threshold AND agree in sign → publish.
      2. Exactly one metric crosses threshold → candidate (no publish).
      3. Neither crosses → no alert at all.
    """
    judge_abs = abs(metric.judge_z)
    embed_abs = abs(metric.embedding_z)
    judge_trip = judge_abs >= Z_INFO
    embed_trip = embed_abs >= Z_INFO

    if not (judge_trip or embed_trip):
        return None

    if judge_trip and embed_trip:
        # Sign agreement check (both negative = both indicating drop).
        # Embedding z is positive when cosine *fell* (we encode it that
        # way in the helper). So matching signs is meaningful.
        if (metric.judge_z * metric.embedding_z) >= 0:
            return DriftVerdict(
                publish=True,
                is_candidate=False,
                severity=_severity(metric, judge_abs, embed_abs),
            )
        # Disagree in sign — keep as candidate.
        return DriftVerdict(
            publish=False,
            is_candidate=True,
            severity=_severity(metric, judge_abs, embed_abs),
        )

    # Single metric trip → candidate only.
    return DriftVerdict(
        publish=False,
        is_candidate=True,
        severity=_severity(metric, judge_abs, embed_abs),
    )


def _severity(metric: DriftMetric, judge_abs: float, embed_abs: float) -> str:
    z = max(judge_abs, embed_abs)
    delta = abs(metric.delta_pp)
    if delta >= CRITICAL_DELTA_PP or z >= Z_CRITICAL:
        return "critical"
    if z >= Z_WARN:
        return "warn"
    return "info"


# ── helpers ─────────────────────────────────────────────────────────────────


def _group_by_day(probes: Iterable[ProbeRow]) -> Mapping[date, list[ProbeRow]]:
    out: dict[date, list[ProbeRow]] = defaultdict(list)
    for p in probes:
        out[p.run_date].append(p)
    return out


def _safe_pass_rate(probes: Sequence[ProbeRow]) -> float | None:
    judged = [p for p in probes if p.judge_pass is not None]
    if not judged:
        return None
    n_pass = sum(1 for p in judged if p.judge_pass)
    return n_pass / float(len(judged))


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / float(len(values))


def _stddev(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    m = _mean(values)
    var = sum((v - m) ** 2 for v in values) / float(n - 1)
    return math.sqrt(var)


def _mean_vector(vectors: Sequence[Sequence[float]]) -> tuple[float, ...]:
    if not vectors:
        return ()
    n = len(vectors)
    dim = len(vectors[0])
    acc = [0.0] * dim
    for v in vectors:
        if len(v) != dim:
            # Heterogeneous embeddings → bail out (would corrupt cosine).
            return ()
        for i, x in enumerate(v):
            acc[i] += x
    return tuple(x / n for x in acc)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _embedding_zscore(
    *,
    current_probes: Sequence[ProbeRow],
    by_day: Mapping[date, Sequence[ProbeRow]],
    baseline_start: date,
    baseline_end: date,
    centroids: Mapping[str, tuple[float, ...]],
) -> float:
    """Compute embedding_z.

    Convention: positive z ↔ cosine-vs-centroid *fell* below baseline,
    matching the sign convention of judge_z (positive ↔ pass-rate
    fell). This makes "both negative" mean "both indicate degradation",
    which is the same direction so signs *match* (both negative).
    Wait — let's flip:  judge_z is `(current - baseline) / σ`. A
    drop in pass-rate makes judge_z negative. A drop in cosine should
    also produce a negative embedding_z. So we'll mirror the sign.
    """
    if not centroids:
        return 0.0

    # Per-day mean cosine for the baseline window.
    daily_cosines: list[float] = []
    for offset in range((baseline_end - baseline_start).days + 1):
        d = baseline_start + timedelta(days=offset)
        day_probes = by_day.get(d, [])
        per_prompt: list[float] = []
        for p in day_probes:
            if p.outcome != "ok" or p.embedding is None:
                continue
            centroid = centroids.get(p.prompt_id)
            if not centroid:
                continue
            per_prompt.append(_cosine(p.embedding, centroid))
        if per_prompt:
            daily_cosines.append(_mean(per_prompt))

    if len(daily_cosines) < 2:
        return 0.0

    baseline_mean = _mean(daily_cosines)
    baseline_std = max(_stddev(daily_cosines), STDDEV_FLOOR)

    # Today's mean cosine.
    today_per_prompt: list[float] = []
    for p in current_probes:
        if p.embedding is None:
            continue
        centroid = centroids.get(p.prompt_id)
        if not centroid:
            continue
        today_per_prompt.append(_cosine(p.embedding, centroid))

    if not today_per_prompt:
        return 0.0
    today_mean = _mean(today_per_prompt)

    return (today_mean - baseline_mean) / baseline_std
