"""Unit tests for the Ablation Root-Cause Attribution system.

Tests cover:
  - axis_extractor:          extract 6 axes from various Call-like objects
  - determinism_classifier:  classify determinism from mock query results
  - confidence_scorer:       statistical axis scoring against control group
  - synthesis:               JSON parse + fallback narrative on LLM error
"""
from __future__ import annotations

import json
import math
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ── helpers ────────────────────────────────────────────────────────────────────


def _make_call(**kwargs):
    defaults = dict(
        id="call-001",
        project_id="proj-test",
        model="anthropic/claude-haiku-4",
        agent_name="order-agent",
        status="error",
        error_code=None,
        latency_ms=1200.0,
        output_tokens=50,
        payload_json="{}",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_control(model="anthropic/claude-3-sonnet", fp="fp-xyz789", latency=800.0, tokens=120, tool_count=0, fallback_len=0, similarity=0.85):
    from app.services.ablation.control_group import ControlTrace
    return ControlTrace(
        call_id="ctrl-001",
        model=model,
        agent_name="order-agent",
        prompt_fingerprint=fp,
        latency_ms=latency,
        output_tokens=tokens,
        error_code=None,
        tool_count=tool_count,
        fallback_len=fallback_len,
        similarity=similarity,
        payload={},
    )


# ── axis_extractor tests ────────────────────────────────────────────────────────


class TestAxisExtractor:
    def test_extracts_six_axes(self):
        from app.services.ablation.axis_extractor import extract_axes
        call = _make_call()
        axes = extract_axes(call)
        assert len(axes) == 6

    def test_axis_types(self):
        from app.services.ablation.axis_extractor import extract_axes
        call = _make_call()
        types = {a.axis_type for a in extract_axes(call)}
        assert types == {"model_version", "prompt_template", "tool_behavior", "latency_env", "input_class", "retry_pattern"}

    def test_model_version_raw(self):
        from app.services.ablation.axis_extractor import extract_axes
        call = _make_call(model="openai/gpt-4o")
        axes = {a.axis_type: a for a in extract_axes(call)}
        assert axes["model_version"].raw["model"] == "openai/gpt-4o"
        assert axes["model_version"].failing_value == "openai/gpt-4o"

    def test_tool_behavior_parses_payload(self):
        from app.services.ablation.axis_extractor import extract_axes
        payload = json.dumps({
            "tool_calls_made": [{"name": "search"}, {"name": "lookup"}],
            "timeout_triggered": True,
        })
        call = _make_call(payload_json=payload)
        axes = {a.axis_type: a for a in extract_axes(call)}
        raw = axes["tool_behavior"].raw
        assert raw["tool_count"] == 2
        assert raw["timeout_triggered"] is True

    def test_token_bucket_empty(self):
        from app.services.ablation.axis_extractor import extract_axes
        call = _make_call(output_tokens=0)
        axes = {a.axis_type: a for a in extract_axes(call)}
        assert axes["input_class"].raw["token_bucket"] == "empty"

    def test_token_bucket_large(self):
        from app.services.ablation.axis_extractor import extract_axes
        call = _make_call(output_tokens=1500)
        axes = {a.axis_type: a for a in extract_axes(call)}
        assert axes["input_class"].raw["token_bucket"] == "large"

    def test_retry_pattern_from_payload(self):
        from app.services.ablation.axis_extractor import extract_axes
        payload = json.dumps({"fallback_chain": ["m1", "m2", "m3"], "retry_metadata": {"count": 2}})
        call = _make_call(payload_json=payload)
        axes = {a.axis_type: a for a in extract_axes(call)}
        assert axes["retry_pattern"].raw["fallback_len"] == 3
        assert axes["retry_pattern"].raw["has_retry_meta"] is True

    def test_broken_payload_json_safe(self):
        from app.services.ablation.axis_extractor import extract_axes
        call = _make_call(payload_json="NOT_JSON{{{")
        axes = extract_axes(call)
        assert len(axes) == 6  # still returns all 6 axes gracefully


# ── determinism_classifier tests ───────────────────────────────────────────────


class TestDeterminismClassifier:
    def _mock_db(self, rows):
        db = MagicMock()
        result = MagicMock()
        result.all.return_value = rows
        db.execute.return_value = result
        return db

    def test_deterministic_high_fail_rate(self):
        from app.services.ablation.determinism_classifier import classify_determinism
        rows = [SimpleNamespace(status="error", error_code=None)] * 8 + \
               [SimpleNamespace(status="completed", error_code=None)] * 2
        db = self._mock_db(rows)
        call = _make_call(error_code=None)
        result = classify_determinism(db, project_id="p", call=call)
        assert result.determinism_class == "deterministic"
        assert result.fail_rate >= 0.75

    def test_stochastic_medium_fail_rate(self):
        from app.services.ablation.determinism_classifier import classify_determinism
        rows = [SimpleNamespace(status="error", error_code=None)] * 4 + \
               [SimpleNamespace(status="completed", error_code=None)] * 6
        db = self._mock_db(rows)
        call = _make_call(error_code=None)
        result = classify_determinism(db, project_id="p", call=call)
        assert result.determinism_class == "stochastic"

    def test_environmental_infra_error_code(self):
        from app.services.ablation.determinism_classifier import classify_determinism
        rows = [SimpleNamespace(status="completed", error_code=None)] * 10
        db = self._mock_db(rows)
        call = _make_call(error_code="RATE_LIMIT")
        result = classify_determinism(db, project_id="p", call=call)
        assert result.determinism_class == "environmental"

    def test_unknown_insufficient_history(self):
        from app.services.ablation.determinism_classifier import classify_determinism
        rows = [SimpleNamespace(status="error", error_code=None)] * 3  # < MIN_SAMPLE_SIZE=5
        db = self._mock_db(rows)
        call = _make_call()
        result = classify_determinism(db, project_id="p", call=call)
        assert result.determinism_class == "unknown"

    def test_environmental_timeout_in_payload(self):
        from app.services.ablation.determinism_classifier import classify_determinism
        rows = [SimpleNamespace(status="completed", error_code=None)] * 10
        db = self._mock_db(rows)
        call = _make_call(payload_json=json.dumps({"timeout_triggered": True}))
        result = classify_determinism(db, project_id="p", call=call)
        assert result.determinism_class == "environmental"


# ── confidence_scorer tests ────────────────────────────────────────────────────


class TestConfidenceScorer:
    def test_model_mismatch_high_confidence(self):
        from app.services.ablation.axis_extractor import extract_axes
        from app.services.ablation.confidence_scorer import score_axes
        call = _make_call(model="openai/gpt-4o")
        axes = extract_axes(call)
        # Control group uses a completely different model — high mismatch → high confidence
        control = [_make_control(model="anthropic/claude-3-sonnet")] * 10
        scored = score_axes(axes, control)
        mv = next(s for s in scored if s.axis.axis_type == "model_version")
        assert mv.confidence > 0.7

    def test_model_match_low_confidence(self):
        from app.services.ablation.axis_extractor import extract_axes
        from app.services.ablation.confidence_scorer import score_axes
        call = _make_call(model="anthropic/claude-haiku-4")
        axes = extract_axes(call)
        # Control group uses SAME model → low causal confidence for this axis
        control = [_make_control(model="anthropic/claude-haiku-4")] * 10
        scored = score_axes(axes, control)
        mv = next(s for s in scored if s.axis.axis_type == "model_version")
        assert mv.confidence < 0.15

    def test_latency_outlier_high_confidence(self):
        from app.services.ablation.axis_extractor import extract_axes
        from app.services.ablation.confidence_scorer import score_axes
        # Failing call: 9000ms; control: ~800ms → z-score > 2 → environmental
        call = _make_call(latency_ms=9000.0)
        axes = extract_axes(call)
        control = [_make_control(latency=800.0 + i * 10) for i in range(10)]
        scored = score_axes(axes, control)
        lat = next(s for s in scored if s.axis.axis_type == "latency_env")
        assert lat.confidence > 0.3

    def test_empty_control_group_zero_confidence(self):
        from app.services.ablation.axis_extractor import extract_axes
        from app.services.ablation.confidence_scorer import score_axes
        call = _make_call()
        axes = extract_axes(call)
        scored = score_axes(axes, [])
        assert all(s.confidence == 0.0 for s in scored)

    def test_sorted_descending(self):
        from app.services.ablation.axis_extractor import extract_axes
        from app.services.ablation.confidence_scorer import score_axes
        call = _make_call(model="openai/gpt-4o", latency_ms=9000.0)
        axes = extract_axes(call)
        control = [_make_control(model="anthropic/claude-3-sonnet", latency=800.0)] * 10
        scored = score_axes(axes, control)
        confidences = [s.confidence for s in scored]
        assert confidences == sorted(confidences, reverse=True)

    def test_evidence_populated(self):
        from app.services.ablation.axis_extractor import extract_axes
        from app.services.ablation.confidence_scorer import score_axes
        call = _make_call(model="openai/gpt-4o")
        axes = extract_axes(call)
        control = [_make_control(model="anthropic/claude-3-sonnet")] * 5
        scored = score_axes(axes, control)
        mv = next(s for s in scored if s.axis.axis_type == "model_version")
        assert "failing_model" in mv.evidence
        assert mv.evidence["control_group_size"] == 5


# ── synthesis tests ─────────────────────────────────────────────────────────────


class TestSynthesis:
    def test_skip_when_no_high_confidence_axes(self):
        from app.services.ablation.synthesis import synthesise_root_cause
        result = synthesise_root_cause(
            determinism_class="stochastic",
            agent_name="order-agent",
            diagnosis_categories=["HALLUCINATION_RISK"],
            scored_axes=[
                {"axis_type": "model_version", "axis_label": "Model X", "confidence": 0.3, "evidence": {}},
            ],
            control_group_size=8,
        )
        assert result.skipped is True
        assert result.skip_reason == "no_high_confidence_axes"
        assert result.synthesis_confidence == 0.0

    def test_llm_error_returns_fallback(self):
        from app.services.ablation.synthesis import synthesise_root_cause
        with patch("app.services.ablation.synthesis.OpenAI") as MockOAI:
            MockOAI.side_effect = Exception("API unavailable")
            result = synthesise_root_cause(
                determinism_class="deterministic",
                agent_name="order-agent",
                diagnosis_categories=["SCHEMA_VIOLATION"],
                scored_axes=[
                    {"axis_type": "model_version", "axis_label": "openai/gpt-4o", "confidence": 0.85, "evidence": {}},
                ],
                control_group_size=12,
            )
        assert "model_version" in result.root_cause_narrative
        assert result.fix_difficulty == "medium"
        assert result.synthesis_confidence > 0

    def test_fingerprint_is_deterministic(self):
        from app.services.ablation.synthesis import _fingerprint
        axes = [
            {"axis_type": "model_version", "confidence": 0.85},
            {"axis_type": "latency_env", "confidence": 0.40},
        ]
        assert _fingerprint(axes) == _fingerprint(axes)

    def test_difficulty_validation(self):
        from app.services.ablation.synthesis import _validate_difficulty
        assert _validate_difficulty("easy") == "easy"
        assert _validate_difficulty("hard") == "hard"
        assert _validate_difficulty("UNKNOWN") == "medium"
        assert _validate_difficulty(None) == "medium"
