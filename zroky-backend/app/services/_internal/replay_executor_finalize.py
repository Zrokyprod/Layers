from app.services._internal.replay_executor_common import *
from app.services._internal.replay_executor_diff import (
    _aggregate_trace_proof,
    _source_failure_signal,
)

def _mark_running(db: Session, run: ReplayRun) -> None:
    run.status = _RUN_RUNNING
    run.started_at = datetime.now(timezone.utc)
    db.add(run)
    db.commit()
    db.refresh(run)


def _finalize(
    db: Session,
    run: ReplayRun,
    *,
    counts: dict[str, int],
    total: int,
    budget_tracker: Optional[ReplayBudgetTracker] = None,
    calibration_meta: Optional[dict] = None,
) -> ReplayRun:
    """Apply pass/fail/error decision rule + write summary."""
    pass_n = int(counts.get("pass", 0))
    fail_n = int(counts.get("fail", 0))
    error_n = int(counts.get("error", 0))

    # Decision rule (locked):
    #   any fail              → run = fail
    #   no fail, any error    → run = error
    #   all pass (or empty)   → run = pass
    if fail_n > 0:
        final = _RUN_FAIL
    elif error_n > 0:
        final = _RUN_ERROR
    else:
        final = _RUN_PASS

    # Preserve any existing trace_count_at_dispatch snapshot from
    # dispatch_replay_run for dashboard progress rendering.
    existing = _safe_json_object(run.summary_json)
    replay_mode = str(
        existing.get("requested_replay_mode")
        or existing.get("replay_mode")
        or REPLAY_MODE_STUB
    )
    proof = _aggregate_trace_proof(db, run_id=run.id, project_id=run.project_id)
    tool_missing = int(
        proof.get("tool_behavior_diff", {}).get("missing_count") or 0
    ) > 0
    tool_proof_required = replay_mode in {
        REPLAY_MODE_MOCKED_TOOL,
        REPLAY_MODE_LIVE_SANDBOX,
    }
    verified_fix = (
        replay_mode in REAL_COMPARISON_REPLAY_MODES
        and final == _RUN_PASS
        and not (tool_proof_required and tool_missing)
    )
    if replay_mode == REPLAY_MODE_STUB:
        verification_status = "sanity_check_only"
    elif verified_fix:
        verification_status = "verified_fix"
    elif final == _RUN_PASS and tool_proof_required and tool_missing:
        verification_status = "real_comparison_missing_tool_proof"
    elif final == _RUN_ERROR:
        verification_status = "real_comparison_error"
    else:
        verification_status = "real_comparison_failed"
    reproduced_original_failure = (
        None
        if replay_mode == REPLAY_MODE_STUB
        else _source_failure_signal(db, run=run, existing=existing)
    )
    summary = {
        **existing,
        "trace_count_at_dispatch": existing.get(
            "trace_count_at_dispatch", total
        ),
        "trace_count_executed": total,
        "pass_count": pass_n,
        "fail_count": fail_n,
        "error_count": error_n,
        "reproduced_original_failure": reproduced_original_failure,
        "fix_passed": final == _RUN_PASS,
        "verified_fix": verified_fix,
        "verification_status": verification_status,
    }
    summary.update(proof)
    # Option B — surface cumulative replay spend so the dashboard can
    # show "This run cost $0.34 in live LLM calls".
    if budget_tracker is not None:
        summary["replay_cost_usd"] = round(budget_tracker.spent_usd, 8)
    # Calibration snapshot — attach accuracy + mode so the run summary also
    # carries the calibration context without a second API call.
    if calibration_meta:
        if calibration_meta.get("judge_accuracy_on_your_data") is not None:
            summary["judge_accuracy_on_your_data"] = calibration_meta["judge_accuracy_on_your_data"]
        if calibration_meta.get("judge_mode") is not None:
            summary["judge_mode"] = calibration_meta["judge_mode"]
    run.status = final
    run.completed_at = datetime.now(timezone.utc)
    run.summary_json = json.dumps(summary, separators=(",", ":"))
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "replay_executor.finalized run=%s status=%s pass=%d fail=%d error=%d",
        run.id, final, pass_n, fail_n, error_n,
    )
    return run


def _finalize_error(
    db: Session, run: ReplayRun, *, reason: str
) -> ReplayRun:
    """Short-circuit fatal-error finalize (no traces graded)."""
    existing = _safe_json_object(run.summary_json)
    replay_mode = str(
        existing.get("requested_replay_mode")
        or existing.get("replay_mode")
        or REPLAY_MODE_STUB
    )
    reproduced_original_failure = (
        None
        if replay_mode == REPLAY_MODE_STUB
        else _source_failure_signal(db, run=run, existing=existing)
    )
    summary = {
        **existing,
        "trace_count_at_dispatch": existing.get("trace_count_at_dispatch", 0),
        "trace_count_executed": 0,
        "pass_count": 0,
        "fail_count": 0,
        "error_count": 0,
        "error_reason": reason,
        "reproduced_original_failure": reproduced_original_failure,
        "fix_passed": False,
        "verified_fix": False,
        "verification_status": "sanity_check_only"
        if replay_mode == REPLAY_MODE_STUB
        else "real_comparison_error",
    }
    run.status = _RUN_ERROR
    run.completed_at = datetime.now(timezone.utc)
    run.summary_json = json.dumps(summary, separators=(",", ":"))
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.warning(
        "replay_executor.finalized_error run=%s reason=%s", run.id, reason
    )
    return run


__all__ = [name for name in globals() if not name.startswith("__")]
