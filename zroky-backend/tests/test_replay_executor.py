"""
Tests for `app/services/replay_executor.py` (Module 8; plan §6.4).

Coverage:
  - execute_replay_run end-to-end:
      * pending → running → pass when all traces match
      * pending → fail when any trace fails
      * pending → error when only inconclusive verdicts (no fail)
      * non-pending runs are returned unchanged (idempotency)
      * missing run returns None
      * deleted golden set finalizes the run as error
      * empty golden set passes with zero counts
      * trace cap (max_traces) finalizes the run as error
  - per-trace grading:
      * default_resolver reads source Call payload_json["response"]
      * source-call missing → trace recorded as error
      * resolver exceptions are caught and become error traces
      * evaluator override picks DeterministicStubEvaluator
      * evaluator_factory wins over evaluator
      * evaluator exceptions are caught and become inconclusive verdicts
      * trace_status mapping: pass / fail / error from inconclusive
      * judge_scores_json shape includes verdict/confidence/model/judges
      * output_text is bounded at 8000 chars
  - calibration sampling:
      * record_calibration=False writes no samples
      * record_calibration=True writes a sample only when stub == exact_match pass
      * stub fail/inconclusive does NOT record (would be too noisy)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import (
    Call,
    GoldenSet,
    GoldenTrace,
    ReplayRun,
    ReplayRunTrace,
)
from app.services import judge_calibration
from app.services.goldens import (
    GOLDEN_TRACE_STATUS_DRAFT,
    add_trace,
    create_golden_set,
)
from app.services.judge_engine import (
    DeterministicStubEvaluator,
    Evaluator,
    VERDICT_FAIL,
    VERDICT_PASS,
    Verdict,
)
from app.services.replay_executor import (
    ActualOutput,
    ReplayBudgetTracker,
    _estimate_llm_cost,
    default_resolver,
    execute_replay_run,
    make_live_llm_resolver,
)
from app.services.replay_runs import (
    REPLAY_MODE_LIVE_SANDBOX,
    REPLAY_MODE_MOCKED_TOOL,
    REPLAY_MODE_REAL_LLM,
    dispatch_replay_run,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_replay_executor.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def _isolate_calibration():
    judge_calibration._unregister_all_callbacks_for_tests()
    judge_calibration.clear_all()
    yield
    judge_calibration._unregister_all_callbacks_for_tests()
    judge_calibration.clear_all()


@pytest.fixture(autouse=True)
def _force_memory_calibration_store(monkeypatch):
    """Avoid touching a developer's local Redis."""
    monkeypatch.setattr(judge_calibration, "_redis_client", lambda: None)


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_call(
    db, *, project_id: str, call_id: str, response_text: str, model: str = "m/x",
    prompt: str = "p"
) -> Call:
    call = Call(
        id=call_id,
        project_id=project_id,
        event_id=f"evt-{call_id}",
        provider="openai",
        model=model,
        status="ok",
        agent_name="agent-1",
        latency_ms=120,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        cost_total=0.001,
        is_production=True,
        payload_json=json.dumps({
            "prompt": prompt,
            "response": response_text,
            "model": model,
        }),
    )
    db.add(call)
    db.commit()
    return call


def _seed_run_with_traces(
    db,
    *,
    project_id: str = "p1",
    expected_responses: list[str],
    actual_responses: list[str] | None = None,
) -> tuple[ReplayRun, list[GoldenTrace]]:
    """Build a golden set with len(expected_responses) traces, each backed by
    a Call whose response_text is `actual_responses[i]` (defaults to expected
    so the deterministic stub returns pass)."""
    if actual_responses is None:
        actual_responses = list(expected_responses)
    assert len(expected_responses) == len(actual_responses)
    gs = create_golden_set(
        db,
        project_id=project_id,
        name="Test set",
        description=None,
    )
    traces: list[GoldenTrace] = []
    for i, (expected, actual) in enumerate(zip(expected_responses, actual_responses)):
        call = _make_call(
            db,
            project_id=project_id,
            call_id=f"call-{i}",
            response_text=actual,
        )
        t = add_trace(
            db,
            project_id=project_id,
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text=expected,
            expected_tokens=30,
            expected_cost_usd=0.001,
            expected_latency_ms=120,
            criteria_json='{"allow_empty_expected":true}' if expected == "" else None,
            weight=1.0,
        )
        assert t is not None
        traces.append(t)
    run = dispatch_replay_run(
        db,
        project_id=project_id,
        golden_set_id=gs.id,
        trigger="manual",
    )
    assert run is not None
    return run, traces


class _ScriptedEvaluator(Evaluator):
    """Returns a fixed verdict regardless of input."""

    name = "scripted"

    def __init__(self, verdict: str, confidence: float = 1.0, reason: str = "scripted") -> None:
        self._v = Verdict.normalize(verdict, confidence, reason, model="scripted-judge")

    def evaluate(self, actual, expected, *, context=None):  # type: ignore[override]
        return self._v


class _RaisingEvaluator(Evaluator):
    name = "raising"

    def evaluate(self, actual, expected, *, context=None):  # type: ignore[override]
        raise RuntimeError("evaluator boom")


# ── default_resolver ─────────────────────────────────────────────────────────


class TestDefaultResolver:
    def test_reads_response_from_payload(self, db_session) -> None:
        call = _make_call(
            db_session,
            project_id="p1",
            call_id="c1",
            response_text="actual response",
        )
        # Build a minimal trace pointing at the call.
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text="exp",
            expected_tokens=None,
            expected_cost_usd=None,
            expected_latency_ms=None,
            criteria_json=None,
            weight=1.0,
        )
        out = default_resolver(trace, call)
        assert out.text == "actual response"
        assert out.model == "m/x"
        assert out.reason is None

    def test_missing_call_returns_reason(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=None,
            expected_output_text="exp",
            expected_tokens=None,
            expected_cost_usd=None,
            expected_latency_ms=None,
            criteria_json=None,
            weight=1.0,
        )
        out = default_resolver(trace, None)
        assert out.text is None
        assert out.reason == "source_call_missing"

    def test_missing_response_field_returns_reason(self, db_session) -> None:
        call = Call(
            id="c-empty",
            project_id="p1",
            event_id="evt-empty",
            provider="x",
            model="m",
            status="ok",
            payload_json=json.dumps({"prompt": "p"}),  # no response
            is_production=True,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cost_total=0.0,
        )
        db_session.add(call)
        db_session.commit()
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id="c-empty",
            expected_output_text="exp",
            expected_tokens=None,
            expected_cost_usd=None,
            expected_latency_ms=None,
            criteria_json=None,
            weight=1.0,
        )
        out = default_resolver(trace, call)
        assert out.text is None
        assert out.reason == "source_call_missing_response"


# ── execute_replay_run end-to-end ────────────────────────────────────────────


class TestExecuteReplayRun:
    def test_all_pass_finalizes_pass(self, db_session) -> None:
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["a", "b", "c"]
        )
        updated = execute_replay_run(
            db_session,
            project_id=run.project_id,
            run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
        )
        assert updated is not None
        assert updated.status == "pass"
        assert updated.completed_at is not None
        summary = json.loads(updated.summary_json)
        assert summary["pass_count"] == 3
        assert summary["fail_count"] == 0
        assert summary["error_count"] == 0
        assert summary["trace_count_executed"] == 3
        assert summary["verification_status"] == "sanity_check_only"
        assert summary["verified_fix"] is False
        assert summary["fix_passed"] is True

        traces = db_session.execute(
            select(ReplayRunTrace).where(ReplayRunTrace.replay_run_id == run.id)
        ).scalars().all()
        assert len(traces) == 3
        assert all(t.status == "pass" for t in traces)
        for t in traces:
            scores = json.loads(t.judge_scores_json)
            assert scores["verdict"] == "pass"

    def test_draft_traces_are_not_executed(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="p1", name="draft-skip")
        active_call = _make_call(
            db_session,
            project_id="p1",
            call_id="call-active",
            response_text="approved",
        )
        active_trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=active_call.id,
            expected_output_text="approved",
        )
        draft_call = _make_call(
            db_session,
            project_id="p1",
            call_id="call-draft",
            response_text="observed only",
        )
        draft_trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=draft_call.id,
        )
        assert active_trace is not None
        assert draft_trace is not None
        assert draft_trace.status == GOLDEN_TRACE_STATUS_DRAFT

        run = dispatch_replay_run(
            db_session, project_id="p1", golden_set_id=gs.id, trigger="manual"
        )
        assert run is not None
        assert json.loads(run.summary_json)["trace_count_at_dispatch"] == 1

        updated = execute_replay_run(
            db_session,
            project_id="p1",
            run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
        )

        assert updated is not None
        assert updated.status == "pass"
        summary = json.loads(updated.summary_json)
        assert summary["trace_count_executed"] == 1
        traces = db_session.execute(
            select(ReplayRunTrace).where(ReplayRunTrace.replay_run_id == run.id)
        ).scalars().all()
        assert len(traces) == 1
        assert traces[0].golden_trace_id == active_trace.id

    def test_any_fail_finalizes_fail(self, db_session) -> None:
        run, _ = _seed_run_with_traces(
            db_session,
            expected_responses=["a", "b", "c"],
            actual_responses=["a", "WRONG", "c"],
        )
        updated = execute_replay_run(
            db_session,
            project_id=run.project_id,
            run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
        )
        assert updated is not None
        assert updated.status == "fail"
        summary = json.loads(updated.summary_json)
        assert summary["pass_count"] == 2
        assert summary["fail_count"] == 1
        assert summary["error_count"] == 0

    def test_only_inconclusive_finalizes_not_verified(self, db_session) -> None:
        # Use empty expected_output_text so deterministic stub returns
        # inconclusive for every trace.
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["", "", ""]
        )
        updated = execute_replay_run(
            db_session,
            project_id=run.project_id,
            run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
        )
        assert updated is not None
        assert updated.status == "not_verified"
        summary = json.loads(updated.summary_json)
        assert summary["not_verified_count"] == 3
        assert summary["error_count"] == 0
        assert summary["pass_count"] == 0
        assert summary["fail_count"] == 0

    def test_missing_run_returns_none(self, db_session) -> None:
        out = execute_replay_run(
            db_session, project_id="p1", run_id="run-does-not-exist"
        )
        assert out is None

    def test_non_pending_run_returns_unchanged(self, db_session) -> None:
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["a"]
        )
        # Manually flip to pass.
        run.status = "pass"
        db_session.add(run)
        db_session.commit()
        out = execute_replay_run(
            db_session,
            project_id=run.project_id,
            run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
        )
        # Should be returned as-is; no traces written.
        assert out is not None
        assert out.status == "pass"
        traces = db_session.execute(
            select(ReplayRunTrace).where(ReplayRunTrace.replay_run_id == run.id)
        ).scalars().all()
        assert len(traces) == 0

    def test_idempotent_on_running_status(self, db_session) -> None:
        """Re-entering execute on a running row is a no-op (the executor
        only transitions pending→running). Catches double-dispatch races."""
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["a"]
        )
        run.status = "running"
        db_session.add(run)
        db_session.commit()
        out = execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
        )
        assert out is not None
        assert out.status == "running"
        traces = db_session.execute(
            select(ReplayRunTrace).where(ReplayRunTrace.replay_run_id == run.id)
        ).scalars().all()
        assert len(traces) == 0

    def test_deleted_golden_set_finalizes_error(self, db_session) -> None:
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["a"]
        )
        # Delete the parent set out from under us.
        db_session.execute(
            GoldenSet.__table__.delete().where(GoldenSet.id == run.golden_set_id)
        )
        db_session.commit()
        out = execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
        )
        assert out is not None
        assert out.status == "error"
        summary = json.loads(out.summary_json)
        assert summary["error_reason"] == "golden_set_deleted"

    def test_empty_golden_set_passes(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="p1", name="empty")
        run = dispatch_replay_run(
            db_session, project_id="p1", golden_set_id=gs.id, trigger="manual"
        )
        assert run is not None
        out = execute_replay_run(
            db_session, project_id="p1", run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
        )
        assert out is not None
        assert out.status == "pass"
        summary = json.loads(out.summary_json)
        assert summary["trace_count_executed"] == 0

    def test_trace_cap_finalizes_error(self, db_session) -> None:
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["a", "b", "c"]
        )
        out = execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
            max_traces=2,  # cap below the 3 we seeded
        )
        assert out is not None
        assert out.status == "error"
        summary = json.loads(out.summary_json)
        assert "too_many_traces" in summary["error_reason"]

    def test_real_replay_from_issue_marks_verified_fix(self, db_session) -> None:
        run, _ = _seed_run_with_traces(db_session, expected_responses=["fixed"])
        summary = json.loads(run.summary_json)
        summary["replay_mode"] = REPLAY_MODE_REAL_LLM
        summary["requested_replay_mode"] = REPLAY_MODE_REAL_LLM
        summary["source_issue_id"] = "issue-1"
        summary["source_issue_failure_code"] = "SCHEMA_VIOLATION"
        run.summary_json = json.dumps(summary, separators=(",", ":"))
        db_session.add(run)
        db_session.commit()

        out = execute_replay_run(
            db_session,
            project_id=run.project_id,
            run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
            actual_output_resolver=lambda trace, _call: ActualOutput(
                text=trace.expected_output_text,
                model="gpt-4o",
            ),
        )

        assert out is not None
        assert out.status == "pass"
        updated_summary = json.loads(out.summary_json)
        assert updated_summary["reproduced_original_failure"] is True
        assert updated_summary["fix_passed"] is True
        assert updated_summary["verified_fix"] is True
        assert updated_summary["verification_status"] == "verified_fix"


# ── per-trace grading details ────────────────────────────────────────────────


class TestPerTraceGrading:
    def test_evaluator_factory_wins_over_evaluator(self, db_session) -> None:
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["a"]
        )
        # Factory always returns a "fail" judgement; plain evaluator says
        # pass. Factory must win.
        out = execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=_ScriptedEvaluator(VERDICT_PASS),
            evaluator_factory=lambda _t: _ScriptedEvaluator(VERDICT_FAIL),
        )
        assert out is not None
        assert out.status == "fail"

    def test_no_evaluator_uses_deterministic_stub(self, db_session) -> None:
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["a"]
        )
        out = execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id
        )
        assert out is not None
        assert out.status == "pass"
        traces = db_session.execute(
            select(ReplayRunTrace).where(ReplayRunTrace.replay_run_id == run.id)
        ).scalars().all()
        scores = json.loads(traces[0].judge_scores_json)
        assert scores["model"] == "deterministic_stub"

    def test_evaluator_exception_becomes_error_trace(self, db_session) -> None:
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["a"]
        )
        out = execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=_RaisingEvaluator(),
        )
        assert out is not None
        # The judge raised → inconclusive → error trace → run = error.
        assert out.status == "error"
        traces = db_session.execute(
            select(ReplayRunTrace).where(ReplayRunTrace.replay_run_id == run.id)
        ).scalars().all()
        assert len(traces) == 1
        assert traces[0].status == "error"
        scores = json.loads(traces[0].judge_scores_json)
        assert scores["verdict"] == "inconclusive"
        assert "evaluator_error" in scores["reason"]

    def test_resolver_exception_becomes_error_trace(self, db_session) -> None:
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["a"]
        )

        def _boom(trace, call):  # noqa: ARG001
            raise RuntimeError("resolver kaput")

        out = execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
            actual_output_resolver=_boom,
        )
        assert out is not None
        assert out.status == "error"
        traces = db_session.execute(
            select(ReplayRunTrace).where(ReplayRunTrace.replay_run_id == run.id)
        ).scalars().all()
        assert traces[0].status == "error"
        scores = json.loads(traces[0].judge_scores_json)
        assert "resolver_error" in scores["reason"]

    def test_resolver_returns_none_text_becomes_not_verified(self, db_session) -> None:
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["a"]
        )
        out = execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
            actual_output_resolver=lambda t, c: ActualOutput(
                text=None, reason="custom_no_output"
            ),
        )
        assert out is not None
        assert out.status == "not_verified"
        traces = db_session.execute(
            select(ReplayRunTrace).where(ReplayRunTrace.replay_run_id == run.id)
        ).scalars().all()
        assert traces[0].status == "not_verified"
        scores = json.loads(traces[0].judge_scores_json)
        assert scores["reason"] == "custom_no_output"

    def test_output_text_capped_at_8000(self, db_session) -> None:
        long_text = "x" * 12_000
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=[long_text]
        )
        out = execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=DeterministicStubEvaluator(),
        )
        assert out is not None
        traces = db_session.execute(
            select(ReplayRunTrace).where(ReplayRunTrace.replay_run_id == run.id)
        ).scalars().all()
        assert traces[0].output_text is not None
        assert len(traces[0].output_text) == 8000

    def test_judge_scores_json_includes_ensemble_judges(self, db_session) -> None:
        from app.services.judge_engine import EnsembleEvaluator

        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["a"]
        )
        ev = EnsembleEvaluator(
            [_ScriptedEvaluator(VERDICT_PASS, 0.9, "alpha"),
             _ScriptedEvaluator(VERDICT_PASS, 0.7, "beta")]
        )
        out = execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=ev,
        )
        assert out is not None
        traces = db_session.execute(
            select(ReplayRunTrace).where(ReplayRunTrace.replay_run_id == run.id)
        ).scalars().all()
        scores = json.loads(traces[0].judge_scores_json)
        assert scores["model"] == "ensemble:2"
        assert "judges" in scores
        assert len(scores["judges"]) == 2


# ── calibration sampling ─────────────────────────────────────────────────────


class TestCalibrationSampling:
    def test_calibration_off_writes_no_samples(self, db_session) -> None:
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["a"]
        )
        execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=_ScriptedEvaluator(VERDICT_PASS),
            record_calibration=False,
        )
        st = judge_calibration.compute_drift("p1", "scripted-judge")
        assert st.sample_count == 0

    def test_calibration_on_records_pass_when_stub_exact_match(
        self, db_session
    ) -> None:
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["matching"]
        )
        execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=_ScriptedEvaluator(VERDICT_PASS),
            record_calibration=True,
        )
        st = judge_calibration.compute_drift("p1", "scripted-judge")
        assert st.sample_count == 1
        # Both judge and truth said pass → no disagreement.
        assert st.disagreement_count == 0

    def test_calibration_records_judge_disagreement(self, db_session) -> None:
        # Stub says pass (exact match); judge says fail → counted as
        # disagreement.
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=["matching"]
        )
        execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=_ScriptedEvaluator(VERDICT_FAIL),
            record_calibration=True,
        )
        st = judge_calibration.compute_drift("p1", "scripted-judge")
        assert st.sample_count == 1
        assert st.disagreement_count == 1

    def test_calibration_skips_when_stub_inconclusive(self, db_session) -> None:
        # Empty expected → stub returns inconclusive → no sample.
        run, _ = _seed_run_with_traces(
            db_session, expected_responses=[""]
        )
        execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=_ScriptedEvaluator(VERDICT_PASS),
            record_calibration=True,
        )
        st = judge_calibration.compute_drift("p1", "scripted-judge")
        assert st.sample_count == 0

    def test_calibration_skips_when_stub_fails(self, db_session) -> None:
        # Mismatched outputs → stub fails → no sample (too noisy).
        run, _ = _seed_run_with_traces(
            db_session,
            expected_responses=["expected"],
            actual_responses=["actual"],
        )
        execute_replay_run(
            db_session, project_id=run.project_id, run_id=run.id,
            evaluator=_ScriptedEvaluator(VERDICT_PASS),
            record_calibration=True,
        )
        st = judge_calibration.compute_drift("p1", "scripted-judge")
        assert st.sample_count == 0


# ── Option B: budget tracker ─────────────────────────────────────────────────


class TestReplayBudgetTracker:
    def test_can_spend_within_budget(self) -> None:
        bt = ReplayBudgetTracker(budget_usd=1.0)
        assert bt.can_spend(estimated_usd=0.5) is True
        bt.record_spend(0.5)
        assert bt.can_spend(estimated_usd=0.4) is True
        assert bt.can_spend(estimated_usd=0.1) is True
        # 0.5 + 0.5 = 1.0 → still allowed (exactly at cap)
        assert bt.can_spend(estimated_usd=0.5) is True
        # 0.5 + 0.50000001 > 1.0 → blocked
        assert bt.can_spend(estimated_usd=0.50000001) is False

    def test_zero_budget_blocks_all(self) -> None:
        bt = ReplayBudgetTracker(budget_usd=0.0)
        assert bt.can_spend() is False
        assert bt.can_spend(estimated_usd=0.0) is False

    def test_negative_budget_normalised_to_zero(self) -> None:
        bt = ReplayBudgetTracker(budget_usd=-5.0)
        assert bt.can_spend() is False

    def test_record_spend_accumulates(self) -> None:
        bt = ReplayBudgetTracker(budget_usd=10.0)
        bt.record_spend(1.5)
        bt.record_spend(2.5)
        assert bt.spent_usd == 4.0


# ── Option B: cost estimation ────────────────────────────────────────────────


class TestEstimateLlmCost:
    def test_known_model(self) -> None:
        # gpt-4o @ 1M in + 500K out
        cost = _estimate_llm_cost("gpt-4o", 1_000_000, 500_000)
        # in=5.0, out=15.0 per 1M
        assert cost == pytest.approx(5.0 + 7.5, abs=0.01)

    def test_known_model_with_provider_prefix(self) -> None:
        cost = _estimate_llm_cost("openai/gpt-4o-mini", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.15 + 0.6, abs=0.01)

    def test_unknown_model_uses_fallback(self) -> None:
        cost = _estimate_llm_cost("some-unknown-model", 1_000_000, 1_000_000)
        assert cost == pytest.approx(5.0 + 15.0, abs=0.01)

    def test_zero_tokens(self) -> None:
        assert _estimate_llm_cost("gpt-4o", 0, 0) == 0.0


# ── Option B: live_llm_resolver ────────────────────────────────────────────


class TestLiveLlmResolver:
    def test_missing_call_returns_error(self, db_session) -> None:
        resolver = make_live_llm_resolver()
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=None,
            expected_output_text="exp",
        )
        out = resolver(trace, None)
        assert out.text is None
        assert out.reason == "source_call_missing"

    def test_missing_prompt_returns_error(self, db_session) -> None:
        call = Call(
            id="c-no-prompt",
            project_id="p1",
            event_id="evt-np",
            provider="x",
            model="m",
            status="ok",
            payload_json=json.dumps({"response": "r"}),
            is_production=True,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cost_total=0.0,
        )
        db_session.add(call)
        db_session.commit()
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text="exp",
        )
        resolver = make_live_llm_resolver()
        out = resolver(trace, call)
        assert out.text is None
        assert out.reason == "source_call_missing_prompt"

    def test_missing_model_returns_error(self, db_session) -> None:
        call = Call(
            id="c-no-model",
            project_id="p1",
            event_id="evt-nm",
            provider="x",
            model="",
            status="ok",
            payload_json=json.dumps({"prompt": "hi"}),
            is_production=True,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cost_total=0.0,
        )
        db_session.add(call)
        db_session.commit()
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text="exp",
        )
        resolver = make_live_llm_resolver()
        out = resolver(trace, call)
        assert out.text is None
        assert out.reason == "source_call_missing_model"

    def test_mocked_tool_requires_captured_tool_snapshot(self, db_session) -> None:
        call = _make_call(db_session, project_id="p1", call_id="c1", response_text="old")
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text="exp",
        )

        resolver = make_live_llm_resolver(replay_mode=REPLAY_MODE_MOCKED_TOOL)
        out = resolver(trace, call)

        assert out.text is None
        assert out.reason == "tool_snapshot_missing"
        assert out.metadata is not None
        assert out.metadata["tool_behavior_diff"]["available"] is False

    def test_mocked_tool_injects_frozen_tool_context(self, db_session, monkeypatch) -> None:
        call = _make_call(db_session, project_id="p1", call_id="c1", response_text="old")
        call.tool_lifecycle_summary_json = json.dumps(
            [{"tool_name": "refund_lookup", "tool_success": True}]
        )
        db_session.add(call)
        db_session.commit()
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text="exp",
        )

        captured_messages = []

        class _FakeClient:
            def chat_completions_create(self, *, model, messages, **kwargs):
                captured_messages.append(messages)

                class _U:
                    prompt_tokens = 1
                    completion_tokens = 1

                class _C:
                    class message:
                        content = "ok"

                class _R:
                    choices = [_C()]
                    usage = _U()

                return _R()

        monkeypatch.setattr(
            "app.services.llm_client.get_llm_client",
            lambda: _FakeClient(),
        )

        resolver = make_live_llm_resolver(replay_mode=REPLAY_MODE_MOCKED_TOOL)
        out = resolver(trace, call)

        assert out.text == "ok"
        assert "refund_lookup" in captured_messages[0][0]["content"]
        assert out.metadata is not None
        tool_diff = out.metadata["tool_behavior_diff"]
        assert tool_diff["available"] is True
        assert tool_diff["mode"] == "mocked_tool_frozen_outputs"

    def test_live_sandbox_fails_closed_without_runtime(self, db_session) -> None:
        call = _make_call(db_session, project_id="p1", call_id="c1", response_text="old")
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text="exp",
        )

        resolver = make_live_llm_resolver(replay_mode=REPLAY_MODE_LIVE_SANDBOX)
        out = resolver(trace, call)

        assert out.text is None
        assert out.reason == "sandbox_tool_runtime_unavailable"
        assert out.metadata is not None
        assert out.metadata["tool_behavior_diff"]["mode"] == "live_sandbox"

    def test_live_sandbox_calls_configured_worker(self, db_session, monkeypatch) -> None:
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "REPLAY_SANDBOX_WORKER_URL", "https://sandbox.zroky.test/replay")
        monkeypatch.setattr(settings, "REPLAY_SANDBOX_WORKER_TOKEN", "sandbox-secret")
        call = _make_call(db_session, project_id="p1", call_id="c1", response_text="old")
        call.tool_lifecycle_summary_json = json.dumps([{"tool_name": "lookup"}])
        db_session.add(call)
        db_session.commit()
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text="exp",
        )

        captured = {}

        class _FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "output_text": "sandbox output",
                    "model": "gpt-4o",
                    "latency_ms": 25,
                    "cost_usd": 0.002,
                    "input_tokens": 12,
                    "output_tokens": 4,
                    "tool_behavior_diff": {
                        "available": True,
                        "changed": True,
                        "mode": "live_sandbox",
                    },
                }

        def _fake_post(url, *, json, headers, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            captured["timeout"] = timeout
            return _FakeResponse()

        monkeypatch.setattr("httpx.post", _fake_post)

        resolver = make_live_llm_resolver(replay_mode=REPLAY_MODE_LIVE_SANDBOX)
        out = resolver(trace, call)

        assert out.text == "sandbox output"
        assert out.model == "gpt-4o"
        assert out.cost_total == pytest.approx(0.002)
        assert captured["url"] == "https://sandbox.zroky.test/replay"
        assert captured["headers"]["Authorization"] == "Bearer sandbox-secret"
        assert captured["json"]["tool_snapshot"] == [{"tool_name": "lookup"}]
        assert out.metadata is not None
        assert out.metadata["tool_behavior_diff"]["changed"] is True

    def test_calls_provider_and_returns_text(self, db_session, monkeypatch) -> None:
        call = _make_call(db_session, project_id="p1", call_id="c1", response_text="old")
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text="exp",
        )

        class _FakeUsage:
            prompt_tokens = 10
            completion_tokens = 5

        class _FakeChoice:
            class message:
                content = "new response"

        class _FakeResponse:
            choices = [_FakeChoice()]
            usage = _FakeUsage()

        client_calls = []

        class _FakeClient:
            def chat_completions_create(self, *, model, messages, **kwargs):
                client_calls.append((model, messages))
                return _FakeResponse()

        monkeypatch.setattr(
            "app.services.llm_client.get_llm_client",
            lambda: _FakeClient(),
        )

        resolver = make_live_llm_resolver()
        out = resolver(trace, call)
        assert out.text == "new response"
        assert out.model == "m/x"
        assert out.input_tokens == 10
        assert out.output_tokens == 5
        assert out.cost_total > 0
        assert len(client_calls) == 1
        assert client_calls[0][0] == "m/x"

    def test_applies_prompt_override(self, db_session, monkeypatch) -> None:
        call = _make_call(
            db_session, project_id="p1", call_id="c1", response_text="old", prompt="original"
        )
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text="exp",
        )

        captured_messages = []

        class _FakeClient:
            def chat_completions_create(self, *, model, messages, **kwargs):
                captured_messages.append(messages)
                class _U:
                    prompt_tokens = 1
                    completion_tokens = 1
                class _C:
                    class message:
                        content = "ok"
                class _R:
                    choices = [_C()]
                    usage = _U()
                return _R()

        monkeypatch.setattr(
            "app.services.llm_client.get_llm_client",
            lambda: _FakeClient(),
        )

        resolver = make_live_llm_resolver(candidate_prompt_override="overridden prompt")
        out = resolver(trace, call)
        assert out.text == "ok"
        assert captured_messages[0][0]["content"] == "overridden prompt"

    def test_applies_model_override(self, db_session, monkeypatch) -> None:
        call = _make_call(db_session, project_id="p1", call_id="c1", response_text="old")
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text="exp",
        )

        captured_model = []

        class _FakeClient:
            def chat_completions_create(self, *, model, messages, **kwargs):
                captured_model.append(model)
                class _U:
                    prompt_tokens = 1
                    completion_tokens = 1
                class _C:
                    class message:
                        content = "ok"
                class _R:
                    choices = [_C()]
                    usage = _U()
                return _R()

        monkeypatch.setattr(
            "app.services.llm_client.get_llm_client",
            lambda: _FakeClient(),
        )

        resolver = make_live_llm_resolver(candidate_model_override="gpt-4o")
        out = resolver(trace, call)
        assert out.text == "ok"
        assert captured_model[0] == "gpt-4o"

    def test_budget_exceeded_returns_error(self, db_session, monkeypatch) -> None:
        call = _make_call(db_session, project_id="p1", call_id="c1", response_text="old")
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text="exp",
        )

        tracker = ReplayBudgetTracker(budget_usd=0.0)
        resolver = make_live_llm_resolver(budget_tracker=tracker)
        out = resolver(trace, call)
        assert out.text is None
        assert out.reason == "budget_exceeded"

    def test_provider_error_returns_error(self, db_session, monkeypatch) -> None:
        call = _make_call(db_session, project_id="p1", call_id="c1", response_text="old")
        gs = create_golden_set(db_session, project_id="p1", name="ds")
        trace = add_trace(
            db_session,
            project_id="p1",
            golden_set_id=gs.id,
            call_id=call.id,
            expected_output_text="exp",
        )

        class _BoomClient:
            def chat_completions_create(self, **kwargs):
                raise RuntimeError("provider down")

        monkeypatch.setattr(
            "app.services.llm_client.get_llm_client",
            lambda: _BoomClient(),
        )

        resolver = make_live_llm_resolver()
        out = resolver(trace, call)
        assert out.text is None
        assert "provider_error" in out.reason
