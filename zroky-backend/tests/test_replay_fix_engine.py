"""Tests for replay_fix_engine — replay-driven auto-fix engine (Module 10 advanced).

Coverage:
  * Pattern detection (_detect_pattern) — hallucination, format_drift,
    model_degradation, mixed
  * LLM fix generation (_generate_fix_with_llm / _parse_fix_json) —
    happy path, unparseable JSON, missing fields, advisory_only
  * analyze_and_generate_fix — skip when run passes, skip when no
    failing traces, generates suggestion with confidence >= floor
  * Mocked LLM client injection via monkeypatch.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import (
    Call,
    GoldenTrace,
    ReplayRun,
    ReplayRunTrace,
)
from app.services.replay_fix_engine import (
    RegressionPattern,
    TraceFailure,
    _FIX_CONFIDENCE_FLOOR,
    _build_analysis_input,
    _detect_pattern,
    _generate_fix_with_llm,
    _parse_fix_json,
    analyze_and_generate_fix,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_replay_fix.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def mock_llm_client(monkeypatch: pytest.MonkeyPatch):
    """Install a fake LLM client that returns a controllable JSON response."""
    _last_messages: list[dict[str, str]] = []

    class _FakeClient:
        def __init__(self, response_json: dict[str, Any] | None = None) -> None:
            self._response_json = response_json or {
                "fix_type": "prompt_tweak",
                "confidence": 0.92,
                "regression_summary": "model started emitting markdown instead of JSON",
                "reasoning": "Adding an explicit JSON format instruction should restore schema compliance.",
                "proposed_prompt_body": "You are a helpful assistant. Respond ONLY in valid JSON.",
            }

        def chat_completions_create(self, *, model, messages, **kwargs):
            _last_messages.clear()
            _last_messages.extend(messages)
            return self._make_resp()

        def _make_resp(self):
            raw = json.dumps(self._response_json)

            class _Msg:
                content = raw

            class _Choice:
                message = _Msg()

            class _Resp:
                choices = [_Choice()]

            return _Resp()

    def _install(response_json: dict[str, Any] | None = None):
        from app.services import llm_client as llm_module

        client = _FakeClient(response_json)
        monkeypatch.setattr(llm_module, "get_llm_client", lambda: client)
        return client, _last_messages

    return _install


# ── helpers ────────────────────────────────────────────────────────────────


def _seed_failing_replay(
    session,
    *,
    project_id: str = "p1",
    run_id: str = "run-1",
    replay_mode: str = "real_llm",
    candidate_prompt_override: str | None = "new prompt",
    status: str = "fail",
    fail_count: int = 3,
    trace_count: int = 5,
) -> ReplayRun:
    summary = {
        "trace_count_at_dispatch": trace_count,
        "trace_count_executed": trace_count,
        "pass_count": trace_count - fail_count,
        "fail_count": fail_count,
        "error_count": 0,
        "replay_mode": replay_mode,
        "candidate_prompt_override": candidate_prompt_override,
        "candidate_model_override": None,
    }
    run = ReplayRun(
        id=run_id,
        project_id=project_id,
        golden_set_id="gs-x",
        trigger="manual",
        status=status,
        summary_json=json.dumps(summary, separators=(",", ":")),
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _seed_trace(
    session,
    *,
    run: ReplayRun,
    trace_id: str,
    status: str = "fail",
    verdict: str = "fail",
    expected: str = "expected output",
    actual: str = "actual output",
    reason: str = "exact_mismatch",
    confidence: float = 0.85,
    model: str | None = None,
) -> ReplayRunTrace:
    gt = GoldenTrace(
        id=f"gt-{trace_id}",
        project_id=run.project_id,
        golden_set_id=run.golden_set_id,
        call_id="c-orig",
        expected_output_text=expected,
    )
    session.add(gt)
    session.commit()
    session.refresh(gt)

    call = Call(
        id=f"c-replayed-{trace_id}",
        project_id=run.project_id,
        event_id=f"evt-{trace_id}",
        provider="openrouter",
        model=model or "claude-3-haiku",
        status="success",
        payload_json=json.dumps({"prompt": "orig prompt", "model": model or "claude-3-haiku"}),
    )
    session.add(call)
    session.commit()
    session.refresh(call)

    rrt = ReplayRunTrace(
        id=trace_id,
        project_id=run.project_id,
        replay_run_id=run.id,
        golden_trace_id=gt.id,
        call_id_replayed=call.id,
        output_text=actual,
        status=status,
        judge_scores_json=json.dumps(
            {
                "verdict": verdict,
                "confidence": confidence,
                "reason": reason,
                "model": model or "claude-3-haiku",
            },
            separators=(",", ":"),
        ),
    )
    session.add(rrt)
    session.commit()
    session.refresh(rrt)
    return rrt


# ── pattern detection ───────────────────────────────────────────────────────


class TestPatternDetection:
    def test_hallucination_pattern(self) -> None:
        traces = [
            TraceFailure(
                trace_id="t1",
                call_id=None,
                expected_output="foo",
                actual_output="bar with hallucination signal",
                verdict="fail",
                confidence=0.9,
                reason="hallucination detected",
                model="gpt-4",
                judge_scores={},
            ),
            TraceFailure(
                trace_id="t2",
                call_id=None,
                expected_output="foo",
                actual_output="baz with fabricated detail",
                verdict="fail",
                confidence=0.8,
                reason="fabricated content",
                model="gpt-4",
                judge_scores={},
            ),
        ]
        pattern = _detect_pattern(traces)
        assert pattern.pattern_type == "hallucination"
        assert pattern.affected_trace_count == 2
        assert pattern.confidence > 0.8

    def test_format_drift_pattern(self) -> None:
        traces = [
            TraceFailure(
                trace_id=f"t{i}",
                call_id=None,
                expected_output="foo",
                actual_output="bar",
                verdict="fail",
                confidence=0.9,
                reason="exact_mismatch",
                model="gpt-4",
                judge_scores={},
            )
            for i in range(5)
        ]
        pattern = _detect_pattern(traces)
        assert pattern.pattern_type == "format_drift"
        assert pattern.affected_trace_count == 5

    def test_model_degradation_pattern(self) -> None:
        traces = [
            TraceFailure(
                trace_id=f"t{i}",
                call_id=None,
                expected_output="foo",
                actual_output="bar",
                verdict="fail",
                confidence=0.6,
                reason="semantic_drift",
                model="gpt-4",
                judge_scores={},
            )
            for i in range(4)
        ]
        pattern = _detect_pattern(traces)
        assert pattern.pattern_type == "model_degradation"
        assert pattern.affected_trace_count == 4

    def test_mixed_pattern(self) -> None:
        traces = [
            TraceFailure(
                trace_id="t1",
                call_id=None,
                expected_output="foo",
                actual_output="bar",
                verdict="fail",
                confidence=0.5,
                reason="timeout",
                model="claude",
                judge_scores={},
            ),
            TraceFailure(
                trace_id="t2",
                call_id=None,
                expected_output="foo",
                actual_output="baz",
                verdict="fail",
                confidence=0.5,
                reason="unknown",
                model="gpt-4",
                judge_scores={},
            ),
        ]
        pattern = _detect_pattern(traces)
        assert pattern.pattern_type == "mixed"

    def test_no_traces(self) -> None:
        pattern = _detect_pattern([])
        assert pattern.pattern_type == "none"


# ── analysis input builder ────────────────────────────────────────────────


class TestAnalysisInputBuilder:
    def test_includes_run_summary_and_traces(self) -> None:
        traces = [
            TraceFailure(
                trace_id="t1",
                call_id=None,
                expected_output="exp",
                actual_output="act",
                verdict="fail",
                confidence=0.9,
                reason="exact_mismatch",
                model="gpt-4",
                judge_scores={},
            )
        ]
        pattern = RegressionPattern(
            pattern_type="format_drift",
            description="all traces drifted",
            affected_trace_count=1,
            confidence=0.9,
        )
        inp = _build_analysis_input(
            failing_traces=traces,
            pattern=pattern,
            candidate_prompt_override="new prompt",
            candidate_model_override=None,
            run_summary={"trace_count_executed": 5, "pass_count": 2, "fail_count": 3, "error_count": 0},
        )
        assert "format_drift" in inp
        assert "new prompt" in inp
        assert "Trace 1" in inp
        assert "Expected" in inp
        assert "Actual" in inp


# ── LLM fix generation ──────────────────────────────────────────────────────


class TestGenerateFixWithLlm:
    def test_happy_path_returns_fix(self, mock_llm_client) -> None:
        mock_llm_client()
        analysis_input = "some analysis"
        fix = _generate_fix_with_llm(analysis_input)
        assert fix is not None
        assert fix.fix_type == "prompt_tweak"
        assert fix.confidence == 0.92
        assert fix.has_patch is True
        assert "regression_summary" in fix.evidence
        assert fix.evidence["proposed_prompt_body"] == "You are a helpful assistant. Respond ONLY in valid JSON."

    def test_model_swap(self, mock_llm_client) -> None:
        mock_llm_client(
            response_json={
                "fix_type": "model_swap",
                "confidence": 0.88,
                "regression_summary": "model too slow",
                "reasoning": "Swap to faster model.",
                "proposed_model": "gpt-4o-mini",
            }
        )
        fix = _generate_fix_with_llm("analysis")
        assert fix is not None
        assert fix.fix_type == "model_swap"
        assert fix.has_patch is True
        assert fix.evidence["proposed_model"] == "gpt-4o-mini"
        assert fix.evidence["config_path"] == "config/model.yaml"

    def test_advisory_only_no_patch(self, mock_llm_client) -> None:
        mock_llm_client(
            response_json={
                "fix_type": "advisory_only",
                "confidence": 0.5,
                "regression_summary": "unclear root cause",
                "reasoning": "Need more data.",
            }
        )
        fix = _generate_fix_with_llm("analysis")
        assert fix is not None
        assert fix.fix_type == "advisory_only"
        assert fix.has_patch is False

    def test_llm_failure_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services import llm_client as llm_module

        class _Boom:
            def chat_completions_create(self, **kwargs):
                raise RuntimeError("provider down")

        monkeypatch.setattr(llm_module, "get_llm_client", lambda: _Boom())
        fix = _generate_fix_with_llm("analysis")
        assert fix is None


# ── parse fix JSON ─────────────────────────────────────────────────────────


class TestParseFixJson:
    def test_valid_json(self) -> None:
        data = {
            "fix_type": "prompt_tweak",
            "confidence": 0.85,
            "regression_summary": "summary",
            "reasoning": "reason",
            "proposed_prompt_body": "new prompt",
        }
        fix = _parse_fix_json(json.dumps(data))
        assert fix is not None
        assert fix.fix_type == "prompt_tweak"
        assert fix.confidence == 0.85

    def test_markdown_fence_stripping(self) -> None:
        raw = "```json\n" + json.dumps({
            "fix_type": "prompt_revert",
            "confidence": 0.9,
            "regression_summary": "summary",
            "reasoning": "reason",
            "proposed_prompt_body": "old prompt",
        }) + "\n```"
        fix = _parse_fix_json(raw)
        assert fix is not None
        assert fix.fix_type == "prompt_revert"

    def test_missing_proposed_prompt_returns_none(self) -> None:
        data = {
            "fix_type": "prompt_tweak",
            "confidence": 0.9,
            "regression_summary": "summary",
            "reasoning": "reason",
        }
        fix = _parse_fix_json(json.dumps(data))
        assert fix is None

    def test_unparseable_returns_none(self) -> None:
        fix = _parse_fix_json("not json at all")
        assert fix is None

    def test_unknown_fix_type_becomes_advisory(self) -> None:
        data = {
            "fix_type": "magic_wand",
            "confidence": 0.7,
            "regression_summary": "summary",
            "reasoning": "reason",
        }
        fix = _parse_fix_json(json.dumps(data))
        assert fix is not None
        assert fix.fix_type == "advisory_only"


# ── end-to-end analyze_and_generate_fix ─────────────────────────────────────


class TestAnalyzeAndGenerateFix:
    def test_skips_when_run_passes(self, db_session) -> None:
        run = _seed_failing_replay(db_session, status="pass", fail_count=0, trace_count=3)
        result = analyze_and_generate_fix(db_session, replay_run=run)
        assert result is None

    def test_skips_when_no_failing_traces(self, db_session) -> None:
        run = _seed_failing_replay(db_session, status="fail", fail_count=2, trace_count=3)
        # Intentionally NOT seeding ReplayRunTrace rows
        result = analyze_and_generate_fix(db_session, replay_run=run)
        assert result is None

    def test_generates_fix_when_traces_fail(self, db_session, mock_llm_client) -> None:
        run = _seed_failing_replay(
            db_session,
            status="fail",
            fail_count=2,
            trace_count=3,
            candidate_prompt_override="new prompt",
        )
        _seed_trace(
            db_session,
            run=run,
            trace_id="t1",
            expected="expected 1",
            actual="actual 1",
            reason="exact_mismatch",
        )
        _seed_trace(
            db_session,
            run=run,
            trace_id="t2",
            expected="expected 2",
            actual="actual 2",
            reason="exact_mismatch",
        )
        mock_llm_client()
        result = analyze_and_generate_fix(db_session, replay_run=run)
        assert result is not None
        assert result.confidence >= _FIX_CONFIDENCE_FLOOR
        assert result.has_patch is True
        assert "regression_summary" in result.regression_summary or result.regression_summary

    def test_returns_none_when_low_confidence(self, db_session, mock_llm_client) -> None:
        run = _seed_failing_replay(db_session, status="fail", fail_count=1, trace_count=2)
        _seed_trace(db_session, run=run, trace_id="t1")
        mock_llm_client(
            response_json={
                "fix_type": "prompt_tweak",
                "confidence": 0.3,
                "regression_summary": "summary",
                "reasoning": "reason",
                "proposed_prompt_body": "new prompt",
            }
        )
        result = analyze_and_generate_fix(db_session, replay_run=run)
        assert result is None  # filtered by confidence floor
