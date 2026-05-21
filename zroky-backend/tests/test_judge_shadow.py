"""
Tests for `app/services/judge_shadow.py` (Module 7.5 refactor).

Coverage:
  - should_run_shadow_judge eligibility checks:
      * ineligible failure_code → False
      * feature flag off (no row, off, tenant on disabled list) → False
      * feature flag on globally + tenant in disabled list → False
      * feature flag on per-tenant → True (when sample passes)
      * sample miss (rng > 0.01) → False
      * spend cap breached (>= 5%) → False
      * happy path → True
  - run_shadow_judge delegation to SingleJudgeEvaluator:
      * happy path returns dict with verdict/confidence/reason/model/latency_ms
      * LLM exception (via stub evaluator) → inconclusive verdict; never raises
      * calibration sample recorded with truth=fail
      * calibration record swallowed on storage failure (does not crash)
  - _build_user_prompt: prompt assembly truncates inputs at documented caps
  - judge_shadow's own integration with judge_engine SingleJudgeEvaluator:
      * system_prompt override is honored
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import FeatureFlag, PlatformLlmUsage
from app.services import judge_calibration, judge_shadow
from app.services.judge_engine import (
    SingleJudgeEvaluator,
    VERDICT_FAIL,
    VERDICT_INCONCLUSIVE,
    VERDICT_PASS,
    Verdict,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_judge_shadow.db"
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


# Convenience: a SingleJudgeEvaluator stub that returns a fixed Verdict.
class _StubEvaluator(SingleJudgeEvaluator):
    """Bypasses LLM calls and returns a pre-baked Verdict."""

    def __init__(self, verdict: Verdict) -> None:
        # Skip parent __init__ to avoid the model/system_prompt machinery
        # (we don't need them for the stub).
        self._stub_verdict = verdict
        self.model = verdict.model or "stub"

    def evaluate(self, actual, expected, *, context=None):  # type: ignore[override]
        return self._stub_verdict


def _enable_flag_for_tenant(db, tenant_id: str, *, globally: bool = False) -> None:
    flag = FeatureFlag(
        key="judge_shadow_enabled",
        enabled_globally=globally,
        enabled_tenants_json=json.dumps([] if globally else [tenant_id]),
        disabled_tenants_json="[]",
    )
    db.add(flag)
    db.commit()


# ── should_run_shadow_judge ──────────────────────────────────────────────────


class TestShouldRunShadowJudge:
    def test_ineligible_failure_code_returns_false(self, db_session) -> None:
        _enable_flag_for_tenant(db_session, "t1")
        out = judge_shadow.should_run_shadow_judge(
            db=db_session, tenant_id="t1", failure_code="UNRELATED",
            rng=random.Random(0),
        )
        assert out is False

    def test_no_flag_row_returns_false(self, db_session) -> None:
        # No FeatureFlag row at all → False even on eligible code.
        out = judge_shadow.should_run_shadow_judge(
            db=db_session, tenant_id="t1", failure_code="LOW_CONFIDENCE",
            rng=random.Random(0),
        )
        assert out is False

    def test_flag_disabled_globally_with_tenant_not_listed(
        self, db_session
    ) -> None:
        flag = FeatureFlag(
            key="judge_shadow_enabled",
            enabled_globally=False,
            enabled_tenants_json="[]",
            disabled_tenants_json="[]",
        )
        db_session.add(flag)
        db_session.commit()
        out = judge_shadow.should_run_shadow_judge(
            db=db_session, tenant_id="t1", failure_code="LOW_CONFIDENCE",
            rng=random.Random(0),
        )
        assert out is False

    def test_flag_global_on_with_tenant_in_disabled_list(self, db_session) -> None:
        flag = FeatureFlag(
            key="judge_shadow_enabled",
            enabled_globally=True,
            enabled_tenants_json="[]",
            disabled_tenants_json=json.dumps(["t1"]),
        )
        db_session.add(flag)
        db_session.commit()
        out = judge_shadow.should_run_shadow_judge(
            db=db_session, tenant_id="t1", failure_code="LOOP_DETECTED",
            rng=random.Random(0),
        )
        assert out is False

    def test_sample_miss_returns_false(self, db_session) -> None:
        _enable_flag_for_tenant(db_session, "t1")
        # Random.random() > 0.01 → fails sample.
        rng = random.Random()
        rng.random = lambda: 0.5  # type: ignore[method-assign]
        out = judge_shadow.should_run_shadow_judge(
            db=db_session, tenant_id="t1", failure_code="LOW_CONFIDENCE",
            rng=rng,
        )
        assert out is False

    def test_sample_hit_returns_true(self, db_session) -> None:
        _enable_flag_for_tenant(db_session, "t1")
        rng = random.Random()
        rng.random = lambda: 0.001  # type: ignore[method-assign]
        out = judge_shadow.should_run_shadow_judge(
            db=db_session, tenant_id="t1", failure_code="LOW_CONFIDENCE",
            rng=rng,
        )
        assert out is True

    def test_spend_cap_breach_returns_false(self, db_session) -> None:
        _enable_flag_for_tenant(db_session, "t1")
        # Inject usage rows where judge spend = 50% of total → above 5%.
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        db_session.add(PlatformLlmUsage(
            id="u1", purpose="prod", provider="openrouter",
            model="anthropic/claude-sonnet-4", cost_usd=10.0,
            tenant_id="t1", created_at=now,
        ))
        db_session.add(PlatformLlmUsage(
            id="u2", purpose="judge_shadow", provider="openrouter",
            model="openai/gpt-4o-mini", cost_usd=10.0,
            tenant_id="t1", created_at=now,
        ))
        db_session.commit()
        rng = random.Random()
        rng.random = lambda: 0.001  # type: ignore[method-assign]
        out = judge_shadow.should_run_shadow_judge(
            db=db_session, tenant_id="t1", failure_code="LOW_CONFIDENCE",
            rng=rng,
        )
        assert out is False

    def test_loop_detected_is_eligible(self, db_session) -> None:
        _enable_flag_for_tenant(db_session, "t1")
        rng = random.Random()
        rng.random = lambda: 0.001  # type: ignore[method-assign]
        out = judge_shadow.should_run_shadow_judge(
            db=db_session, tenant_id="t1", failure_code="LOOP_DETECTED",
            rng=rng,
        )
        assert out is True


# ── run_shadow_judge ─────────────────────────────────────────────────────────


class TestRunShadowJudge:
    def test_delegates_to_evaluator_and_returns_dict(self) -> None:
        verdict = Verdict.normalize(
            VERDICT_FAIL, 0.85, "loop confirmed",
            model="openai/gpt-4o-mini",
            latency_ms=120,
        )
        out = judge_shadow.run_shadow_judge(
            tenant_id="t1",
            call_id="c1",
            failure_code="LOOP_DETECTED",
            call_prompt="user prompt",
            call_response="model response",
            diagnosis_summary="loop pattern",
            evaluator=_StubEvaluator(verdict),
        )
        assert out == {
            "verdict": "fail",
            "confidence": 0.85,
            "reason": "loop confirmed",
            "model": "openai/gpt-4o-mini",
            "latency_ms": 120,
        }

    def test_pass_verdict_is_passed_through(self) -> None:
        v = Verdict.normalize(VERDICT_PASS, 0.9, "ok", model="m1")
        out = judge_shadow.run_shadow_judge(
            tenant_id="t1",
            call_id="c1",
            failure_code="LOW_CONFIDENCE",
            call_prompt=None, call_response=None, diagnosis_summary=None,
            evaluator=_StubEvaluator(v),
        )
        assert out["verdict"] == "pass"
        assert out["confidence"] == 0.9

    def test_inconclusive_verdict_is_passed_through(self) -> None:
        v = Verdict.normalize(VERDICT_INCONCLUSIVE, 0.0, "judge_error:Timeout", model="m1")
        out = judge_shadow.run_shadow_judge(
            tenant_id="t1", call_id="c1", failure_code="LOW_CONFIDENCE",
            call_prompt=None, call_response=None, diagnosis_summary=None,
            evaluator=_StubEvaluator(v),
        )
        assert out["verdict"] == "inconclusive"
        assert out["reason"] == "judge_error:Timeout"

    def test_records_calibration_sample_with_truth_fail(self) -> None:
        v = Verdict.normalize(VERDICT_PASS, 0.9, "ok", model="judge-x")
        judge_shadow.run_shadow_judge(
            tenant_id="t-cal",
            call_id="c1",
            failure_code="LOW_CONFIDENCE",
            call_prompt=None, call_response=None, diagnosis_summary=None,
            evaluator=_StubEvaluator(v),
        )
        # Judge said pass; deterministic detector said fail → disagreement.
        st = judge_calibration.compute_drift("t-cal", "judge-x")
        assert st.sample_count == 1
        assert st.disagreement_count == 1

    def test_calibration_no_disagreement_when_judge_agrees(self) -> None:
        v = Verdict.normalize(VERDICT_FAIL, 0.9, "confirmed", model="judge-x")
        judge_shadow.run_shadow_judge(
            tenant_id="t-cal2",
            call_id="c1",
            failure_code="LOW_CONFIDENCE",
            call_prompt=None, call_response=None, diagnosis_summary=None,
            evaluator=_StubEvaluator(v),
        )
        st = judge_calibration.compute_drift("t-cal2", "judge-x")
        assert st.sample_count == 1
        assert st.disagreement_count == 0

    def test_calibration_failure_does_not_crash(self, monkeypatch) -> None:
        """If judge_calibration.record_sample raises, run_shadow_judge must
        still return the verdict cleanly."""
        def _boom(**kwargs):
            raise RuntimeError("storage down")

        monkeypatch.setattr(judge_calibration, "record_sample", _boom)
        v = Verdict.normalize(VERDICT_FAIL, 0.9, "confirmed", model="judge-x")
        out = judge_shadow.run_shadow_judge(
            tenant_id="t1", call_id="c1", failure_code="LOW_CONFIDENCE",
            call_prompt=None, call_response=None, diagnosis_summary=None,
            evaluator=_StubEvaluator(v),
        )
        assert out["verdict"] == "fail"  # unaffected

    def test_default_evaluator_is_constructed_when_omitted(
        self, monkeypatch
    ) -> None:
        """When `evaluator` is not passed, run_shadow_judge constructs a
        SingleJudgeEvaluator on the fly. Exercise that path with a faked
        LLM client so we don't make a real API call."""
        from app.services import llm_client as llm_module

        class _FakeMsg:
            content = '{"verdict":"fail","confidence":0.7,"reason":"x"}'

        class _FakeChoice:
            message = _FakeMsg()

        class _FakeResp:
            choices = [_FakeChoice()]

        class _FakeClient:
            def chat_completions_create(self, **kwargs):
                # Verify the system prompt override propagated through.
                msgs = kwargs["messages"]
                assert msgs[0]["role"] == "system"
                assert "quality-assurance judge" in msgs[0]["content"]
                return _FakeResp()

        monkeypatch.setattr(llm_module, "get_llm_client", lambda: _FakeClient())
        out = judge_shadow.run_shadow_judge(
            tenant_id="t1", call_id="c1", failure_code="LOOP_DETECTED",
            call_prompt="p", call_response="r", diagnosis_summary="d",
        )
        assert out["verdict"] == "fail"
        assert out["confidence"] == 0.7


# ── _build_user_prompt ───────────────────────────────────────────────────────


class TestBuildUserPrompt:
    def test_includes_call_id_and_failure_code_always(self) -> None:
        out = judge_shadow._build_user_prompt(
            call_id="c1", failure_code="LOW_CONFIDENCE",
            call_prompt=None, call_response=None,
            diagnosis_summary=None, policy_text=None,
        )
        assert "call_id: c1" in out
        assert "failure_code: LOW_CONFIDENCE" in out

    def test_optional_sections_are_included_when_provided(self) -> None:
        out = judge_shadow._build_user_prompt(
            call_id="c1", failure_code="LOOP_DETECTED",
            call_prompt="my prompt", call_response="my response",
            diagnosis_summary="diag summary", policy_text="policy",
        )
        assert "policy:" in out
        assert "prompt:" in out
        assert "response:" in out
        assert "diagnosis_summary:" in out

    def test_inputs_are_truncated_at_documented_caps(self) -> None:
        out = judge_shadow._build_user_prompt(
            call_id="c1", failure_code="LOOP_DETECTED",
            call_prompt="P" * 2000,
            call_response="R" * 2000,
            diagnosis_summary="D" * 2000,
            policy_text="X" * 5000,
        )
        # Caps: prompt 800, response 800, diagnosis_summary 400, policy 1800.
        assert "P" * 801 not in out
        assert "R" * 801 not in out
        assert "D" * 401 not in out
        assert "X" * 1801 not in out


# ── SingleJudgeEvaluator system_prompt override (the new judge_engine API) ───


class TestSystemPromptOverride:
    def test_default_system_prompt_used_when_not_overridden(self) -> None:
        ev = SingleJudgeEvaluator(model="m/x")
        # Default prompt mentions "actual" vs "expected" framing.
        assert "expected" in ev.system_prompt.lower()
        assert "actual" in ev.system_prompt.lower()

    def test_override_replaces_default(self) -> None:
        custom = "Be a strict QA judge."
        ev = SingleJudgeEvaluator(model="m/x", system_prompt=custom)
        assert ev.system_prompt == custom

    def test_empty_override_falls_back_to_default(self) -> None:
        ev = SingleJudgeEvaluator(model="m/x", system_prompt="   ")
        assert "expected" in ev.system_prompt.lower()

    def test_none_override_uses_default(self) -> None:
        ev = SingleJudgeEvaluator(model="m/x", system_prompt=None)
        assert "expected" in ev.system_prompt.lower()
