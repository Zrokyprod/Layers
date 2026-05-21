"""
Tests for multi-dimensional and reference-free evaluators in judge_engine.py.

Coverage:
  - _parse_multidim_json: clean JSON with all dims, partial dims (some missing),
    fenced JSON, no dimensions key (fallback to top-level verdict only),
    corrupt JSON, non-object response
  - MultiDimEvaluator: success path (mocked LLM returns 4 dims), partial-dim
    fallback, LLM exception → inconclusive
  - ReferenceFreeEvaluator: success path (mocked LLM returns 4 dims), ignores
    expected argument, LLM exception → inconclusive
  - Helper accessors: get_dimensions, get_overall_score, has_dimensions on
    multi-dim, standard, and stub verdicts
  - get_multidim_evaluator factory: deterministic override, kill-switch,
    no API key fallback, enabled path
  - get_reference_free_evaluator factory: same pattern
  - judge_multidim one-shot helper: returns Verdict with dimensions
  - judge_reference_free one-shot helper: no expected needed
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services.judge_engine import (
    DeterministicStubEvaluator,
    MultiDimEvaluator,
    ReferenceFreeEvaluator,
    VERDICT_FAIL,
    VERDICT_INCONCLUSIVE,
    VERDICT_PASS,
    Verdict,
    _MULTIDIM_DIMENSIONS,
    _REFREE_DIMENSIONS,
    _parse_multidim_json,
    get_dimensions,
    get_multidim_evaluator,
    get_overall_score,
    get_reference_free_evaluator,
    has_dimensions,
    judge_multidim,
    judge_reference_free,
)


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────

def _make_llm_resp(content: str) -> MagicMock:
    """Build a minimal mock that looks like an OpenAI-compatible response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _multidim_json(
    verdict: str = "pass",
    confidence: float = 0.9,
    reason: str = "looks good",
    dims: dict[str, Any] | None = None,
) -> str:
    if dims is None:
        dims = {
            "accuracy": {"score": 0.9, "reason": "match"},
            "faithfulness": {"score": 0.95, "reason": "no extras"},
            "relevance": {"score": 0.85, "reason": "on topic"},
            "coherence": {"score": 0.88, "reason": "logical"},
        }
    return json.dumps({
        "verdict": verdict,
        "confidence": confidence,
        "reason": reason,
        "dimensions": dims,
    })


def _refree_json(
    verdict: str = "pass",
    confidence: float = 0.82,
    reason: str = "well grounded",
    dims: dict[str, Any] | None = None,
) -> str:
    if dims is None:
        dims = {
            "relevance": {"score": 0.9, "reason": "on topic"},
            "coherence": {"score": 0.85, "reason": "consistent"},
            "groundedness": {"score": 0.8, "reason": "hedged"},
            "completeness": {"score": 0.75, "reason": "thorough"},
        }
    return json.dumps({
        "verdict": verdict,
        "confidence": confidence,
        "reason": reason,
        "dimensions": dims,
    })


# ──────────────────────────────────────────────────────────────────────────
# _parse_multidim_json
# ──────────────────────────────────────────────────────────────────────────


class TestParseMultidimJson:
    def test_clean_json_all_dims(self) -> None:
        raw = _multidim_json()
        verdict, conf, reason, dims, overall = _parse_multidim_json(raw, _MULTIDIM_DIMENSIONS)
        assert verdict == VERDICT_PASS
        assert conf == pytest.approx(0.9)
        assert reason == "looks good"
        assert set(dims.keys()) == set(_MULTIDIM_DIMENSIONS)
        assert dims["accuracy"]["score"] == pytest.approx(0.9)
        assert dims["faithfulness"]["reason"] == "no extras"
        assert overall is not None
        assert overall == pytest.approx((0.9 + 0.95 + 0.85 + 0.88) / 4, abs=1e-4)

    def test_fenced_json_stripped(self) -> None:
        raw = "```json\n" + _multidim_json() + "\n```"
        verdict, _, _, dims, _ = _parse_multidim_json(raw, _MULTIDIM_DIMENSIONS)
        assert verdict == VERDICT_PASS
        assert "accuracy" in dims

    def test_missing_dim_filled_with_zero(self) -> None:
        partial_dims = {
            "accuracy": {"score": 0.8, "reason": "ok"},
        }
        raw = _multidim_json(dims=partial_dims)
        _, _, _, dims, overall = _parse_multidim_json(raw, _MULTIDIM_DIMENSIONS)
        assert dims["accuracy"]["score"] == pytest.approx(0.8)
        assert dims["faithfulness"] == {"score": 0.0, "reason": "missing"}
        assert dims["relevance"] == {"score": 0.0, "reason": "missing"}
        assert dims["coherence"] == {"score": 0.0, "reason": "missing"}
        assert overall == pytest.approx(0.8 / 4, abs=1e-4)

    def test_no_dimensions_key_all_filled_missing(self) -> None:
        raw = json.dumps({"verdict": "fail", "confidence": 0.6, "reason": "bad"})
        verdict, conf, reason, dims, overall = _parse_multidim_json(raw, _MULTIDIM_DIMENSIONS)
        assert verdict == VERDICT_FAIL
        assert conf == pytest.approx(0.6)
        for dim in _MULTIDIM_DIMENSIONS:
            assert dims[dim] == {"score": 0.0, "reason": "missing"}
        assert overall == pytest.approx(0.0)

    def test_corrupt_json_returns_inconclusive(self) -> None:
        verdict, conf, _, dims, overall = _parse_multidim_json("not json at all", _MULTIDIM_DIMENSIONS)
        assert verdict == VERDICT_INCONCLUSIVE
        assert conf == 0.0
        assert dims == {}
        assert overall is None

    def test_non_object_returns_inconclusive(self) -> None:
        verdict, _, _, _, _ = _parse_multidim_json(json.dumps([1, 2, 3]), _MULTIDIM_DIMENSIONS)
        assert verdict == VERDICT_INCONCLUSIVE

    def test_score_clamped_to_unit_interval(self) -> None:
        dims = {d: {"score": 2.5, "reason": "over"} for d in _MULTIDIM_DIMENSIONS}
        raw = _multidim_json(dims=dims)
        _, _, _, parsed_dims, _ = _parse_multidim_json(raw, _MULTIDIM_DIMENSIONS)
        for d in _MULTIDIM_DIMENSIONS:
            assert parsed_dims[d]["score"] == pytest.approx(1.0)

    def test_refree_dimensions_parsed(self) -> None:
        raw = _refree_json()
        _, _, _, dims, overall = _parse_multidim_json(raw, _REFREE_DIMENSIONS)
        assert set(dims.keys()) == set(_REFREE_DIMENSIONS)
        assert dims["groundedness"]["score"] == pytest.approx(0.8)
        assert overall is not None

    def test_invalid_verdict_normalized(self) -> None:
        raw = json.dumps({"verdict": "MAYBE", "confidence": 0.5})
        verdict, _, _, _, _ = _parse_multidim_json(raw, _MULTIDIM_DIMENSIONS)
        assert verdict == VERDICT_INCONCLUSIVE


# ──────────────────────────────────────────────────────────────────────────
# Helper accessors
# ──────────────────────────────────────────────────────────────────────────


class TestHelperAccessors:
    def _multidim_verdict(self) -> Verdict:
        return Verdict.normalize(
            VERDICT_PASS,
            0.9,
            "all good",
            metadata={
                "dimensions": {"accuracy": {"score": 0.9, "reason": "ok"}},
                "overall_score": 0.9,
            },
        )

    def test_get_dimensions_multidim_verdict(self) -> None:
        v = self._multidim_verdict()
        dims = get_dimensions(v)
        assert "accuracy" in dims
        assert dims["accuracy"]["score"] == pytest.approx(0.9)

    def test_get_dimensions_plain_verdict_returns_empty(self) -> None:
        v = Verdict.normalize(VERDICT_PASS, 0.8, "ok")
        assert get_dimensions(v) == {}

    def test_get_dimensions_none_metadata(self) -> None:
        v = Verdict(verdict=VERDICT_PASS, confidence=0.8, metadata=None)
        assert get_dimensions(v) == {}

    def test_get_overall_score_present(self) -> None:
        v = self._multidim_verdict()
        assert get_overall_score(v) == pytest.approx(0.9)

    def test_get_overall_score_absent(self) -> None:
        v = Verdict.normalize(VERDICT_PASS, 0.8, "ok")
        assert get_overall_score(v) is None

    def test_get_overall_score_non_numeric(self) -> None:
        v = Verdict.normalize(VERDICT_PASS, 0.8, "ok", metadata={"overall_score": "high"})
        assert get_overall_score(v) is None

    def test_has_dimensions_true(self) -> None:
        v = self._multidim_verdict()
        assert has_dimensions(v) is True

    def test_has_dimensions_false_plain(self) -> None:
        v = Verdict.normalize(VERDICT_PASS, 0.8, "ok")
        assert has_dimensions(v) is False

    def test_has_dimensions_false_empty_dict(self) -> None:
        v = Verdict.normalize(VERDICT_PASS, 0.8, "ok", metadata={"dimensions": {}})
        assert has_dimensions(v) is False


# ──────────────────────────────────────────────────────────────────────────
# MultiDimEvaluator
# ──────────────────────────────────────────────────────────────────────────


class TestMultiDimEvaluator:
    def test_success_path_returns_dimensions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ev = MultiDimEvaluator(model="test-model")
        mock_client = MagicMock()
        mock_client.chat_completions_create.return_value = _make_llm_resp(_multidim_json())

        with patch("app.services.llm_client.get_llm_client", return_value=mock_client):
            v = ev.evaluate("actual output", "expected output")

        assert v.verdict == VERDICT_PASS
        assert v.confidence == pytest.approx(0.9)
        assert has_dimensions(v)
        dims = get_dimensions(v)
        assert set(dims.keys()) == set(_MULTIDIM_DIMENSIONS)
        assert get_overall_score(v) is not None
        assert v.model == "test-model"

    def test_partial_dims_in_metadata(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ev = MultiDimEvaluator(model="test-model")
        partial_dims = {"accuracy": {"score": 0.7, "reason": "partial"}}
        mock_client = MagicMock()
        mock_client.chat_completions_create.return_value = _make_llm_resp(
            _multidim_json(dims=partial_dims)
        )

        with patch("app.services.llm_client.get_llm_client", return_value=mock_client):
            v = ev.evaluate("actual", "expected")

        dims = get_dimensions(v)
        assert dims["accuracy"]["score"] == pytest.approx(0.7)
        assert dims["faithfulness"]["reason"] == "missing"

    def test_llm_exception_returns_inconclusive(self) -> None:
        ev = MultiDimEvaluator(model="test-model")
        mock_client = MagicMock()
        mock_client.chat_completions_create.side_effect = RuntimeError("timeout")

        with patch("app.services.llm_client.get_llm_client", return_value=mock_client):
            v = ev.evaluate("actual", "expected")

        assert v.verdict == VERDICT_INCONCLUSIVE
        assert v.confidence == 0.0
        assert "judge_error" in v.reason

    def test_missing_model_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.judge_engine.get_settings",
            lambda: MagicMock(
                JUDGE_MULTIDIM_MODEL="",
                JUDGE_SINGLE_MODEL="",
                JUDGE_MAX_TOKENS=256,
                JUDGE_TEMPERATURE=0.0,
            ),
        )
        with pytest.raises(ValueError, match="model is required"):
            MultiDimEvaluator()

    def test_context_forwarded_to_prompt(self) -> None:
        ev = MultiDimEvaluator(model="test-model")
        captured: list[dict] = []

        def fake_create(messages: list, **_kw: Any) -> MagicMock:
            captured.append({"messages": messages})
            return _make_llm_resp(_multidim_json())

        mock_client = MagicMock()
        mock_client.chat_completions_create.side_effect = fake_create

        with patch("app.services.llm_client.get_llm_client", return_value=mock_client):
            ev.evaluate("actual", "expected", context={"original_prompt": "hello"})

        assert captured
        user_content = captured[0]["messages"][1]["content"]
        assert "hello" in user_content


# ──────────────────────────────────────────────────────────────────────────
# ReferenceFreeEvaluator
# ──────────────────────────────────────────────────────────────────────────


class TestReferenceFreeEvaluator:
    def test_success_path_returns_dimensions(self) -> None:
        ev = ReferenceFreeEvaluator(model="test-model")
        mock_client = MagicMock()
        mock_client.chat_completions_create.return_value = _make_llm_resp(_refree_json())

        with patch("app.services.llm_client.get_llm_client", return_value=mock_client):
            v = ev.evaluate("actual output", "ignored expected")

        assert v.verdict == VERDICT_PASS
        assert has_dimensions(v)
        dims = get_dimensions(v)
        assert set(dims.keys()) == set(_REFREE_DIMENSIONS)
        assert "groundedness" in dims
        assert dims["groundedness"]["score"] == pytest.approx(0.8)

    def test_expected_argument_ignored(self) -> None:
        ev = ReferenceFreeEvaluator(model="test-model")
        captured: list[dict] = []

        def fake_create(messages: list, **_kw: Any) -> MagicMock:
            captured.append({"messages": messages})
            return _make_llm_resp(_refree_json())

        mock_client = MagicMock()
        mock_client.chat_completions_create.side_effect = fake_create

        with patch("app.services.llm_client.get_llm_client", return_value=mock_client):
            ev.evaluate("actual", "this should not appear in prompt")

        user_content = captured[0]["messages"][1]["content"]
        assert "this should not appear in prompt" not in user_content

    def test_original_prompt_surfaced_in_user_prompt(self) -> None:
        ev = ReferenceFreeEvaluator(model="test-model")
        captured: list[dict] = []

        def fake_create(messages: list, **_kw: Any) -> MagicMock:
            captured.append({"messages": messages})
            return _make_llm_resp(_refree_json())

        mock_client = MagicMock()
        mock_client.chat_completions_create.side_effect = fake_create

        ctx = {"original_prompt": "What is the refund policy?"}
        with patch("app.services.llm_client.get_llm_client", return_value=mock_client):
            ev.evaluate("You get a refund within 30 days.", "", context=ctx)

        user_content = captured[0]["messages"][1]["content"]
        assert "What is the refund policy?" in user_content

    def test_low_groundedness_fails(self) -> None:
        ev = ReferenceFreeEvaluator(model="test-model")
        low_ground_dims = {
            "relevance": {"score": 0.9, "reason": "on topic"},
            "coherence": {"score": 0.85, "reason": "consistent"},
            "groundedness": {"score": 0.2, "reason": "fabricated claims"},
            "completeness": {"score": 0.8, "reason": "ok"},
        }
        mock_client = MagicMock()
        mock_client.chat_completions_create.return_value = _make_llm_resp(
            _refree_json(verdict="fail", dims=low_ground_dims)
        )

        with patch("app.services.llm_client.get_llm_client", return_value=mock_client):
            v = ev.evaluate("agent claimed X", "", context=None)

        assert v.verdict == VERDICT_FAIL
        assert get_dimensions(v)["groundedness"]["score"] == pytest.approx(0.2)

    def test_llm_exception_returns_inconclusive(self) -> None:
        ev = ReferenceFreeEvaluator(model="test-model")
        mock_client = MagicMock()
        mock_client.chat_completions_create.side_effect = ConnectionError("network error")

        with patch("app.services.llm_client.get_llm_client", return_value=mock_client):
            v = ev.evaluate("actual", "")

        assert v.verdict == VERDICT_INCONCLUSIVE
        assert "judge_error" in v.reason

    def test_missing_model_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.judge_engine.get_settings",
            lambda: MagicMock(
                JUDGE_REFERENCE_FREE_MODEL="",
                JUDGE_SINGLE_MODEL="",
                JUDGE_MAX_TOKENS=256,
                JUDGE_TEMPERATURE=0.0,
            ),
        )
        with pytest.raises(ValueError, match="model is required"):
            ReferenceFreeEvaluator()


# ──────────────────────────────────────────────────────────────────────────
# get_multidim_evaluator factory
# ──────────────────────────────────────────────────────────────────────────


class TestGetMultidimEvaluator:
    def _settings(self, **overrides: Any) -> MagicMock:
        defaults = dict(
            JUDGE_MULTIDIM_ENABLED=True,
            JUDGE_MULTIDIM_MODEL="m1",
            JUDGE_SINGLE_MODEL="claude-haiku-4",
            JUDGE_MAX_TOKENS=256,
            JUDGE_TEMPERATURE=0.0,
            OPENROUTER_API_KEY="key",
            OPENAI_API_KEY=None,
        )
        defaults.update(overrides)
        return MagicMock(**defaults)

    def test_deterministic_override_returns_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.services.judge_engine.get_settings", lambda: self._settings())
        ev = get_multidim_evaluator(deterministic=True)
        assert isinstance(ev, DeterministicStubEvaluator)

    def test_kill_switch_returns_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.judge_engine.get_settings",
            lambda: self._settings(JUDGE_MULTIDIM_ENABLED=False),
        )
        ev = get_multidim_evaluator()
        assert isinstance(ev, DeterministicStubEvaluator)

    def test_no_api_key_returns_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.judge_engine.get_settings",
            lambda: self._settings(OPENROUTER_API_KEY=None, OPENAI_API_KEY=None),
        )
        ev = get_multidim_evaluator()
        assert isinstance(ev, DeterministicStubEvaluator)

    def test_enabled_returns_multidim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.services.judge_engine.get_settings", lambda: self._settings())
        ev = get_multidim_evaluator()
        assert isinstance(ev, MultiDimEvaluator)
        assert ev.model == "m1"

    def test_model_override_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.services.judge_engine.get_settings", lambda: self._settings())
        ev = get_multidim_evaluator(model="override-model")
        assert isinstance(ev, MultiDimEvaluator)
        assert ev.model == "override-model"


# ──────────────────────────────────────────────────────────────────────────
# get_reference_free_evaluator factory
# ──────────────────────────────────────────────────────────────────────────


class TestGetReferenceFreeEvaluator:
    def _settings(self, **overrides: Any) -> MagicMock:
        defaults = dict(
            JUDGE_REFERENCE_FREE_ENABLED=True,
            JUDGE_REFERENCE_FREE_MODEL="m2",
            JUDGE_SINGLE_MODEL="claude-haiku-4",
            JUDGE_MAX_TOKENS=256,
            JUDGE_TEMPERATURE=0.0,
            OPENROUTER_API_KEY="key",
            OPENAI_API_KEY=None,
        )
        defaults.update(overrides)
        return MagicMock(**defaults)

    def test_deterministic_override_returns_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.services.judge_engine.get_settings", lambda: self._settings())
        ev = get_reference_free_evaluator(deterministic=True)
        assert isinstance(ev, DeterministicStubEvaluator)

    def test_kill_switch_returns_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.judge_engine.get_settings",
            lambda: self._settings(JUDGE_REFERENCE_FREE_ENABLED=False),
        )
        ev = get_reference_free_evaluator()
        assert isinstance(ev, DeterministicStubEvaluator)

    def test_no_api_key_returns_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.judge_engine.get_settings",
            lambda: self._settings(OPENROUTER_API_KEY=None, OPENAI_API_KEY=None),
        )
        ev = get_reference_free_evaluator()
        assert isinstance(ev, DeterministicStubEvaluator)

    def test_enabled_returns_refree(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.services.judge_engine.get_settings", lambda: self._settings())
        ev = get_reference_free_evaluator()
        assert isinstance(ev, ReferenceFreeEvaluator)
        assert ev.model == "m2"


# ──────────────────────────────────────────────────────────────────────────
# One-shot helpers: judge_multidim + judge_reference_free
# ──────────────────────────────────────────────────────────────────────────


class TestOneShopHelpers:
    def test_judge_multidim_deterministic_returns_verdict(self) -> None:
        v = judge_multidim("same text", "same text", deterministic=True)
        assert isinstance(v, Verdict)
        assert v.verdict == VERDICT_PASS

    def test_judge_multidim_deterministic_fail(self) -> None:
        v = judge_multidim("actual", "expected different", deterministic=True)
        assert v.verdict == VERDICT_FAIL

    def test_judge_reference_free_deterministic_returns_verdict(self) -> None:
        v = judge_reference_free("some output", deterministic=True)
        assert isinstance(v, Verdict)

    def test_judge_reference_free_no_expected_arg(self) -> None:
        v = judge_reference_free("output text", deterministic=True)
        assert isinstance(v, Verdict)
        assert v.verdict in {VERDICT_PASS, VERDICT_FAIL, VERDICT_INCONCLUSIVE}

    def test_judge_multidim_with_llm(self) -> None:
        mock_client = MagicMock()
        mock_client.chat_completions_create.return_value = _make_llm_resp(_multidim_json())
        ev = MultiDimEvaluator(model="test-model")
        with patch("app.services.judge_engine.get_multidim_evaluator", return_value=ev):
            with patch("app.services.llm_client.get_llm_client", return_value=mock_client):
                v = judge_multidim("actual", "expected", model="test-model")
        assert v.verdict == VERDICT_PASS
        assert has_dimensions(v)

    def test_judge_reference_free_with_llm(self) -> None:
        mock_client = MagicMock()
        mock_client.chat_completions_create.return_value = _make_llm_resp(_refree_json())
        ev = ReferenceFreeEvaluator(model="test-model")
        with patch("app.services.judge_engine.get_reference_free_evaluator", return_value=ev):
            with patch("app.services.llm_client.get_llm_client", return_value=mock_client):
                v = judge_reference_free("agent output", model="test-model")
        assert v.verdict == VERDICT_PASS
        assert has_dimensions(v)
        assert "groundedness" in get_dimensions(v)
