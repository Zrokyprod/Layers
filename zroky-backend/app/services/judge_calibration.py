"""
Judge calibration tracker (Module 7; plan §17.2 decision #4).

Maintains a rolling per-(project, judge_model) sample window of judge verdicts
paired with ground-truth verdicts (when known) and emits a `judge_drift_alert`
WARNING log when the disagreement rate exceeds
`JUDGE_CALIBRATION_DRIFT_THRESHOLD` (default 5%).

Design choices:
  - No new DB table. Samples live in Redis (TTL'd sliding window) when
    REDIS_URL is reachable, else in a process-local dict.
  - No new detector vocab. Drift is surfaced via structured log + an
    in-memory alert callback registry. Module 11 (founder console) will
    wire the callback to the alerts surface; for now, anyone curious can
    grep `event=judge_drift_alert` in the log stream.
  - Pure-functional sample shape so a future migration to ClickHouse
    (per plan trigger ">50M events/mo") is a 1-table swap.

Public surface:
  - `record_sample(*, project_id, judge_model, judge_verdict, truth_verdict)`
    → returns `DriftStatus` describing the post-record window state.
  - `compute_drift(project_id, judge_model)` → DriftStatus.
  - `register_alert_callback(fn)` → fn(DriftStatus) called on threshold
    breach. Used by tests and (eventually) the founder console alerts.
  - `clear_all()` → wipe all windows. Test-only.

Threshold semantics:
  - Disagreement = samples where judge_verdict != truth_verdict, including
    inconclusive-on-either-side (the judge SHOULD form an opinion when ground
    truth is decisive).
  - Window: JUDGE_CALIBRATION_WINDOW_HOURS hours of wall-clock time.
  - Floor: at least JUDGE_CALIBRATION_MIN_SAMPLES before drift is computed —
    smaller windows are too noisy to alarm on.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ── data shapes ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DriftStatus:
    """Snapshot of a (project, judge_model) calibration window."""

    project_id: str
    judge_model: str
    sample_count: int
    disagreement_count: int
    disagreement_rate: float
    threshold: float
    breached: bool

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "judge_model": self.judge_model,
            "sample_count": self.sample_count,
            "disagreement_count": self.disagreement_count,
            "disagreement_rate": self.disagreement_rate,
            "threshold": self.threshold,
            "breached": self.breached,
        }


# ── alert callback registry ────────────────────────────────────────────────


_callbacks_lock = threading.Lock()
_callbacks: list[Callable[[DriftStatus], None]] = []


def register_alert_callback(fn: Callable[[DriftStatus], None]) -> None:
    """Register a function to be called when drift threshold is breached.

    Callbacks run synchronously on the recording thread. If a callback
    raises, the exception is logged but does not propagate (so a
    misbehaving alert sink can't crash the worker).
    """
    if not callable(fn):
        raise TypeError("register_alert_callback expects a callable")
    with _callbacks_lock:
        _callbacks.append(fn)


def _unregister_all_callbacks_for_tests() -> None:
    """Clear callbacks. Test fixtures call this between cases."""
    with _callbacks_lock:
        _callbacks.clear()


def _fire_callbacks(status: DriftStatus) -> None:
    with _callbacks_lock:
        snapshot = list(_callbacks)
    for cb in snapshot:
        try:
            cb(status)
        except Exception:  # noqa: BLE001
            logger.exception("judge_calibration: alert callback raised")


# ── storage: redis primary, in-memory fallback ─────────────────────────────


_memory_lock = threading.Lock()
# key=(project_id, judge_model) → list[(timestamp_epoch, judge_v, truth_v)]
_memory_store: dict[tuple[str, str], list[tuple[float, str, str]]] = {}


def _redis_client():
    """Return a redis.Redis or None on any failure.

    Mirrors the resolver's lazy-init pattern so tests that don't run Redis
    transparently degrade to the in-memory store.
    """
    try:
        import redis  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    url = (get_settings().REDIS_URL or "").strip()
    if not url:
        return None
    try:
        client = redis.from_url(url, socket_connect_timeout=0.5)
        client.ping()
        return client
    except Exception:  # noqa: BLE001
        return None


def _redis_key(project_id: str, judge_model: str) -> str:
    safe_pid = project_id.replace(":", "_")
    safe_model = judge_model.replace(":", "_")
    return f"judgecal:{safe_pid}:{safe_model}"


def _record_redis(
    client,
    *,
    project_id: str,
    judge_model: str,
    judge_verdict: str,
    truth_verdict: str,
    now: float,
    window_seconds: int,
) -> list[tuple[float, str, str]]:
    """Append + prune in Redis. Returns the post-prune sample list.

    Uses a sorted set keyed on timestamp so range-by-score gives us the
    sliding window for free. Values are JSON triples.
    """
    key = _redis_key(project_id, judge_model)
    member = json.dumps(
        {"t": now, "j": judge_verdict, "g": truth_verdict},
        separators=(",", ":"),
    )
    cutoff = now - window_seconds
    try:
        pipe = client.pipeline()
        pipe.zadd(key, {member: now})
        pipe.zremrangebyscore(key, "-inf", cutoff)
        # Generous TTL so dormant projects don't pile up in Redis.
        pipe.expire(key, window_seconds * 2)
        pipe.zrange(key, 0, -1)
        results = pipe.execute()
    except Exception:  # noqa: BLE001
        logger.warning(
            "judge_calibration: redis pipeline failed; falling back to memory"
        )
        return _record_memory(
            project_id=project_id,
            judge_model=judge_model,
            judge_verdict=judge_verdict,
            truth_verdict=truth_verdict,
            now=now,
            window_seconds=window_seconds,
        )
    samples: list[tuple[float, str, str]] = []
    for raw in results[-1] or []:
        try:
            obj = json.loads(raw)
            samples.append(
                (float(obj["t"]), str(obj["j"]), str(obj["g"]))
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    samples.sort(key=lambda x: x[0])
    return samples


def _record_memory(
    *,
    project_id: str,
    judge_model: str,
    judge_verdict: str,
    truth_verdict: str,
    now: float,
    window_seconds: int,
) -> list[tuple[float, str, str]]:
    """Append + prune in the process-local dict."""
    key = (project_id, judge_model)
    cutoff = now - window_seconds
    with _memory_lock:
        bucket = _memory_store.setdefault(key, [])
        bucket.append((now, judge_verdict, truth_verdict))
        # Prune in place — small windows so O(n) is fine.
        _memory_store[key] = [s for s in bucket if s[0] >= cutoff]
        return list(_memory_store[key])


def _read_samples(
    *, project_id: str, judge_model: str, window_seconds: int
) -> list[tuple[float, str, str]]:
    """Read without writing. Used by compute_drift()."""
    now = time.time()
    cutoff = now - window_seconds
    client = _redis_client()
    if client is not None:
        key = _redis_key(project_id, judge_model)
        try:
            client.zremrangebyscore(key, "-inf", cutoff)
            raws = client.zrange(key, 0, -1)
            out: list[tuple[float, str, str]] = []
            for raw in raws or []:
                try:
                    obj = json.loads(raw)
                    out.append(
                        (float(obj["t"]), str(obj["j"]), str(obj["g"]))
                    )
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
            out.sort(key=lambda x: x[0])
            return out
        except Exception:  # noqa: BLE001
            logger.warning(
                "judge_calibration: redis read failed; falling back to memory"
            )
    key2 = (project_id, judge_model)
    with _memory_lock:
        return [s for s in _memory_store.get(key2, []) if s[0] >= cutoff]


# ── core API ───────────────────────────────────────────────────────────────


def record_sample(
    *,
    project_id: str,
    judge_model: str,
    judge_verdict: str,
    truth_verdict: str,
) -> DriftStatus:
    """Record one (judge_verdict, truth_verdict) pair and return the
    post-record DriftStatus.

    Fires registered alert callbacks if the threshold is breached AND the
    floor sample count is met. Idempotency note: callers may invoke this
    multiple times with the same logical sample (e.g. on retry); each
    call is a fresh sample.
    """
    s = get_settings()
    pid = (project_id or "").strip()
    model = (judge_model or "").strip()
    if not pid or not model:
        # Nothing to do — surfacing as a no-op DriftStatus rather than
        # raising keeps callers from having to defensively check IDs.
        return DriftStatus(
            project_id=pid,
            judge_model=model,
            sample_count=0,
            disagreement_count=0,
            disagreement_rate=0.0,
            threshold=float(s.JUDGE_CALIBRATION_DRIFT_THRESHOLD),
            breached=False,
        )

    window_seconds = max(1, int(s.JUDGE_CALIBRATION_WINDOW_HOURS) * 3600)
    now = time.time()

    client = _redis_client()
    if client is not None:
        samples = _record_redis(
            client,
            project_id=pid,
            judge_model=model,
            judge_verdict=judge_verdict,
            truth_verdict=truth_verdict,
            now=now,
            window_seconds=window_seconds,
        )
    else:
        samples = _record_memory(
            project_id=pid,
            judge_model=model,
            judge_verdict=judge_verdict,
            truth_verdict=truth_verdict,
            now=now,
            window_seconds=window_seconds,
        )

    status = _evaluate(samples, project_id=pid, judge_model=model, settings=s)
    if status.breached:
        # Structured WARNING — founder-console alerts (Module 11) will
        # subscribe via register_alert_callback once it ships.
        logger.warning(
            "judge_drift_alert project=%s model=%s rate=%.3f threshold=%.3f n=%d",
            status.project_id,
            status.judge_model,
            status.disagreement_rate,
            status.threshold,
            status.sample_count,
        )
        _fire_callbacks(status)
    return status


def compute_drift(project_id: str, judge_model: str) -> DriftStatus:
    """Compute the current DriftStatus without recording a new sample."""
    s = get_settings()
    pid = (project_id or "").strip()
    model = (judge_model or "").strip()
    window_seconds = max(1, int(s.JUDGE_CALIBRATION_WINDOW_HOURS) * 3600)
    samples = _read_samples(
        project_id=pid, judge_model=model, window_seconds=window_seconds
    )
    return _evaluate(samples, project_id=pid, judge_model=model, settings=s)


def _evaluate(
    samples: list[tuple[float, str, str]],
    *,
    project_id: str,
    judge_model: str,
    settings,
) -> DriftStatus:
    n = len(samples)
    threshold = float(settings.JUDGE_CALIBRATION_DRIFT_THRESHOLD)
    min_samples = int(settings.JUDGE_CALIBRATION_MIN_SAMPLES)
    if n == 0:
        return DriftStatus(
            project_id=project_id,
            judge_model=judge_model,
            sample_count=0,
            disagreement_count=0,
            disagreement_rate=0.0,
            threshold=threshold,
            breached=False,
        )
    disagree = sum(1 for _, j, g in samples if j != g)
    rate = disagree / n
    breached = (n >= min_samples) and (rate > threshold)
    return DriftStatus(
        project_id=project_id,
        judge_model=judge_model,
        sample_count=n,
        disagreement_count=disagree,
        disagreement_rate=rate,
        threshold=threshold,
        breached=breached,
    )


def clear_all() -> None:
    """Wipe all in-memory windows + all Redis keys (test-only).

    Best-effort on Redis; never raises.
    """
    with _memory_lock:
        _memory_store.clear()
        _dim_memory_store.clear()
    client = _redis_client()
    if client is None:
        return
    try:
        for key in client.scan_iter(match="judgecal:*"):
            client.delete(key)
        for key in client.scan_iter(match="judgedim:*"):
            client.delete(key)
    except Exception:  # noqa: BLE001
        logger.debug("judge_calibration.clear_all: redis sweep failed")


# ─────────────────────────────────────────────────────────────────────────────
# Per-dimension drift (Layer 3 extension)
#
# Verdict-level calibration above catches *flips* (judge says pass when truth
# was fail). But the multi-dim evaluators (MultiDimEvaluator,
# ReferenceFreeEvaluator) produce continuous scores per dimension that can
# slide downward for weeks before the verdict actually flips. Per-dim drift
# tracking surfaces those slides early.
#
# Storage layout mirrors the verdict-pair store: a separate Redis sorted set
# and parallel in-memory dict, keyed on (project_id, judge_model, dimension).
# Records hold (timestamp, score) tuples.
#
# Drift heuristic: split the window into older-half and recent-half by sample
# count, compare means. Breach when (older_mean - recent_mean) exceeds
# _DIMENSION_DRIFT_THRESHOLD (default 0.10 on a 0..1 scale).
# ─────────────────────────────────────────────────────────────────────────────


_DIMENSION_DRIFT_THRESHOLD: float = 0.10
_DIMENSION_MIN_SAMPLES_PER_HALF: int = 10


@dataclass(frozen=True)
class DimensionDriftStatus:
    """Snapshot of a per-dimension drift window.

    Drift is measured as ``older_mean - recent_mean`` (positive => quality
    going down). Breach fires when drift exceeds ``threshold`` AND both
    halves have at least ``_DIMENSION_MIN_SAMPLES_PER_HALF`` samples.
    """

    project_id: str
    judge_model: str
    dimension: str
    sample_count: int
    older_mean: float
    recent_mean: float
    drift: float  # older_mean - recent_mean (positive => degradation)
    threshold: float
    breached: bool

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "judge_model": self.judge_model,
            "dimension": self.dimension,
            "sample_count": self.sample_count,
            "older_mean": self.older_mean,
            "recent_mean": self.recent_mean,
            "drift": self.drift,
            "threshold": self.threshold,
            "breached": self.breached,
        }


# In-memory store: (project_id, judge_model, dimension) → list[(timestamp, score)]
_dim_memory_store: dict[tuple[str, str, str], list[tuple[float, float]]] = {}


def _dim_redis_key(project_id: str, judge_model: str, dimension: str) -> str:
    safe_pid = project_id.replace(":", "_")
    safe_model = judge_model.replace(":", "_")
    safe_dim = dimension.replace(":", "_")
    return f"judgedim:{safe_pid}:{safe_model}:{safe_dim}"


def _dim_record_redis(
    client,
    *,
    project_id: str,
    judge_model: str,
    dimension: str,
    score: float,
    now: float,
    window_seconds: int,
) -> list[tuple[float, float]]:
    """Append + prune in Redis. Returns the post-prune sample list."""
    key = _dim_redis_key(project_id, judge_model, dimension)
    member = json.dumps({"t": now, "s": score}, separators=(",", ":"))
    cutoff = now - window_seconds
    try:
        pipe = client.pipeline()
        pipe.zadd(key, {member: now})
        pipe.zremrangebyscore(key, "-inf", cutoff)
        pipe.expire(key, window_seconds * 2)
        pipe.zrange(key, 0, -1)
        results = pipe.execute()
    except Exception:  # noqa: BLE001
        logger.warning(
            "judge_calibration: redis dim pipeline failed; falling back to memory"
        )
        return _dim_record_memory(
            project_id=project_id,
            judge_model=judge_model,
            dimension=dimension,
            score=score,
            now=now,
            window_seconds=window_seconds,
        )
    samples: list[tuple[float, float]] = []
    for raw in results[-1] or []:
        try:
            obj = json.loads(raw)
            samples.append((float(obj["t"]), float(obj["s"])))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    samples.sort(key=lambda x: x[0])
    return samples


def _dim_record_memory(
    *,
    project_id: str,
    judge_model: str,
    dimension: str,
    score: float,
    now: float,
    window_seconds: int,
) -> list[tuple[float, float]]:
    """Append + prune in the process-local dict."""
    key = (project_id, judge_model, dimension)
    cutoff = now - window_seconds
    with _memory_lock:
        bucket = _dim_memory_store.setdefault(key, [])
        bucket.append((now, score))
        _dim_memory_store[key] = [s for s in bucket if s[0] >= cutoff]
        return list(_dim_memory_store[key])


def _dim_read_samples(
    *,
    project_id: str,
    judge_model: str,
    dimension: str,
    window_seconds: int,
) -> list[tuple[float, float]]:
    """Read without writing. Used by compute_dimension_drift()."""
    now = time.time()
    cutoff = now - window_seconds
    client = _redis_client()
    if client is not None:
        key = _dim_redis_key(project_id, judge_model, dimension)
        try:
            client.zremrangebyscore(key, "-inf", cutoff)
            raws = client.zrange(key, 0, -1)
            out: list[tuple[float, float]] = []
            for raw in raws or []:
                try:
                    obj = json.loads(raw)
                    out.append((float(obj["t"]), float(obj["s"])))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
            out.sort(key=lambda x: x[0])
            return out
        except Exception:  # noqa: BLE001
            logger.warning(
                "judge_calibration: redis dim read failed; falling back to memory"
            )
    key2 = (project_id, judge_model, dimension)
    with _memory_lock:
        return [s for s in _dim_memory_store.get(key2, []) if s[0] >= cutoff]


def _evaluate_dimension(
    samples: list[tuple[float, float]],
    *,
    project_id: str,
    judge_model: str,
    dimension: str,
) -> DimensionDriftStatus:
    n = len(samples)
    if n == 0:
        return DimensionDriftStatus(
            project_id=project_id,
            judge_model=judge_model,
            dimension=dimension,
            sample_count=0,
            older_mean=0.0,
            recent_mean=0.0,
            drift=0.0,
            threshold=_DIMENSION_DRIFT_THRESHOLD,
            breached=False,
        )
    # Split by sample count into older-half / recent-half. We split exactly
    # in half (n // 2) so each side is balanced regardless of sample cadence.
    half = n // 2
    if half == 0:
        # Only 1 sample — no drift can be measured yet.
        return DimensionDriftStatus(
            project_id=project_id,
            judge_model=judge_model,
            dimension=dimension,
            sample_count=n,
            older_mean=samples[0][1],
            recent_mean=samples[0][1],
            drift=0.0,
            threshold=_DIMENSION_DRIFT_THRESHOLD,
            breached=False,
        )
    older = samples[:half]
    recent = samples[half:]
    older_mean = sum(s for _, s in older) / len(older)
    recent_mean = sum(s for _, s in recent) / len(recent)
    drift = older_mean - recent_mean  # positive => degradation
    breached = (
        len(older) >= _DIMENSION_MIN_SAMPLES_PER_HALF
        and len(recent) >= _DIMENSION_MIN_SAMPLES_PER_HALF
        and drift > _DIMENSION_DRIFT_THRESHOLD
    )
    return DimensionDriftStatus(
        project_id=project_id,
        judge_model=judge_model,
        dimension=dimension,
        sample_count=n,
        older_mean=round(older_mean, 4),
        recent_mean=round(recent_mean, 4),
        drift=round(drift, 4),
        threshold=_DIMENSION_DRIFT_THRESHOLD,
        breached=breached,
    )


def record_dimension_sample(
    *,
    project_id: str,
    judge_model: str,
    dimension: str,
    score: float,
) -> DimensionDriftStatus:
    """Record one (dimension, score) sample. Returns post-record drift status.

    Score must be in [0.0, 1.0]; out-of-range values are clamped. The
    same window-hours setting governs both verdict-level and dimension-level
    samples — keeps the operational story simple.

    Best-effort: silent no-op (returns zeroed status) when any required
    argument is missing or empty.
    """
    s = get_settings()
    pid = (project_id or "").strip()
    model = (judge_model or "").strip()
    dim = (dimension or "").strip()
    if not pid or not model or not dim:
        return DimensionDriftStatus(
            project_id=pid,
            judge_model=model,
            dimension=dim,
            sample_count=0,
            older_mean=0.0,
            recent_mean=0.0,
            drift=0.0,
            threshold=_DIMENSION_DRIFT_THRESHOLD,
            breached=False,
        )

    try:
        clamped = max(0.0, min(1.0, float(score)))
    except (TypeError, ValueError):
        return DimensionDriftStatus(
            project_id=pid,
            judge_model=model,
            dimension=dim,
            sample_count=0,
            older_mean=0.0,
            recent_mean=0.0,
            drift=0.0,
            threshold=_DIMENSION_DRIFT_THRESHOLD,
            breached=False,
        )

    window_seconds = max(1, int(s.JUDGE_CALIBRATION_WINDOW_HOURS) * 3600)
    now = time.time()

    client = _redis_client()
    if client is not None:
        samples = _dim_record_redis(
            client,
            project_id=pid,
            judge_model=model,
            dimension=dim,
            score=clamped,
            now=now,
            window_seconds=window_seconds,
        )
    else:
        samples = _dim_record_memory(
            project_id=pid,
            judge_model=model,
            dimension=dim,
            score=clamped,
            now=now,
            window_seconds=window_seconds,
        )

    status = _evaluate_dimension(
        samples, project_id=pid, judge_model=model, dimension=dim
    )
    if status.breached:
        logger.warning(
            "judge_dimension_drift_alert project=%s model=%s dim=%s "
            "older=%.3f recent=%.3f drift=%.3f threshold=%.3f n=%d",
            status.project_id,
            status.judge_model,
            status.dimension,
            status.older_mean,
            status.recent_mean,
            status.drift,
            status.threshold,
            status.sample_count,
        )
        # Per-dim alerts share the verdict-level callback registry. Callers
        # that want to differentiate can inspect type(status).
        _fire_callbacks(status)  # type: ignore[arg-type]
    return status


def compute_dimension_drift(
    project_id: str, judge_model: str, dimension: str
) -> DimensionDriftStatus:
    """Compute the current per-dimension drift without recording a sample."""
    s = get_settings()
    pid = (project_id or "").strip()
    model = (judge_model or "").strip()
    dim = (dimension or "").strip()
    window_seconds = max(1, int(s.JUDGE_CALIBRATION_WINDOW_HOURS) * 3600)
    samples = _dim_read_samples(
        project_id=pid,
        judge_model=model,
        dimension=dim,
        window_seconds=window_seconds,
    )
    return _evaluate_dimension(
        samples, project_id=pid, judge_model=model, dimension=dim
    )


__all__ = [
    "DriftStatus",
    "DimensionDriftStatus",
    "record_sample",
    "compute_drift",
    "record_dimension_sample",
    "compute_dimension_drift",
    "register_alert_callback",
    "clear_all",
]
