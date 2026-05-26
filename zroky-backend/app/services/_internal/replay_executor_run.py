from app.services._internal.replay_executor_common import *
from app.services._internal.replay_executor_live import *
from app.services._internal.replay_executor_diff import *
from app.services._internal.replay_executor_finalize import *
from app.services._internal.replay_executor_grading import *

def execute_replay_run(
    db: Session,
    *,
    project_id: str,
    run_id: str,
    evaluator: Optional[Evaluator] = None,
    evaluator_factory: Optional[EvaluatorFactory] = None,
    actual_output_resolver: ActualOutputResolver = default_resolver,
    record_calibration: bool = False,
    max_traces: int = MAX_TRACES_PER_RUN,
    # Option B — real-LLM replay overrides + budget guard.
    candidate_prompt_override: Optional[str] = None,
    candidate_model_override: Optional[str] = None,
    budget_tracker: Optional[ReplayBudgetTracker] = None,
) -> Optional[ReplayRun]:
    """Execute a pending ReplayRun. Returns the updated run, or None if not found.

    Parameters
    ----------
    evaluator
        Pre-built Evaluator. Cheaper than constructing one per trace; pass
        this when calling from a context where you've already resolved the
        plan/entitlements (e.g. Celery worker).
    evaluator_factory
        Per-trace evaluator builder. Useful when criteria_json on different
        traces should pick different judges (e.g. a schema-shaped golden
        wants DeterministicStubEvaluator). Wins over `evaluator` when both
        are given.
    actual_output_resolver
        Hook for the customer-hosted worker. Default reads from source Call.
    record_calibration
        When True, runs a DeterministicStubEvaluator alongside the real judge
        and records the comparison as a calibration sample. Adds zero LLM
        cost but doubles in-process work; default False.

    Returns
    -------
    ReplayRun
        The updated run row (status = pass | fail | error). Returns None
        if no run with that (project_id, run_id) exists.

    Idempotency
    -----------
    Only pending runs are executed. Already-terminal runs are returned as-is.
    """
    run = db.execute(
        select(ReplayRun).where(
            ReplayRun.project_id == project_id,
            ReplayRun.id == run_id,
        )
    ).scalar_one_or_none()
    if run is None:
        return None

    if run.status != _RUN_PENDING:
        # Already running or terminal — do nothing. The dispatcher/route
        # treats this as success since the caller's intent (run got
        # scheduled) is satisfied by the row's existence.
        logger.info(
            "replay_executor.skip run=%s status=%s (non-pending)",
            run.id, run.status,
        )
        return run

    parent = db.execute(
        select(GoldenSet).where(
            GoldenSet.project_id == project_id,
            GoldenSet.id == run.golden_set_id,
        )
    ).scalar_one_or_none()
    if parent is None:
        # Parent set was deleted between dispatch and execute. Mark error.
        return _finalize_error(
            db, run, reason="golden_set_deleted"
        )

    traces = list(
        db.execute(
            select(GoldenTrace)
            .where(
                GoldenTrace.project_id == project_id,
                GoldenTrace.golden_set_id == run.golden_set_id,
            )
            .order_by(GoldenTrace.created_at.asc(), GoldenTrace.id.asc())
            .limit(max_traces + 1)
        ).scalars().all()
    )
    if len(traces) > max_traces:
        return _finalize_error(
            db, run,
            reason=f"too_many_traces (>{max_traces})",
        )
    if not traces:
        # Empty golden set — mark as pass with zero traces. The dashboard
        # already handles zero-trace runs gracefully.
        _mark_running(db, run)
        return _finalize(
            db, run,
            counts={"pass": 0, "fail": 0, "error": 0},
            total=0,
        )

    _mark_running(db, run)

    # Resolve calibration context once per run — cheap read, injected into
    # every trace's judge_scores_json as `judge_accuracy_on_your_data` + `judge_mode`.
    calibration_meta: dict | None = None
    _judge_model: str | None = None
    if evaluator is not None and hasattr(evaluator, "model"):
        _judge_model = getattr(evaluator, "model", None)
    if _judge_model:
        try:
            _mode_view = resolve_mode(db, project_id=project_id, judge_model=_judge_model)
            calibration_meta = {
                "judge_accuracy_on_your_data": _mode_view.accuracy,
                "judge_mode": _mode_view.mode,
                "judge_sample_count": _mode_view.sample_count,
                "judge_last_calibrated": _mode_view.last_run_date,
            }
        except Exception:  # noqa: BLE001
            logger.debug(
                "replay_executor.calibration_meta_failed run=%s", run.id, exc_info=True
            )

    counts = {"pass": 0, "fail": 0, "error": 0}
    for trace in traces:
        verdict_kind = _grade_trace(
            db,
            run=run,
            trace=trace,
            evaluator=evaluator,
            evaluator_factory=evaluator_factory,
            actual_output_resolver=actual_output_resolver,
            record_calibration=record_calibration,
            calibration_meta=calibration_meta,
        )
        counts[verdict_kind] = counts.get(verdict_kind, 0) + 1

    return _finalize(
        db, run,
        counts=counts,
        total=len(traces),
        budget_tracker=budget_tracker,
        calibration_meta=calibration_meta,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
