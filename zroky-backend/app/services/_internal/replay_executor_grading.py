from app.services._internal.replay_executor_common import *
from app.services._internal.replay_executor_diff import *

def _grade_trace(
    db: Session,
    *,
    run: ReplayRun,
    trace: GoldenTrace,
    evaluator: Optional[Evaluator],
    evaluator_factory: Optional[EvaluatorFactory],
    actual_output_resolver: ActualOutputResolver,
    record_calibration: bool,
    calibration_meta: Optional[dict] = None,
) -> str:
    """Resolve actual, grade, persist a ReplayRunTrace. Returns the trace's status."""
    source_call: Optional[Call] = None
    if trace.call_id:
        source_call = db.execute(
            select(Call).where(
                Call.id == trace.call_id,
                Call.project_id == trace.project_id,
            )
        ).scalar_one_or_none()

    actual: ActualOutput
    try:
        actual = actual_output_resolver(trace, source_call)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "replay_executor.resolver_failed run=%s trace=%s err=%s",
            run.id, trace.id, exc,
        )
        actual = ActualOutput(text=None, reason=f"resolver_error:{type(exc).__name__}")

    if actual.text is None:
        trace_status = _resolver_reason_to_trace_status(actual.reason)
        return _write_trace_row(
            db,
            run=run,
            trace=trace,
            source_call=source_call,
            actual=actual,
            verdict=Verdict.normalize(
                VERDICT_INCONCLUSIVE,
                0.0,
                actual.reason or "no_actual_output",
                model="resolver",
            ),
            status=trace_status,
            call_id_replayed=source_call.id if source_call else None,
            calibration_meta=calibration_meta,
        )

    # Pick evaluator.
    chosen: Evaluator
    if evaluator_factory is not None:
        chosen = evaluator_factory(trace)
    elif evaluator is not None:
        chosen = evaluator
    else:
        # No evaluator supplied — pick a deterministic stub so the function
        # is callable without any LLM key. Callers that want real grading
        # should supply `evaluator=judge_engine.get_evaluator(...)`.
        chosen = DeterministicStubEvaluator()

    expected = trace.expected_output_text or ""
    context = _build_judge_context(trace=trace, source_call=source_call)

    try:
        verdict = chosen.evaluate(actual.text, expected, context=context)
    except Exception as exc:  # noqa: BLE001
        # Evaluator implementations promise not to raise; guard anyway.
        logger.warning(
            "replay_executor.evaluator_raised run=%s trace=%s err=%s",
            run.id, trace.id, exc,
        )
        verdict = Verdict.normalize(
            VERDICT_INCONCLUSIVE, 0.0, f"evaluator_error:{type(exc).__name__}"
        )

    # Optional calibration sample (deterministic-stub ground truth, only
    # when the stub is decisive on exact_match — i.e. a "pass" we can trust).
    if record_calibration:
        try:
            stub_verdict = DeterministicStubEvaluator().evaluate(
                actual.text, expected, context=context
            )
            # Only anchor calibration to confident stub passes; stub fail/
            # inconclusive verdicts are too noisy (paraphrased correct
            # answers would mass-trigger drift alerts).
            if (
                stub_verdict.verdict == VERDICT_PASS
                and stub_verdict.reason == "exact_match"
            ):
                judge_calibration.record_sample(
                    project_id=trace.project_id,
                    judge_model=verdict.model or "unknown",
                    judge_verdict=verdict.verdict,
                    truth_verdict=stub_verdict.verdict,
                )
        except Exception:  # noqa: BLE001
            logger.debug(
                "replay_executor.calibration_sample_failed run=%s trace=%s",
                run.id, trace.id, exc_info=True,
            )

    # Determine the persisted trace status. The judge's verdict is the
    # ground truth here: pass→pass, fail→fail, inconclusive→error.
    trace_status = _verdict_to_trace_status(verdict.verdict, reason=verdict.reason)
    return _write_trace_row(
        db,
        run=run,
        trace=trace,
        source_call=source_call,
        actual=actual,
        verdict=verdict,
        status=trace_status,
        call_id_replayed=source_call.id if source_call else None,
        calibration_meta=calibration_meta,
    )


def _verdict_to_trace_status(verdict: str, *, reason: Optional[str] = None) -> str:
    """Map judge verdict → replay_run_traces.status (CHECK = pass/fail/error)."""
    if verdict == VERDICT_PASS:
        return _TRACE_PASS
    if verdict == VERDICT_FAIL:
        return _TRACE_FAIL
    normalized = (reason or "").strip().lower()
    if normalized.startswith("evaluator_error:"):
        return _TRACE_ERROR
    return _TRACE_NOT_VERIFIED


def _resolver_reason_to_trace_status(reason: Optional[str]) -> str:
    """Map resolver no-output reasons to honest replay proof status."""
    normalized = (reason or "").strip().lower()
    if normalized.startswith("resolver_error:") or normalized.startswith("unexpected_error:"):
        return _TRACE_ERROR
    return _TRACE_NOT_VERIFIED


def _build_judge_context(
    *, trace: GoldenTrace, source_call: Optional[Call]
) -> dict[str, Any]:
    """Compose the `context` dict passed to evaluators."""
    ctx: dict[str, Any] = {
        "trace_id": trace.id,
        "golden_set_id": trace.golden_set_id,
    }
    if trace.criteria_json:
        criteria = _safe_json_object(trace.criteria_json)
        if criteria:
            ctx["criteria"] = criteria
    if source_call is not None:
        payload = _safe_json_object(source_call.payload_json)
        prompt = payload.get("prompt")
        if prompt:
            # Cap at 1500 chars; the judge prompt has its own caps too.
            ctx["original_prompt"] = str(prompt)[:1500]
        model = payload.get("model")
        if model:
            ctx["original_model"] = str(model)
    return ctx


def _write_trace_row(
    db: Session,
    *,
    run: ReplayRun,
    trace: GoldenTrace,
    source_call: Optional[Call],
    actual: ActualOutput,
    verdict: Verdict,
    status: str,
    call_id_replayed: Optional[str],
    calibration_meta: Optional[dict] = None,
) -> str:
    """Insert one ReplayRunTrace row and commit."""
    tool_behavior_diff = _build_tool_behavior_diff(
        source_call=source_call,
        actual=actual,
    )
    scores = {
        "verdict": verdict.verdict,
        "confidence": verdict.confidence,
        "reason": verdict.reason,
        "model": verdict.model,
        "latency_ms": verdict.latency_ms,
        "output_diff": _build_output_diff(
            expected=trace.expected_output_text or "",
            actual=actual.text or "",
        ),
        "tool_behavior_diff": tool_behavior_diff,
        "cost_delta_usd": round(actual.cost_total - float(trace.expected_cost_usd or 0.0), 8),
        "latency_delta_ms": actual.latency_ms - int(trace.expected_latency_ms or 0),
        # Option B — real-LLM replay telemetry per trace.
        "replay_cost_usd": round(actual.cost_total, 8),
        "replay_input_tokens": actual.input_tokens,
        "replay_output_tokens": actual.output_tokens,
    }
    if actual.metadata and isinstance(actual.metadata.get("rag_grounding_diff"), dict):
        scores["rag_grounding_diff"] = actual.metadata["rag_grounding_diff"]
    if actual.reason:
        scores["resolver_reason"] = actual.reason
    if actual.metadata:
        resolver_metadata = {
            key: value
            for key, value in actual.metadata.items()
            if key != "tool_behavior_diff"
        }
        if resolver_metadata:
            scores["resolver_metadata"] = resolver_metadata
    # Surface ensemble per-judge details and multi-dim scores if present.
    if verdict.metadata and isinstance(verdict.metadata, dict):
        # Keep judge_scores_json bounded — `judges` can grow with ensemble
        # size but is already capped at a few entries.
        meta_judges = verdict.metadata.get("judges")
        if meta_judges:
            scores["judges"] = meta_judges
        meta_dims = verdict.metadata.get("dimensions")
        if meta_dims:
            scores["dimensions"] = meta_dims
        overall = verdict.metadata.get("overall_score")
        if overall is not None:
            scores["overall_score"] = overall

    # Calibration context — attached when available so the dashboard and
    # regression-CI gate can show accuracy-on-your-data alongside every verdict.
    if calibration_meta:
        if calibration_meta.get("judge_accuracy_on_your_data") is not None:
            scores["judge_accuracy_on_your_data"] = calibration_meta["judge_accuracy_on_your_data"]
        if calibration_meta.get("judge_mode") is not None:
            scores["judge_mode"] = calibration_meta["judge_mode"]

    row = ReplayRunTrace(
        id=str(uuid4()),
        replay_run_id=run.id,
        golden_trace_id=trace.id,
        project_id=trace.project_id,
        call_id_replayed=call_id_replayed,
        judge_scores_json=json.dumps(scores, separators=(",", ":"), default=str),
        status=status,
        diff_metric=_simple_diff_metric(trace.expected_output_text or "", actual.text or ""),
        # Bound stored output text so big agent responses don't blow up the row.
        output_text=(actual.text[:8000] if actual.text else None),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    logger.debug(
        "replay_executor.trace_written run=%s trace=%s status=%s verdict=%s",
        run.id, trace.id, status, verdict.verdict,
    )
    return status


__all__ = [name for name in globals() if not name.startswith("__")]
