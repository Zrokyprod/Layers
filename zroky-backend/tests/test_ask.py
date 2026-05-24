"""Unit tests for the Ask Zroky service.

Covers the deterministic-by-design pieces:
    * intent_router.classify_intent — keyword + window + agent + UUID extraction
    * answer_synthesizer._fallback — heuristic answer when LLM is unavailable
    * answer_synthesizer._parse_json — robust JSON extraction
    * answer_synthesizer._clamp_confidence — bound checks

Synthesizer + data_retriever full integration is exercised through a
project-scoped SQL fixture in a future suite; here we keep the unit footprint
small so the test runs in CI without a DB.
"""
from __future__ import annotations

from app.services.ask.intent_router import classify_intent
from app.services.ask.answer_synthesizer import (
    _clamp_confidence,
    _fallback,
    _parse_json,
)
from app.services.ask.data_retriever import EvidenceBundle
from app.services.ask import Intent


# ── intent_router ─────────────────────────────────────────────────────────────


def test_classify_cost_question():
    intent = classify_intent("How much money did my agent spend yesterday?")
    assert intent.name == "cost"
    assert intent.window_days == 2  # "yesterday" maps to 2-day window


def test_classify_latency_question():
    intent = classify_intent("Why is my checkout agent so slow today?")
    assert intent.name == "latency"
    assert intent.window_days == 1
    assert intent.agent_name == "checkout"


def test_classify_failure_question():
    intent = classify_intent("Show me everything that broke this week")
    assert intent.name == "failure"
    assert intent.window_days == 7


def test_classify_specific_call_uuid():
    intent = classify_intent(
        "Why did call 11111111-2222-3333-4444-555555555555 fail?"
    )
    assert intent.name == "specific_call"
    assert intent.call_id == "11111111-2222-3333-4444-555555555555"


def test_classify_specific_anomaly_uuid():
    intent = classify_intent(
        "Tell me about anomaly 11111111-2222-3333-4444-555555555555"
    )
    assert intent.name == "specific_anomaly"
    assert intent.anomaly_id == "11111111-2222-3333-4444-555555555555"


def test_classify_behavior_question():
    intent = classify_intent("Show me what my agent answered last week")
    # "last week" doesn't match the patterns exactly, falls to default 7-day
    assert intent.name == "behavior"


def test_classify_general_fallback():
    intent = classify_intent("Hello there!")
    assert intent.name == "general"


def test_classify_empty_question():
    intent = classify_intent("")
    assert intent.name == "general"


def test_classify_month_window():
    intent = classify_intent("What were my costs this month?")
    assert intent.window_days == 30


def test_classify_default_window():
    intent = classify_intent("Are there any failures?")
    assert intent.window_days == 7  # default


def test_classify_agent_pattern_my_x_agent():
    intent = classify_intent("Why is my checkout agent failing today?")
    assert intent.agent_name == "checkout"


# ── answer_synthesizer ────────────────────────────────────────────────────────


def test_fallback_no_evidence():
    bundle = EvidenceBundle(intent="general", window_days=7)
    intent = Intent(name="general")
    answer = _fallback(intent, bundle, reason="no_api_key")
    assert "enough data" in answer.answer.lower()
    assert answer.confidence < 0.5
    assert answer.used_llm is False
    assert answer.fallback_reason == "no_api_key"
    assert len(answer.suggested_actions) >= 1


def test_fallback_with_cost_evidence():
    bundle = EvidenceBundle(
        intent="cost",
        window_days=7,
        summary={"total_calls": 1000, "total_cost_usd": 12.50, "error_count": 5},
        rows=[
            {"agent_name": "checkout", "model": "claude-haiku-4", "cost_usd": 0.5}
        ],
    )
    intent = Intent(name="cost", window_days=7)
    answer = _fallback(intent, bundle, reason="llm_error")
    assert "1000 calls" in answer.answer
    assert "$12.5000" in answer.answer or "12.50" in answer.answer.replace(",", "")
    assert "checkout" in answer.answer
    assert answer.used_llm is False


def test_fallback_with_failure_evidence():
    bundle = EvidenceBundle(
        intent="failure",
        window_days=7,
        summary={"total_calls": 100, "error_count": 8},
        rows=[
            {"failure_code": "TIMEOUT", "occurrence_count": 12}
        ],
    )
    intent = Intent(name="failure", window_days=7)
    answer = _fallback(intent, bundle, reason="llm_error")
    assert "TIMEOUT" in answer.answer
    assert "12 times" in answer.answer


def test_parse_json_clean():
    raw = '{"answer": "hello", "suggested_actions": ["a"], "confidence": 0.9}'
    assert _parse_json(raw)["answer"] == "hello"


def test_parse_json_markdown_fenced():
    raw = '```json\n{"answer": "fenced"}\n```'
    assert _parse_json(raw)["answer"] == "fenced"


def test_parse_json_embedded():
    raw = 'Here is the response: {"answer": "embedded"} thanks!'
    assert _parse_json(raw)["answer"] == "embedded"


def test_parse_json_malformed_returns_empty():
    assert _parse_json("not json at all") == {}


def test_clamp_confidence_in_range():
    assert _clamp_confidence(0.5) == 0.5


def test_clamp_confidence_below_zero():
    assert _clamp_confidence(-0.5) == 0.0


def test_clamp_confidence_above_one():
    assert _clamp_confidence(2.5) == 1.0


def test_clamp_confidence_invalid_returns_default():
    assert _clamp_confidence("not a number") == 0.5


def test_clamp_confidence_none_returns_default():
    assert _clamp_confidence(None) == 0.5
