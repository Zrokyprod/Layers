"""
Tests for `app/services/judge_engine.py` (Module 7).

Coverage:
  - Verdict.normalize: invalid verdict/confidence/reason clamping
  - _parse_verdict_json: clean JSON / fenced / malformed / non-object inputs
  - DeterministicStubEvaluator: pass/fail/inconclusive paths
  - SingleJudgeEvaluator: success path (mocked LLM), JSON parse fallback,
    LLM exception → inconclusive
  - EnsembleEvaluator: unanimous, majority, even-tie tiebreak, dissent
    confidence math, fewer-than-2 children rejected
  - get_evaluator factory: deterministic override, JUDGE_ENABLED kill,
    missing API key fallback, ensemble entitlement true/false,
    plan_code defaulting, malformed JUDGE_ENSEMBLE_MODELS_JSON
  - judge() one-shot helper: returns Verdict; honours deterministic flag
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services import judge_engine
from app.services.judge_engine import (
    DeterministicStubEvaluator,
    EnsembleEvaluator,
    Evaluator,
    SingleJudgeEvaluator,
    VALID_VERDICTS,
    VERDICT_FAIL,
    VERDICT_INCONCLUSIVE,
    VERDICT_PASS,
    Verdict,
    _parse_verdict_json,
    get_evaluator,
    judge,
)


# ──────────────────────────────────────────────────────────────────────────
# Verdict dataclass + normalize
# ──────────────────────────────────────────────────────────────────────────


class TestVerdictNormalize:
    def test_pass_verdict_round_trips(self) -> None:
        v = Verdict.normalize(VERDICT_PASS, 0.8, "looks good", model="m1")
        assert v.verdict == VERDICT_PASS
        assert v.confidence == 0.8
        assert v.reason == "looks good"
        assert v.model == "m1"

    def test_invalid_verdict_becomes_inconclusive(self) -> None:
        v = Verdict.normalize("garbage", 0.5)
        assert v.verdict == VERDICT_INCONCLUSIVE

    def test_uppercased_verdict_normalized(self) -> None:
        v = Verdict.normalize("PASS", 1.0)
        assert v.verdict == VERDICT_PASS

    def test_none_verdict_becomes_inconclusive(self) -> None:
        v = Verdict.normalize(None, 0.5)  # type: ignore[arg-type]
        assert v.verdict == VERDICT_INCONCLUSIVE

    def test_negative_confidence_clamped_to_zero(self) -> None:
        v = Verdict.normalize(VERDICT_PASS, -0.5)
        assert v.confidence == 0.0

    def test_above_one_confidence_clamped_to_one(self) -> None:
        v = Verdict.normalize(VERDICT_PASS, 1.7)
        assert v.confidence == 1.0

    def test_non_numeric_confidence_becomes_zero(self) -> None:
        v = Verdict.normalize(VERDICT_FAIL, "high")  # type: ignore[arg-type]
        assert v.confidence == 0.0

    def test_long_reason_is_truncated(self) -> None:
        long_reason = "x" * 1000
        v = Verdict.normalize(VERDICT_PASS, 0.9, long_reason)
        assert len(v.reason) == 500
        assert v.reason.endswith("...")

    def test_negative_latency_clamped_to_zero(self) -> None:
        v = Verdict.normalize(VERDICT_PASS, 0.9, latency_ms=-50)
        assert v.latency_ms == 0

    def test_metadata_is_copied_not_shared(self) -> None:
        meta = {"k": "v"}
        v = Verdict.normalize(VERDICT_PASS, 0.9, metadata=meta)
        meta["k"] = "mutated"
        assert v.metadata["k"] == "v"

    def test_to_dict_is_json_serializable(self) -> None:
        v = Verdict.normalize(
            VERDICT_PASS, 0.9, "fine", model="m1", metadata={"a": 1}
        )
        d = v.to_dict()
        # Must round-trip through json without raising.
        json.dumps(d)
        assert d["verdict"] == VERDICT_PASS
        assert d["metadata"] == {"a": 1}

    def test_valid_verdicts_set_is_exact(self) -> None:
        assert VALID_VERDICTS == frozenset({"pass", "fail", "inconclusive"})


# ──────────────────────────────────────────────────────────────────────────
# _parse_verdict_json
# ──────────────────────────────────────────────────────────────────────────


class TestParseVerdictJson:
    def test_clean_json(self) -> None:
        raw = '{"verdict":"pass","confidence":0.9,"reason":"matches"}'
        verdict, conf, reason = _parse_verdict_json(raw)
        assert (verdict, conf, reason) == ("pass", 0.9, "matches")

    def test_fenced_json(self) -> None:
        raw = '```json\n{"verdict":"fail","confidence":0.7,"reason":"bad"}\n```'
        verdict, conf, reason = _parse_verdict_json(raw)
        assert verdict == "fail"
        assert conf == 0.7

    def test_fenced_no_lang_tag(self) -> None:
        raw = '```\n{"verdict":"pass","confidence":1.0,"reason":"ok"}\n```'
        verdict, _, _ = _parse_verdict_json(raw)
        assert verdict == "pass"

    def test_malformed_json_falls_back_to_inconclusive(self) -> None:
        verdict, conf, reason = _parse_verdict_json("not json at all")
        assert verdict == "inconclusive"
        assert conf == 0.0
        assert reason == "judge_output_unparseable"

    def test_non_object_json_falls_back(self) -> None:
        verdict, _, reason = _parse_verdict_json('["pass", 0.9]')
        assert verdict == "inconclusive"
        assert reason == "judge_output_not_object"

    def test_unknown_verdict_value_normalized(self) -> None:
        raw = '{"verdict":"maybe","confidence":0.5,"reason":"x"}'
        verdict, _, _ = _parse_verdict_json(raw)
        assert verdict == "inconclusive"

    def test_missing_confidence_defaults_zero(self) -> None:
        raw = '{"verdict":"pass","reason":"x"}'
        _, conf, _ = _parse_verdict_json(raw)
        assert conf == 0.0

    def test_empty_input_falls_back(self) -> None:
        verdict, _, _ = _parse_verdict_json("")
        assert verdict == "inconclusive"


# ──────────────────────────────────────────────────────────────────────────
# DeterministicStubEvaluator
# ──────────────────────────────────────────────────────────────────────────


class TestDeterministicStub:
    def test_exact_match_passes(self) -> None:
        v = DeterministicStubEvaluator().evaluate("hello world", "hello world")
        assert v.verdict == VERDICT_PASS
        assert v.confidence == 1.0
        assert v.reason == "exact_match"
        assert v.model == "deterministic_stub"

    def test_case_insensitive_match(self) -> None:
        v = DeterministicStubEvaluator().evaluate("Hello", "hello")
        assert v.verdict == VERDICT_PASS

    def test_whitespace_trimmed(self) -> None:
        v = DeterministicStubEvaluator().evaluate("  ok  ", "ok")
        assert v.verdict == VERDICT_PASS

    def test_mismatch_fails(self) -> None:
        v = DeterministicStubEvaluator().evaluate("foo", "bar")
        assert v.verdict == VERDICT_FAIL
        assert v.confidence == 1.0
        assert v.reason == "exact_mismatch"

    def test_empty_expected_inconclusive(self) -> None:
        v = DeterministicStubEvaluator().evaluate("anything", "")
        assert v.verdict == VERDICT_INCONCLUSIVE
        assert v.reason == "no_expected_provided"

    def test_both_empty_inconclusive(self) -> None:
        v = DeterministicStubEvaluator().evaluate("", "")
        assert v.verdict == VERDICT_INCONCLUSIVE

    def test_latency_is_recorded(self) -> None:
        v = DeterministicStubEvaluator().evaluate("a", "a")
        # Trivially small but the field exists and is non-negative.
        assert v.latency_ms >= 0


# ──────────────────────────────────────────────────────────────────────────
# SingleJudgeEvaluator (LLM client mocked)
# ──────────────────────────────────────────────────────────────────────────


class _FakeChoiceMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeChoiceMessage(content)


class _FakeChatCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeLlmClient:
    """Stand-in for OpenRouterClient used by tests."""

    def __init__(self, raw: str | Exception) -> None:
        self._raw = raw
        self.last_kwargs: dict[str, Any] = {}

    def chat_completions_create(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        if isinstance(self._raw, Exception):
            raise self._raw
        return _FakeChatCompletion(self._raw)


@pytest.fixture()
def patch_llm(monkeypatch):
    """Inject a fake LLM client so SingleJudgeEvaluator never hits network."""

    def _install(raw: str | Exception) -> _FakeLlmClient:
        fake = _FakeLlmClient(raw)
        # llm_client is imported lazily inside SingleJudgeEvaluator.evaluate,
        # so patch the module attribute directly.
        from app.services import llm_client as llm_module

        monkeypatch.setattr(llm_module, "get_llm_client", lambda: fake)
        return fake

    return _install


class TestSingleJudge:
    def test_requires_model(self, monkeypatch) -> None:
        # Force the default-model lookup to return empty so the ValueError
        # branch is exercised even when JUDGE_SINGLE_MODEL is non-empty in
        # settings.
        from app.core.config import get_settings

        s = get_settings()
        original = s.JUDGE_SINGLE_MODEL
        try:
            s.JUDGE_SINGLE_MODEL = ""
            with pytest.raises(ValueError):
                SingleJudgeEvaluator(model="")
            with pytest.raises(ValueError):
                SingleJudgeEvaluator()
        finally:
            s.JUDGE_SINGLE_MODEL = original

    def test_success_path(self, patch_llm) -> None:
        patch_llm('{"verdict":"pass","confidence":0.9,"reason":"good"}')
        ev = SingleJudgeEvaluator(model="anthropic/claude-haiku-4")
        v = ev.evaluate("output A", "output A")
        assert v.verdict == VERDICT_PASS
        assert v.confidence == 0.9
        assert v.reason == "good"
        assert v.model == "anthropic/claude-haiku-4"
        assert v.latency_ms >= 0

    def test_passes_model_to_llm(self, patch_llm) -> None:
        fake = patch_llm('{"verdict":"pass","confidence":1.0}')
        SingleJudgeEvaluator(model="x/y").evaluate("a", "b")
        assert fake.last_kwargs.get("model") == "x/y"
        assert fake.last_kwargs.get("temperature") == 0.0
        assert fake.last_kwargs.get("max_tokens") == 256

    def test_includes_context(self, patch_llm) -> None:
        fake = patch_llm('{"verdict":"pass","confidence":1.0}')
        SingleJudgeEvaluator(model="x/y").evaluate(
            "a", "b", context={"trace_id": "t1", "tier": "pilot"}
        )
        messages = fake.last_kwargs["messages"]
        user_msg = messages[-1]["content"]
        assert "context:" in user_msg
        assert "trace_id" in user_msg

    def test_unparseable_response_yields_inconclusive(self, patch_llm) -> None:
        patch_llm("garbage not json")
        v = SingleJudgeEvaluator(model="x/y").evaluate("a", "b")
        assert v.verdict == VERDICT_INCONCLUSIVE
        assert v.confidence == 0.0
        assert v.reason == "judge_output_unparseable"

    def test_llm_exception_caught(self, patch_llm) -> None:
        patch_llm(RuntimeError("upstream down"))
        v = SingleJudgeEvaluator(model="x/y").evaluate("a", "b")
        assert v.verdict == VERDICT_INCONCLUSIVE
        assert "judge_error" in v.reason
        assert v.confidence == 0.0

    def test_empty_choices_yields_inconclusive(self, patch_llm) -> None:
        # Build a fake response with no choices.
        class _Empty:
            choices: list = []

        from app.services import llm_client as llm_module

        class _C:
            def chat_completions_create(self, **kwargs):
                return _Empty()

        from unittest.mock import patch as mock_patch

        with mock_patch.object(llm_module, "get_llm_client", return_value=_C()):
            v = SingleJudgeEvaluator(model="x/y").evaluate("a", "b")
        assert v.verdict == VERDICT_INCONCLUSIVE


# ──────────────────────────────────────────────────────────────────────────
# EnsembleEvaluator
# ──────────────────────────────────────────────────────────────────────────


class _ScriptedEvaluator(Evaluator):
    """Returns a pre-baked Verdict regardless of input."""

    name = "scripted"

    def __init__(self, verdict: str, confidence: float = 1.0, model: str = "scr") -> None:
        self._v = Verdict.normalize(verdict, confidence, model=model)

    def evaluate(self, actual, expected, *, context=None):  # type: ignore[override]
        return self._v


class TestEnsemble:
    def test_requires_two_children(self) -> None:
        with pytest.raises(ValueError):
            EnsembleEvaluator([_ScriptedEvaluator(VERDICT_PASS)])
        with pytest.raises(ValueError):
            EnsembleEvaluator([])

    def test_unanimous_pass(self) -> None:
        ev = EnsembleEvaluator(
            [_ScriptedEvaluator(VERDICT_PASS, 0.9, "a"),
             _ScriptedEvaluator(VERDICT_PASS, 0.7, "b"),
             _ScriptedEvaluator(VERDICT_PASS, 0.8, "c")]
        )
        v = ev.evaluate("x", "x")
        assert v.verdict == VERDICT_PASS
        assert v.confidence == 1.0
        # Reason borrowed from highest-confidence agreeing judge.
        # judges metadata has 3 entries.
        assert len(v.metadata["judges"]) == 3

    def test_majority_pass(self) -> None:
        ev = EnsembleEvaluator(
            [_ScriptedEvaluator(VERDICT_PASS, 0.9),
             _ScriptedEvaluator(VERDICT_PASS, 0.7),
             _ScriptedEvaluator(VERDICT_FAIL, 0.8)]
        )
        v = ev.evaluate("x", "x")
        assert v.verdict == VERDICT_PASS
        assert v.confidence == pytest.approx(2 / 3, rel=1e-6)

    def test_majority_fail(self) -> None:
        ev = EnsembleEvaluator(
            [_ScriptedEvaluator(VERDICT_FAIL, 0.9),
             _ScriptedEvaluator(VERDICT_FAIL, 0.6),
             _ScriptedEvaluator(VERDICT_PASS, 0.4)]
        )
        v = ev.evaluate("x", "x")
        assert v.verdict == VERDICT_FAIL

    def test_even_tie_uses_median_low(self) -> None:
        # 2 pass (+1), 2 fail (-1) → median_low = -1 → fail (conservative).
        ev = EnsembleEvaluator(
            [_ScriptedEvaluator(VERDICT_PASS),
             _ScriptedEvaluator(VERDICT_PASS),
             _ScriptedEvaluator(VERDICT_FAIL),
             _ScriptedEvaluator(VERDICT_FAIL)]
        )
        v = ev.evaluate("x", "x")
        assert v.verdict == VERDICT_FAIL

    def test_inconclusive_dampens(self) -> None:
        # pass + fail + inconclusive → sorted scores [-1, 0, 1] median = 0
        ev = EnsembleEvaluator(
            [_ScriptedEvaluator(VERDICT_PASS),
             _ScriptedEvaluator(VERDICT_FAIL),
             _ScriptedEvaluator(VERDICT_INCONCLUSIVE)]
        )
        v = ev.evaluate("x", "x")
        assert v.verdict == VERDICT_INCONCLUSIVE

    def test_metadata_contains_each_child(self) -> None:
        ev = EnsembleEvaluator(
            [_ScriptedEvaluator(VERDICT_PASS, 0.5, "alpha"),
             _ScriptedEvaluator(VERDICT_PASS, 0.6, "beta")]
        )
        v = ev.evaluate("x", "x")
        judges = v.metadata["judges"]
        assert len(judges) == 2
        models = {j["model"] for j in judges}
        assert models == {"alpha", "beta"}

    def test_model_string_includes_count(self) -> None:
        ev = EnsembleEvaluator(
            [_ScriptedEvaluator(VERDICT_PASS),
             _ScriptedEvaluator(VERDICT_PASS)]
        )
        v = ev.evaluate("x", "x")
        assert v.model == "ensemble:2"


# ──────────────────────────────────────────────────────────────────────────
# get_evaluator factory
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def fresh_settings(monkeypatch):
    """Return the live Settings object so individual tests can poke fields.

    Settings are a pydantic BaseSettings instance — direct attribute set
    works because all relevant fields are mutable scalars.
    """
    from app.core.config import get_settings

    s = get_settings()
    # Snapshot the fields we tweak so the fixture is teardown-safe.
    snapshot = {
        "JUDGE_ENABLED": s.JUDGE_ENABLED,
        "OPENROUTER_API_KEY": s.OPENROUTER_API_KEY,
        "OPENAI_API_KEY": getattr(s, "OPENAI_API_KEY", None),
        "JUDGE_SINGLE_MODEL": s.JUDGE_SINGLE_MODEL,
        "JUDGE_ENSEMBLE_MODELS_JSON": s.JUDGE_ENSEMBLE_MODELS_JSON,
    }
    yield s
    for k, v in snapshot.items():
        try:
            setattr(s, k, v)
        except Exception:
            pass


class TestGetEvaluator:
    def test_deterministic_override_wins(self, fresh_settings) -> None:
        fresh_settings.JUDGE_ENABLED = True
        fresh_settings.OPENROUTER_API_KEY = "sk-test"
        ev = get_evaluator("plus", deterministic=True)
        assert isinstance(ev, DeterministicStubEvaluator)

    def test_kill_switch_returns_stub(self, fresh_settings) -> None:
        fresh_settings.JUDGE_ENABLED = False
        fresh_settings.OPENROUTER_API_KEY = "sk-test"
        ev = get_evaluator("plus")
        assert isinstance(ev, DeterministicStubEvaluator)

    def test_missing_api_key_returns_stub(self, fresh_settings) -> None:
        fresh_settings.JUDGE_ENABLED = True
        fresh_settings.OPENROUTER_API_KEY = None
        if hasattr(fresh_settings, "OPENAI_API_KEY"):
            fresh_settings.OPENAI_API_KEY = None
        ev = get_evaluator("pro")
        assert isinstance(ev, DeterministicStubEvaluator)

    def test_pro_plan_returns_single(self, fresh_settings) -> None:
        fresh_settings.JUDGE_ENABLED = True
        fresh_settings.OPENROUTER_API_KEY = "sk-test"
        ev = get_evaluator("pro")
        assert isinstance(ev, SingleJudgeEvaluator)

    def test_plus_plan_returns_ensemble(self, fresh_settings) -> None:
        fresh_settings.JUDGE_ENABLED = True
        fresh_settings.OPENROUTER_API_KEY = "sk-test"
        fresh_settings.JUDGE_ENSEMBLE_MODELS_JSON = (
            '["anthropic/claude-haiku-4","openai/gpt-4o-mini"]'
        )
        ev = get_evaluator("plus")
        assert isinstance(ev, EnsembleEvaluator)
        assert len(ev.evaluators) == 2

    def test_enterprise_plan_returns_ensemble(self, fresh_settings) -> None:
        fresh_settings.JUDGE_ENABLED = True
        fresh_settings.OPENROUTER_API_KEY = "sk-test"
        ev = get_evaluator("enterprise")
        assert isinstance(ev, EnsembleEvaluator)

    def test_free_plan_returns_single(self, fresh_settings) -> None:
        fresh_settings.JUDGE_ENABLED = True
        fresh_settings.OPENROUTER_API_KEY = "sk-test"
        ev = get_evaluator("free")
        assert isinstance(ev, SingleJudgeEvaluator)

    def test_entitlement_dict_overrides_plan(self, fresh_settings) -> None:
        """ensemble_enabled=True in resolved entitlements promotes Pro to ensemble."""
        fresh_settings.JUDGE_ENABLED = True
        fresh_settings.OPENROUTER_API_KEY = "sk-test"
        fresh_settings.JUDGE_ENSEMBLE_MODELS_JSON = (
            '["anthropic/claude-haiku-4","openai/gpt-4o-mini"]'
        )
        ev = get_evaluator(
            "pro",
            entitlements_dict={"judge.ensemble_enabled": True},
        )
        assert isinstance(ev, EnsembleEvaluator)

    def test_entitlement_dict_false_demotes_plus(self, fresh_settings) -> None:
        """ensemble_enabled=False in resolved entitlements demotes Plus to single."""
        fresh_settings.JUDGE_ENABLED = True
        fresh_settings.OPENROUTER_API_KEY = "sk-test"
        ev = get_evaluator(
            "plus",
            entitlements_dict={"judge.ensemble_enabled": False},
        )
        assert isinstance(ev, SingleJudgeEvaluator)

    def test_malformed_ensemble_json_falls_back_to_single(
        self, fresh_settings
    ) -> None:
        fresh_settings.JUDGE_ENABLED = True
        fresh_settings.OPENROUTER_API_KEY = "sk-test"
        fresh_settings.JUDGE_ENSEMBLE_MODELS_JSON = "not json"
        ev = get_evaluator("plus")
        assert isinstance(ev, SingleJudgeEvaluator)

    def test_single_item_ensemble_falls_back_to_single(
        self, fresh_settings
    ) -> None:
        fresh_settings.JUDGE_ENABLED = True
        fresh_settings.OPENROUTER_API_KEY = "sk-test"
        fresh_settings.JUDGE_ENSEMBLE_MODELS_JSON = (
            '["anthropic/claude-haiku-4"]'
        )
        ev = get_evaluator("plus")
        assert isinstance(ev, SingleJudgeEvaluator)

    def test_none_plan_code_defaults_to_free(self, fresh_settings) -> None:
        fresh_settings.JUDGE_ENABLED = True
        fresh_settings.OPENROUTER_API_KEY = "sk-test"
        ev = get_evaluator(None)
        # free → single (no ensemble entitlement)
        assert isinstance(ev, SingleJudgeEvaluator)


# ──────────────────────────────────────────────────────────────────────────
# judge() one-shot helper
# ──────────────────────────────────────────────────────────────────────────


class TestJudgeHelper:
    def test_deterministic_path_is_pure(self) -> None:
        v = judge("hello", "hello", deterministic=True)
        assert v.verdict == VERDICT_PASS
        assert v.model == "deterministic_stub"

    def test_routes_through_factory(self, monkeypatch) -> None:
        sentinel = Verdict.normalize(VERDICT_FAIL, 0.5, "from-stub")

        class _StubEv(Evaluator):
            name = "stub"

            def evaluate(self, a, b, *, context=None):  # type: ignore[override]
                return sentinel

        monkeypatch.setattr(judge_engine, "get_evaluator", lambda **k: _StubEv())
        v = judge("anything", "anything")
        assert v is sentinel
