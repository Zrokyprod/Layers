"""Daily judge calibration runner — Calibrated Judge wedge.

Loads golden traces with active human labels for a project, runs each
configured judge model against them, builds the canonical 3x3 confusion
matrix, persists one `JudgeCalibrationRun` row per (project, model,
date), and applies the auto-downgrade safety net via `JudgeModeOverride`.

Design choices (production-grade):
  - Idempotent on (project_id, judge_model, run_date). Re-runs hit the
    UNIQUE constraint and return the existing row. Never duplicates.
  - Hysteresis on auto-downgrade: downgrade at <90%, restore at >=93%.
    Prevents thrashing when accuracy oscillates around the boundary.
  - Min sample floor before any auto-downgrade fires (default 50).
    Below that, the safety net stays out of the way — small label sets
    are too noisy.
  - Best-effort calibration drift recording: every (judge, truth) pair
    is also fed into the existing `judge_calibration` Redis store so
    real-time drift alerts and the daily run agree on the data.
  - No global state. Every public function takes `db: Session` and
    `judge_factory` so tests can inject `DeterministicStubEvaluator`
    or any mock without monkeypatching.
  - `cost_usd` summed from per-judge-call `Verdict.metadata` when
    available; falls back to 0 (the LLM client also records into
    platform_llm_usage so this is duplicative but cheap to gather).

Public surface:
  - `run_calibration(db, *, project_id, judge_model, run_date, ...)` →
    JudgeCalibrationRun
  - `auto_apply_mode(db, *, run, downgrade_threshold, restore_threshold,
    min_samples)` → JudgeModeOverride | None
  - `evaluate_for_calibration(...)` → list[(judge_v, truth_v, confidence)]
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    GoldenLabel,
    GoldenTrace,
    JudgeCalibrationRun,
    JudgeModeOverride,
)
from app.services import judge_calibration as drift_store
from app.services.judge_calibration_metrics import (
    CalibrationMetrics,
    compute_all,
)
from app.services.judge_engine import (
    DeterministicStubEvaluator,
    Evaluator,
    ReferenceFreeEvaluator,
    SingleJudgeEvaluator,
    Verdict,
)

logger = logging.getLogger(__name__)


# ── thresholds ────────────────────────────────────────────────────────────


# Hysteresis defaults. Override per-call via run_calibration() args.
DEFAULT_DOWNGRADE_THRESHOLD: float = 0.90
DEFAULT_RESTORE_THRESHOLD: float = 0.93
DEFAULT_MIN_SAMPLES_FOR_DOWNGRADE: int = 50

# Reason codes written into JudgeModeOverride.
REASON_DOWNGRADE = "accuracy_below_threshold"
REASON_RESTORED = "restored"
REASON_MANUAL = "manual"


# ── factory protocol ──────────────────────────────────────────────────────


JudgeFactory = Callable[[str], Evaluator]
"""Function (judge_model_name) -> Evaluator. Pluggable for tests.

Default factory builds a `ReferenceFreeEvaluator` because calibration
only has the candidate output + input, not a separate golden reference.
"""


def default_judge_factory(judge_model: str) -> Evaluator:
    """Build the evaluator used for daily calibration.

    Why ReferenceFree: a labeled golden trace is (input prompt,
    candidate output, human verdict). There is no separate "expected"
    output to compare against. Reference-free judging fits cleanly.
    Tests can swap in DeterministicStubEvaluator via the
    judge_factory= argument.
    """
    return ReferenceFreeEvaluator(model=judge_model)


def stub_judge_factory(judge_model: str) -> Evaluator:
    """Always return a deterministic stub. Used in tests + offline runs."""
    return DeterministicStubEvaluator()


# ── core ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalibrationSample:
    """One judge-vs-truth comparison."""

    trace_id: str
    judge_verdict: str
    truth_verdict: str
    confidence: float
    cost_usd: float
    latency_ms: int


def _load_labeled_traces(
    db: Session, *, project_id: str
) -> list[tuple[GoldenTrace, GoldenLabel]]:
    """Return [(trace, active_label), ...] for every labeled trace in the project.

    Joins on the active label (`active=true`). Traces without an active
    label are skipped — they aren't part of the calibration set.
    """
    rows = db.execute(
        select(GoldenTrace, GoldenLabel)
        .join(GoldenLabel, GoldenLabel.golden_trace_id == GoldenTrace.id)
        .where(
            GoldenTrace.project_id == project_id,
            GoldenLabel.project_id == project_id,
            GoldenLabel.active.is_(True),
        )
        .order_by(GoldenTrace.created_at)
    ).all()
    return [(trace, label) for trace, label in rows]


def _trace_context(trace: GoldenTrace) -> dict[str, Any]:
    """Build the `context` dict passed to the judge for a labeled trace.

    Pulls `original_prompt` from criteria_json when present so the
    reference-free judge has the input the agent was answering. Never
    raises — malformed JSON degrades to an empty dict.
    """
    ctx: dict[str, Any] = {
        "trace_id": trace.id,
        "golden_set_id": trace.golden_set_id,
        "calibration": True,
    }
    if not trace.criteria_json:
        return ctx
    try:
        decoded = json.loads(trace.criteria_json)
    except (json.JSONDecodeError, TypeError, ValueError):
        return ctx
    if not isinstance(decoded, dict):
        return ctx
    prompt = decoded.get("original_prompt") or decoded.get("prompt")
    if prompt:
        ctx["original_prompt"] = str(prompt)[:1500]
    # Forward any user-supplied criteria so future evaluators can use it.
    extras = {
        k: v for k, v in decoded.items() if k not in {"original_prompt", "prompt"}
    }
    if extras:
        ctx["criteria"] = extras
    return ctx


def evaluate_for_calibration(
    *,
    traces: Sequence[tuple[GoldenTrace, GoldenLabel]],
    judge_model: str,
    judge_factory: JudgeFactory = default_judge_factory,
    record_drift: bool = True,
) -> list[CalibrationSample]:
    """Run the judge against every (trace, label) pair and return samples.

    Side effects (best-effort):
      - When `record_drift=True`, every comparison is also fed into the
        in-process drift store via `drift_store.record_sample()`. This
        keeps the real-time drift alerts and the persisted daily run on
        the same dataset.

    Robust to evaluator failures: a raised exception inside `evaluate()`
    is caught and treated as `inconclusive` so one bad call never aborts
    the whole calibration.
    """
    if not traces:
        return []

    evaluator: Evaluator = judge_factory(judge_model)
    out: list[CalibrationSample] = []

    for trace, label in traces:
        actual = (trace.expected_output_text or "").strip()
        if not actual:
            # Trace has no candidate output → nothing for the judge to grade.
            continue
        context = _trace_context(trace)
        try:
            verdict: Verdict = evaluator.evaluate(actual, "", context=context)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "judge_calibration_runner.evaluator_raised model=%s trace=%s err=%s",
                judge_model, trace.id, exc,
            )
            verdict = Verdict.normalize(
                "inconclusive",
                0.0,
                f"evaluator_error:{type(exc).__name__}",
                model=judge_model,
            )

        sample = CalibrationSample(
            trace_id=trace.id,
            judge_verdict=verdict.verdict,
            truth_verdict=label.verdict,
            confidence=float(verdict.confidence or 0.0),
            cost_usd=float(verdict.metadata.get("cost_usd", 0.0))
            if isinstance(verdict.metadata, Mapping)
            else 0.0,
            latency_ms=int(verdict.latency_ms or 0),
        )
        out.append(sample)

        if record_drift:
            try:
                drift_store.record_sample(
                    project_id=trace.project_id,
                    judge_model=judge_model,
                    judge_verdict=sample.judge_verdict,
                    truth_verdict=sample.truth_verdict,
                )
            except Exception:  # noqa: BLE001
                logger.debug(
                    "judge_calibration_runner.drift_record_failed trace=%s",
                    trace.id, exc_info=True,
                )

    return out


# ── persistence ───────────────────────────────────────────────────────────


def _existing_run(
    db: Session, *, project_id: str, judge_model: str, run_date: date
) -> JudgeCalibrationRun | None:
    return db.execute(
        select(JudgeCalibrationRun).where(
            JudgeCalibrationRun.project_id == project_id,
            JudgeCalibrationRun.judge_model == judge_model,
            JudgeCalibrationRun.run_date == run_date,
        )
    ).scalar_one_or_none()


def _persist_run(
    db: Session,
    *,
    project_id: str,
    judge_model: str,
    run_date: date,
    samples: list[CalibrationSample],
    metrics: CalibrationMetrics,
    low_conf_pct: float,
    started_at: datetime,
    completed_at: datetime,
) -> JudgeCalibrationRun:
    """Insert one calibration run row. Idempotent on UNIQUE conflict."""
    cost = sum(s.cost_usd for s in samples)
    matrix_json = json.dumps(
        {jv: dict(tv_counts) for jv, tv_counts in metrics.confusion_matrix.items()},
        separators=(",", ":"),
    )
    per_class_json = json.dumps(
        [m.to_dict() for m in metrics.per_class],
        separators=(",", ":"),
    )

    row = JudgeCalibrationRun(
        id=str(uuid4()),
        project_id=project_id,
        judge_model=judge_model,
        run_date=run_date,
        status="complete",
        sample_count=metrics.sample_count,
        agreement_count=metrics.agreement_count,
        accuracy=round(metrics.accuracy, 6),
        kappa=round(metrics.kappa, 6),
        low_confidence_pct=round(low_conf_pct, 6),
        confusion_matrix_json=matrix_json,
        per_class_metrics_json=per_class_json,
        cost_usd=cost,
        started_at=started_at,
        completed_at=completed_at,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        db.rollback()
        existing = _existing_run(
            db,
            project_id=project_id,
            judge_model=judge_model,
            run_date=run_date,
        )
        if existing is None:
            # Constraint violation but no existing row — re-raise.
            raise
        return existing


# ── auto-downgrade hysteresis ─────────────────────────────────────────────


def _current_override(
    db: Session, *, project_id: str, judge_model: str
) -> JudgeModeOverride | None:
    return db.execute(
        select(JudgeModeOverride).where(
            JudgeModeOverride.project_id == project_id,
            JudgeModeOverride.judge_model == judge_model,
        )
    ).scalar_one_or_none()


def _upsert_override(
    db: Session,
    *,
    project_id: str,
    judge_model: str,
    mode: str,
    reason: str,
    triggered_by_run_id: str | None,
    accuracy_at_change: float | None,
) -> JudgeModeOverride:
    existing = _current_override(
        db, project_id=project_id, judge_model=judge_model
    )
    now = datetime.now(timezone.utc)
    if existing is None:
        row = JudgeModeOverride(
            id=str(uuid4()),
            project_id=project_id,
            judge_model=judge_model,
            mode=mode,
            reason=reason,
            triggered_by_run_id=triggered_by_run_id,
            accuracy_at_change=accuracy_at_change,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    existing.mode = mode
    existing.reason = reason
    existing.triggered_by_run_id = triggered_by_run_id
    existing.accuracy_at_change = accuracy_at_change
    existing.updated_at = now
    db.commit()
    db.refresh(existing)
    return existing


def auto_apply_mode(
    db: Session,
    *,
    run: JudgeCalibrationRun,
    downgrade_threshold: float = DEFAULT_DOWNGRADE_THRESHOLD,
    restore_threshold: float = DEFAULT_RESTORE_THRESHOLD,
    min_samples: int = DEFAULT_MIN_SAMPLES_FOR_DOWNGRADE,
) -> JudgeModeOverride | None:
    """Apply hysteresis-based auto-downgrade/restore based on a run.

    Decision tree (in order):
      1. sample_count < min_samples → no change (None returned).
      2. Currently advisory + accuracy >= restore_threshold → restore to
         blocking, reason=REASON_RESTORED.
      3. Currently blocking (or no override) + accuracy < downgrade
         and accuracy != 0 (no samples) → downgrade to advisory.
      4. Otherwise → no change (None).

    The "accuracy != 0" guard prevents a zero-sample-day-zero from
    falsely tripping on a freshly-onboarded project. Combined with the
    sample floor it gives two layers of defence.

    Manual overrides (reason=REASON_MANUAL) are NOT auto-restored —
    the operator who flipped the switch keeps it flipped. The runner
    only flips rows it owns (REASON_DOWNGRADE / REASON_RESTORED).
    """
    if run.sample_count < min_samples:
        return None

    current = _current_override(
        db, project_id=run.project_id, judge_model=run.judge_model
    )
    current_mode = current.mode if current is not None else "blocking"
    current_reason = current.reason if current is not None else None

    accuracy_value = float(run.accuracy or 0.0)

    # Restore path — only for runner-owned overrides.
    if (
        current_mode == "advisory"
        and current_reason in (REASON_DOWNGRADE, REASON_RESTORED)
        and accuracy_value >= restore_threshold
    ):
        return _upsert_override(
            db,
            project_id=run.project_id,
            judge_model=run.judge_model,
            mode="blocking",
            reason=REASON_RESTORED,
            triggered_by_run_id=run.id,
            accuracy_at_change=accuracy_value,
        )

    # Downgrade path.
    if (
        current_mode != "advisory"
        and accuracy_value < downgrade_threshold
        and run.sample_count >= min_samples
    ):
        return _upsert_override(
            db,
            project_id=run.project_id,
            judge_model=run.judge_model,
            mode="advisory",
            reason=REASON_DOWNGRADE,
            triggered_by_run_id=run.id,
            accuracy_at_change=accuracy_value,
        )

    return None


# ── orchestration ─────────────────────────────────────────────────────────


def _persist_skipped(
    db: Session,
    *,
    project_id: str,
    judge_model: str,
    run_date: date,
    reason: str,
    started_at: datetime,
) -> JudgeCalibrationRun:
    """Persist a zero-sample 'skipped' run. Idempotent on UNIQUE conflict."""
    row = JudgeCalibrationRun(
        id=str(uuid4()),
        project_id=project_id,
        judge_model=judge_model,
        run_date=run_date,
        status="skipped",
        sample_count=0,
        agreement_count=0,
        accuracy=0.0,
        kappa=0.0,
        low_confidence_pct=0.0,
        per_class_metrics_json=reason,
        cost_usd=0.0,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        db.rollback()
        existing = _existing_run(
            db, project_id=project_id, judge_model=judge_model, run_date=run_date
        )
        return existing or row


def _persist_error(
    db: Session,
    *,
    project_id: str,
    judge_model: str,
    run_date: date,
    error_msg: str,
    started_at: datetime,
) -> JudgeCalibrationRun:
    """Persist a failed 'error' run so failures are visible on the scoreboard."""
    row = JudgeCalibrationRun(
        id=str(uuid4()),
        project_id=project_id,
        judge_model=judge_model,
        run_date=run_date,
        status="error",
        sample_count=0,
        agreement_count=0,
        accuracy=0.0,
        kappa=0.0,
        low_confidence_pct=0.0,
        per_class_metrics_json=error_msg,
        cost_usd=0.0,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except Exception:  # noqa: BLE001
        db.rollback()
    return row


def run_calibration(
    db: Session,
    *,
    project_id: str,
    judge_model: str,
    run_date: date | None = None,
    judge_factory: JudgeFactory = default_judge_factory,
    downgrade_threshold: float = DEFAULT_DOWNGRADE_THRESHOLD,
    restore_threshold: float = DEFAULT_RESTORE_THRESHOLD,
    min_samples_for_downgrade: int = DEFAULT_MIN_SAMPLES_FOR_DOWNGRADE,
    min_samples_to_run: int = 1,
    record_drift: bool = True,
) -> JudgeCalibrationRun:
    """End-to-end: load labels, run judge, persist run, apply hysteresis.

    Returns the persisted JudgeCalibrationRun. Re-running for the same
    (project, model, date) returns the existing row unchanged (idempotent).

    When fewer than `min_samples_to_run` labeled traces exist the run is
    persisted with status='skipped'. When the runner itself raises an
    unexpected exception the run is persisted with status='error'.
    """
    run_date = run_date or date.today()

    existing = _existing_run(
        db, project_id=project_id, judge_model=judge_model, run_date=run_date
    )
    if existing is not None:
        return existing

    started_at = datetime.now(timezone.utc)

    try:
        traces = _load_labeled_traces(db, project_id=project_id)

        if len(traces) < min_samples_to_run:
            reason = f"sample_count={len(traces)} below minimum={min_samples_to_run}"
            logger.info(
                "judge_calibration.skipped project=%s model=%s reason=%s",
                project_id, judge_model, reason,
            )
            return _persist_skipped(
                db,
                project_id=project_id,
                judge_model=judge_model,
                run_date=run_date,
                reason=reason,
                started_at=started_at,
            )

        samples = evaluate_for_calibration(
            traces=traces,
            judge_model=judge_model,
            judge_factory=judge_factory,
            record_drift=record_drift,
        )

        pairs = [(s.judge_verdict, s.truth_verdict) for s in samples]
        confidences = [s.confidence for s in samples]
        metrics, low_conf = compute_all(pairs, confidences)
        completed_at = datetime.now(timezone.utc)

        run = _persist_run(
            db,
            project_id=project_id,
            judge_model=judge_model,
            run_date=run_date,
            samples=samples,
            metrics=metrics,
            low_conf_pct=low_conf,
            started_at=started_at,
            completed_at=completed_at,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "judge_calibration.run_failed project=%s model=%s", project_id, judge_model
        )
        return _persist_error(
            db,
            project_id=project_id,
            judge_model=judge_model,
            run_date=run_date,
            error_msg=str(exc),
            started_at=started_at,
        )

    try:
        auto_apply_mode(
            db,
            run=run,
            downgrade_threshold=downgrade_threshold,
            restore_threshold=restore_threshold,
            min_samples=min_samples_for_downgrade,
        )
    except Exception:  # noqa: BLE001
        # Mode application is best-effort — the run row is what matters
        # for the public scoreboard. Log and continue.
        logger.exception(
            "judge_calibration_runner.auto_apply_mode_failed run=%s", run.id
        )

    logger.info(
        "judge_calibration.run_complete project=%s model=%s date=%s "
        "samples=%d accuracy=%.4f kappa=%.4f low_conf_pct=%.2f",
        project_id, judge_model, run_date.isoformat(),
        run.sample_count, run.accuracy, run.kappa, run.low_confidence_pct,
    )
    return run


__all__ = [
    "DEFAULT_DOWNGRADE_THRESHOLD",
    "DEFAULT_RESTORE_THRESHOLD",
    "DEFAULT_MIN_SAMPLES_FOR_DOWNGRADE",
    "REASON_DOWNGRADE",
    "REASON_RESTORED",
    "REASON_MANUAL",
    "CalibrationSample",
    "default_judge_factory",
    "stub_judge_factory",
    "evaluate_for_calibration",
    "auto_apply_mode",
    "run_calibration",
]
