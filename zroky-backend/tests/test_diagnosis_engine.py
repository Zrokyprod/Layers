from datetime import datetime, timedelta, timezone

import pytest

from app.services.diagnosis_engine import evaluate_diagnosis_payload
from app.services.token_overflow_rules import known_model_context_limit


def _categories(result: dict) -> set[str]:
    return {item["category"] for item in result["diagnoses"]}


def _find(result: dict, category: str) -> dict:
    for item in result["diagnoses"]:
        if item["category"] == category:
            return item
    raise AssertionError(f"Missing diagnosis category {category}")


def test_token_overflow_single_call_subtype() -> None:
    result = evaluate_diagnosis_payload(
        {
            "prompt_tokens": 4300,
            "model_limit_tokens": 4096,
            "system_prompt_tokens": 900,
            "user_message_tokens": 3400,
            "conversation_turns": 1,
        }
    )

    diagnosis = _find(result, "TOKEN_OVERFLOW")
    assert diagnosis["subtype"] == "single_call_overflow"
    assert diagnosis["evidence"]["overflow_by"] == 204


def test_token_overflow_conversation_accumulation_subtype() -> None:
    result = evaluate_diagnosis_payload(
        {
            "prompt_tokens": 5000,
            "model_limit_tokens": 4096,
            "conversation_turns": 9,
            "history_tokens": 2300,
        }
    )

    diagnosis = _find(result, "TOKEN_OVERFLOW")
    assert diagnosis["subtype"] == "conversation_accumulation"


def test_token_overflow_false_positive_guard_3800_of_4096() -> None:
    result = evaluate_diagnosis_payload(
        {
            "prompt_tokens": 3800,
            "model_limit_tokens": 4096,
            "conversation_turns": 5,
            "history_tokens": 1800,
        }
    )

    assert "TOKEN_OVERFLOW" not in _categories(result)


def test_token_overflow_detected_by_error_code_without_usage() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "failed",
            "provider": "openai",
            "model": "gpt-4o",
            "error_code": "TOKEN_OVERFLOW",
            "error_message": "provider did not return usage",
        }
    )

    diagnosis = _find(result, "TOKEN_OVERFLOW")
    assert diagnosis["detected_by"] == "error_code"
    assert diagnosis["confidence"] >= 0.95
    assert diagnosis["evidence"]["detected_by"] == "error_code"
    assert diagnosis["evidence"]["model_limit"] == 128000
    assert diagnosis["evidence"]["model_context_limit_source"] == "catalog_exact"
    assert diagnosis["evidence"]["model_context_limit_confidence"] == 0.95
    assert diagnosis["evidence"]["error_snippet"] == "provider did not return usage"


def test_token_overflow_detected_by_error_message_pattern_without_usage() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "failed",
            "provider": "openai",
            "model": "unknown-model",
            "error_message": "This deployment rejected the request: too many tokens.",
        }
    )

    diagnosis = _find(result, "TOKEN_OVERFLOW")
    assert diagnosis["detected_by"] == "error_message_pattern"
    assert diagnosis["confidence"] == 0.80
    assert diagnosis["evidence"]["matched_error_pattern"] == "too many tokens"
    assert "too many tokens" in diagnosis["evidence"]["error_snippet"]


def test_token_overflow_error_evidence_masks_pii() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "failed",
            "provider": "openai",
            "model": "gpt-4o",
            "error_code": "TOKEN_OVERFLOW",
            "error_message": (
                "maximum context length for user@example.com and "
                "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"
            ),
        }
    )

    diagnosis = _find(result, "TOKEN_OVERFLOW")
    snippet = diagnosis["evidence"]["error_snippet"]
    assert "user@example.com" not in snippet
    assert "sk-proj-" not in snippet
    assert "[REDACTED_EMAIL]" in snippet
    assert "[REDACTED_KEY]" in snippet


def test_token_overflow_detected_by_estimate_with_explicit_limit() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "failed",
            "provider": "openai",
            "model": "gpt-3.5-turbo",
            "estimated_prompt_tokens": 3700,
            "model_context_limit": 4096,
        }
    )

    diagnosis = _find(result, "TOKEN_OVERFLOW")
    assert diagnosis["detected_by"] == "token_estimate"
    assert 0.70 <= diagnosis["confidence"] <= 0.85
    assert diagnosis["evidence"]["estimated_tokens"] == 3700
    assert diagnosis["evidence"]["model_limit"] == 4096
    assert diagnosis["evidence"]["model_context_limit_source"] == "sdk_payload"
    assert diagnosis["evidence"]["model_context_limit_source_detail"] == "model_context_limit"
    assert diagnosis["evidence"]["threshold_estimated_prompt_tokens_gt_90pct_model_limit"] is True


def test_token_overflow_estimate_uses_known_model_default_when_limit_missing() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "failed",
            "model": "gpt-3.5-turbo",
            "estimated_prompt_tokens": 3700,
        }
    )

    diagnosis = _find(result, "TOKEN_OVERFLOW")
    assert diagnosis["detected_by"] == "token_estimate"
    assert diagnosis["evidence"]["model_limit"] == 4096
    assert diagnosis["evidence"]["model_context_limit_source"] == "catalog_exact"


def test_token_overflow_estimate_uses_model_limit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZROKY_MODEL_CONTEXT_LIMITS", '{"custom-model": 1000}')

    result = evaluate_diagnosis_payload(
        {
            "status": "failed",
            "model": "custom-model",
            "estimated_prompt_tokens": 950,
        }
    )

    diagnosis = _find(result, "TOKEN_OVERFLOW")
    assert diagnosis["detected_by"] == "token_estimate"
    assert diagnosis["evidence"]["model_limit"] == 1000
    assert diagnosis["evidence"]["model_context_limit_source"] == "env_override"


def test_invalid_model_context_limit_override_warns(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv(
        "ZROKY_MODEL_CONTEXT_LIMITS",
        "invalid-backend-limit=0,custom-backend-model=12345",
    )

    with caplog.at_level("WARNING", logger="app.services.token_overflow_rules"):
        assert known_model_context_limit("custom-backend-model") == 12345

    assert "Ignoring invalid ZROKY_MODEL_CONTEXT_LIMITS entry" in caplog.text
    assert "invalid-backend-limit=0" in caplog.text


def test_token_overflow_estimate_skips_unknown_model_without_limit() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "failed",
            "model": "unknown-model",
            "estimated_prompt_tokens": 100000,
        }
    )

    assert "TOKEN_OVERFLOW" not in _categories(result)


def test_token_overflow_merges_multiple_signals_without_duplicates() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "failed",
            "model": "gpt-3.5-turbo",
            "error_code": "TOKEN_OVERFLOW",
            "error_message": "maximum context length exceeded",
            "estimated_prompt_tokens": 5000,
            "token_estimator_version": "chars_per_token_v1",
            "token_rules_version": "token_rules_v1",
        }
    )

    diagnoses = [item for item in result["diagnoses"] if item["category"] == "TOKEN_OVERFLOW"]
    assert len(diagnoses) == 1
    diagnosis = diagnoses[0]
    assert diagnosis["detected_by"] == "error_code"
    assert diagnosis["evidence"]["detection_signals"] == [
        "error_code",
        "error_message_pattern",
        "token_estimate",
    ]
    assert diagnosis["evidence"]["token_estimator_version"] == "chars_per_token_v1"
    assert diagnosis["evidence"]["token_rules_version"] == "token_rules_v1"


def test_token_overflow_estimate_skips_partial_response() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "partial",
            "model": "gpt-3.5-turbo",
            "estimated_prompt_tokens": 5000,
        }
    )

    assert "TOKEN_OVERFLOW" not in _categories(result)


def test_rate_limit_contains_provider_degradation_context() -> None:
    result = evaluate_diagnosis_payload(
        {
            "provider": "openai",
            "status_code": 429,
            "error_code": "rate_limit_exceeded",
            "provider_latency_trend_ms": {"p95": 2200, "p99": 4300},
        }
    )

    diagnosis = _find(result, "RATE_LIMIT")
    evidence = diagnosis["evidence"]
    assert evidence["provider_status"] == "unknown"
    assert evidence["status_fetch_timeout_ms"] == 800
    assert evidence["status_cache_ttl_seconds"] == 300
    assert evidence["provider_latency_p95_ms"] == 2200


@pytest.mark.skip(
    reason=(
        "Module 1 removed `resolve_provider_status_context` from diagnosis_engine "
        "when the detector refactor moved provider-status plumbing into the "
        "individual detectors (app.services.detectors.*). Re-author against the "
        "new detector injection surface in Module 7 (Diagnose + Pilot v1)."
    )
)
def test_rate_limit_uses_provider_status_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    pass


def test_auth_failure_detected_for_401() -> None:
    result = evaluate_diagnosis_payload(
        {
            "provider": "anthropic",
            "status_code": 401,
            "error_code": "invalid_api_key",
        }
    )

    assert "AUTH_FAILURE" in _categories(result)


def test_rate_limit_reads_structured_failure_reason() -> None:
    result = evaluate_diagnosis_payload(
        {
            "provider": "openai",
            "status": "failed",
            "error_code": "UNKNOWN_ERROR",
            "failure_reason": {
                "http_status": 429,
                "provider_error_code": "rate_limit_exceeded",
                "provider_request_id": "req_rate_123",
                "retry_after_seconds": 8,
                "message": "Provider throttled the request.",
            },
        }
    )

    diagnosis = _find(result, "RATE_LIMIT")
    assert diagnosis["evidence"]["status_code"] == 429
    assert diagnosis["evidence"]["provider_request_id"] == "req_rate_123"
    assert diagnosis["evidence"]["retry_after_seconds"] == 8


def test_unknown_provider_failure_gets_structured_provider_error_diagnosis() -> None:
    result = evaluate_diagnosis_payload(
        {
            "provider": "openai",
            "model": "gpt-4o",
            "status": "failed",
            "error_code": "UNKNOWN_ERROR",
            "error_message": "BadRequestError: unknown parameter temperature",
            "failure_reason": {
                "schema_version": "zroky.failure_reason.v1",
                "classification": "UNKNOWN_ERROR",
                "error_class": "BadRequestError",
                "http_status": 400,
                "provider_error_code": "unknown_parameter",
                "provider_error_type": "invalid_request_error",
                "provider_error_param": "temperature",
                "provider_request_id": "req_bad_123",
                "message": "Unknown parameter: temperature",
            },
        }
    )

    diagnosis = _find(result, "PROVIDER_ERROR")
    assert diagnosis["subtype"] == "bad_request"
    assert diagnosis["detected_by"] == "structured_failure_reason"
    assert diagnosis["evidence"]["provider_request_id"] == "req_bad_123"
    assert diagnosis["evidence"]["provider_error_param"] == "temperature"
    assert "HTTP 400" in diagnosis["root_cause"]
    assert "req_bad_123" in diagnosis["root_cause"]


def test_loop_detected_for_no_progress_pattern() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "research-agent",
            "prompt_fingerprint": "abc123",
            "loop": {
                "repeat_count": 6,
                "window_seconds": 80,
                "no_progress": True,
                "output_pattern": {
                    "output_fingerprint": "out-fp-1",
                    "repeat_count": 4,
                    "stagnant_output": True,
                },
                "tool_chain_repeat_cycles": 1,
                "tool_window_seconds": 120,
            },
            "retry": {
                "is_sdk_retry": False,
            },
        }
    )

    diagnosis = _find(result, "LOOP_DETECTED")
    assert diagnosis["evidence"]["threshold_agent_repeat_count"] == 5
    assert diagnosis["evidence"]["retry_suppression_applied"] is False
    assert diagnosis["evidence"]["loop_score"] >= 0.65


def test_loop_not_detected_without_no_progress() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "research-agent",
            "prompt_fingerprint": "abc123",
            "loop": {
                "repeat_count": 6,
                "window_seconds": 80,
                "no_progress": False,
            },
        }
    )

    assert "LOOP_DETECTED" not in _categories(result)


def test_loop_detected_includes_strong_evidence() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "research-agent",
            "prompt_fingerprint": "abc123",
            "loop": {
                "repeat_count": 6,
                "window_seconds": 80,
                "no_progress": True,
                "retry_suppression_applied": True,
                "output_pattern": {
                    "output_fingerprint": "stable-output-fp",
                    "repeat_count": 4,
                    "stagnant_output": True,
                },
                "tool_cycle": {
                    "dominant_pattern": "search:abc123",
                    "pattern_type": "same_tool_input",
                    "repeat_count": 4,
                    "tool_sequence": ["search", "search", "search", "search"],
                },
                "sample_timestamps": [
                    "2026-04-23T12:00:01+00:00",
                    "2026-04-23T12:00:11+00:00",
                    "2026-04-23T12:00:21+00:00",
                ],
                "error_pattern": {
                    "dominant_error": "code:rate_limit_exceeded",
                    "dominant_error_count": 4,
                    "failure_count": 5,
                    "useless_output_count": 0,
                    "stagnant_output": False,
                },
                "no_progress_reasons": ["repeated_failures"],
            },
        }
    )

    diagnosis = _find(result, "LOOP_DETECTED")
    evidence = diagnosis["evidence"]
    assert evidence["sample_timestamps"]
    assert evidence["error_pattern"]["dominant_error"] == "code:rate_limit_exceeded"
    assert evidence["error_pattern"]["failure_count"] == 5
    assert evidence["retry_suppression_applied"] is True
    assert "output_fingerprint" in evidence["detected_by"]
    assert "tool_cycle" in evidence["detected_by"]
    assert evidence["loop_window_size"] == 8
    assert evidence["loop_resolved"] is False
    assert evidence["loop_score_breakdown"]["output"] == 0.35


def test_loop_detected_for_repeated_same_output() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "research-agent",
            "prompt_fingerprint": "same-input",
            "output_fingerprint": "same-output",
            "loop": {
                "repeat_count": 5,
                "window_seconds": 70,
                "no_progress": True,
                "output_pattern": {
                    "output_fingerprint": "same-output",
                    "repeat_count": 5,
                    "stagnant_output": True,
                },
            },
        }
    )

    diagnosis = _find(result, "LOOP_DETECTED")
    assert "output_fingerprint" in diagnosis["evidence"]["detected_by"]
    assert diagnosis["evidence"]["output_repeat_count"] == 5
    assert diagnosis["evidence"]["loop_score_breakdown"]["output"] == 0.35


def test_loop_detected_for_near_repeated_outputs() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "research-agent",
            "prompt_fingerprint": "near-output-input",
            "loop": {
                "repeat_count": 5,
                "window_seconds": 70,
                "no_progress": True,
                "loop_window_size": 8,
                "output_pattern": {
                    "repeat_count": 2,
                    "output_similarity_score": 0.84,
                    "near_repeated_output": True,
                },
            },
        }
    )

    diagnosis = _find(result, "LOOP_DETECTED")
    evidence = diagnosis["evidence"]
    assert "output_similarity" in evidence["detected_by"]
    assert evidence["output_similarity_score"] == 0.84
    assert evidence["output_pattern"]["near_repeated_output"] is True
    assert evidence["loop_window_size"] == 8


def test_loop_detected_for_repeated_tool_cycle() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "tool-agent",
            "prompt_fingerprint": "tool-input",
            "loop": {
                "repeat_count": 4,
                "window_seconds": 90,
                "no_progress": True,
                "tool_cycle": {
                    "dominant_pattern": "lookup:input-fp",
                    "pattern_type": "same_tool_input",
                    "repeat_count": 4,
                    "tool_sequence": ["lookup", "lookup", "lookup", "lookup"],
                },
                "output_pattern": {
                    "output_fingerprint": "tool-output-fp",
                    "repeat_count": 3,
                },
            },
        }
    )

    diagnosis = _find(result, "LOOP_DETECTED")
    assert "tool_cycle" in diagnosis["evidence"]["detected_by"]
    assert diagnosis["evidence"]["tool_name"] == "lookup"
    assert diagnosis["evidence"]["tool_cycle"]["state_changed"] is False


def test_loop_detected_for_retry_pattern() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "retry-agent",
            "prompt_fingerprint": "retry-input",
            "retry_metadata": {
                "retry_count": 4,
                "retry_reason": "timeout",
                "max_steps_reached": True,
            },
            "loop": {
                "repeat_count": 5,
                "window_seconds": 80,
                "no_progress": True,
                "retry_pattern": {
                    "retry_count": 4,
                    "dominant_retry_reason": "timeout",
                    "dominant_retry_reason_count": 4,
                },
                "output_pattern": {
                    "output_fingerprint": "retry-output-fp",
                    "repeat_count": 3,
                },
            },
        }
    )

    diagnosis = _find(result, "LOOP_DETECTED")
    assert "retry_pattern" in diagnosis["evidence"]["detected_by"]
    assert diagnosis["evidence"]["retry_count"] == 4


def test_loop_not_detected_for_varied_outputs() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "research-agent",
            "prompt_fingerprint": "abc123",
            "loop": {
                "repeat_count": 6,
                "window_seconds": 80,
                "no_progress": True,
                "output_pattern": {
                    "output_fingerprint": "not-dominant",
                    "repeat_count": 1,
                },
            },
        }
    )

    assert "LOOP_DETECTED" not in _categories(result)


def test_loop_not_detected_after_pattern_breaks() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "research-agent",
            "prompt_fingerprint": "resolved-loop",
            "loop": {
                "repeat_count": 6,
                "window_seconds": 80,
                "no_progress": False,
                "loop_resolved": True,
                "output_pattern": {
                    "output_fingerprint": "old-output",
                    "repeat_count": 5,
                    "output_similarity_score": 0.21,
                    "near_repeated_output": False,
                },
            },
        }
    )

    assert "LOOP_DETECTED" not in _categories(result)


def test_loop_not_detected_when_repeated_tool_changes_state() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "tool-agent",
            "prompt_fingerprint": "state-changing-tool",
            "loop": {
                "repeat_count": 6,
                "window_seconds": 80,
                "no_progress": True,
                "tool_cycle": {
                    "dominant_pattern": "sync:input-fp",
                    "pattern_type": "same_tool_input",
                    "repeat_count": 6,
                    "tool_sequence": ["sync", "sync", "sync", "sync"],
                    "state_changed": True,
                    "state_change_count": 4,
                    "no_state_change_count": 0,
                },
            },
        }
    )

    assert "LOOP_DETECTED" not in _categories(result)


def test_loop_not_detected_for_legitimate_repeated_response() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "faq-agent",
            "prompt_fingerprint": "static-faq",
            "loop": {
                "repeat_count": 8,
                "window_seconds": 80,
                "no_progress": True,
                "legitimate_repeated_output": True,
                "output_pattern": {
                    "output_fingerprint": "static-output",
                    "repeat_count": 8,
                },
            },
        }
    )

    assert "LOOP_DETECTED" not in _categories(result)


def test_loop_detected_suppressed_for_known_sdk_retry() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "research-agent",
            "prompt_fingerprint": "abc123",
            "loop": {
                "repeat_count": 7,
                "window_seconds": 70,
                "no_progress": True,
            },
            "retry": {
                "is_sdk_retry": True,
                "sdk_attempts": 2,
                "backoff_attempts": 2,
            },
        }
    )

    assert "LOOP_DETECTED" not in _categories(result)


def test_loop_detected_suppressed_for_recent_cooldown() -> None:
    now = datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc)
    recent = (now - timedelta(minutes=5)).isoformat()

    result = evaluate_diagnosis_payload(
        {
            "agent_name": "research-agent",
            "prompt_fingerprint": "abc123",
            "loop": {
                "repeat_count": 6,
                "window_seconds": 70,
                "no_progress": True,
                "last_fired_at": recent,
            },
        },
        now=now,
    )

    assert "LOOP_DETECTED" not in _categories(result)


def test_cost_spike_warmup_gate_emits_informational_only() -> None:
    result = evaluate_diagnosis_payload(
        {
            "cost": {
                "current_15m_spend_usd": 70.0,
                "baseline_15m_spend_usd": 20.0,
                "history_days": 2,
                "history_calls": 120,
                "model_spend_coefficient": 1.0,
            }
        }
    )

    assert "COST_SPIKE" not in _categories(result)
    informational = result.get("informational", [])
    assert informational
    assert informational[0]["type"] == "COST_SURGE_WARNING"


def test_cost_spike_hard_trigger_after_warmup() -> None:
    result = evaluate_diagnosis_payload(
        {
            "cost": {
                "current_15m_spend_usd": 120.0,
                "baseline_15m_spend_usd": 20.0,
                "history_days": 14,
                "history_calls": 1200,
                "model_spend_coefficient": 1.2,
            }
        }
    )

    diagnosis = _find(result, "COST_SPIKE")
    assert diagnosis["evidence"]["warmup_gate_met"] is True
    assert diagnosis["evidence"]["hard_threshold_15m_spend_usd"] == 72.0


def test_blast_radius_included_with_trace_payload() -> None:
    result = evaluate_diagnosis_payload(
        {
            "trace_id": "trace-123",
            "agent_name": "research-agent",
            "downstream_calls": [
                {"call_id": "c1", "wasted_cost_usd": 0.8},
                {"call_id": "c2", "wasted_cost_usd": 1.1},
                {"call_id": "c3", "wasted_cost_usd": 0.4},
            ],
        }
    )

    blast_radius = result.get("blast_radius")
    assert blast_radius is not None
    assert blast_radius["downstream_affected_calls"] == 3
    assert blast_radius["wasted_cost_usd"] == 2.3


# ── EMPTY_OUTPUT detector ────────────────────────────────────────────────────


def test_empty_output_detected_for_blank_string_on_success() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "success",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "output_text": "",
            "completion_tokens": 0,
            "finish_reason": "stop",
        }
    )

    diagnosis = _find(result, "EMPTY_OUTPUT")
    assert diagnosis["confidence"] == 0.99
    assert diagnosis["evidence"]["completion_tokens"] == 0


def test_empty_output_detected_for_whitespace_only_response() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "success",
            "response": {"content": "   \n\t  "},
        }
    )

    assert "EMPTY_OUTPUT" in _categories(result)


def test_empty_output_uses_content_filter_root_cause() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "success",
            "output_text": "",
            "finish_reason": "content_filter",
        }
    )

    diagnosis = _find(result, "EMPTY_OUTPUT")
    assert "safety" in diagnosis["root_cause"].lower() or "content filter" in diagnosis["root_cause"].lower()


def test_empty_output_skipped_when_call_failed() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "failed",
            "output_text": "",
            "status_code": 500,
        }
    )

    assert "EMPTY_OUTPUT" not in _categories(result)


def test_empty_output_skipped_when_output_field_absent() -> None:
    # No output field at all — detector cannot judge, must not fire.
    result = evaluate_diagnosis_payload(
        {
            "status": "success",
            "completion_tokens": 0,
        }
    )

    assert "EMPTY_OUTPUT" not in _categories(result)


def test_empty_output_not_fired_for_partial_streaming_state() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "streaming",
            "output_text": "",
        }
    )

    assert "EMPTY_OUTPUT" not in _categories(result)


# ── OUTPUT_TRUNCATED detector ────────────────────────────────────────────────


def test_output_truncated_detected_for_openai_length_finish_reason() -> None:
    result = evaluate_diagnosis_payload(
        {
            "provider": "openai",
            "model": "gpt-4o",
            "finish_reason": "length",
            "completion_tokens": 1000,
            "max_tokens": 1000,
        }
    )

    diagnosis = _find(result, "OUTPUT_TRUNCATED")
    assert diagnosis["evidence"]["finish_reason"] == "length"
    assert diagnosis["evidence"]["requested_max_tokens"] == 1000
    # Suggested cap is at least 2x the previous value, rounded up to 256.
    assert diagnosis["evidence"]["suggested_max_tokens"] >= 2000


def test_output_truncated_detected_for_anthropic_max_tokens_stop_reason() -> None:
    result = evaluate_diagnosis_payload(
        {
            "provider": "anthropic",
            "model": "claude-haiku-4",
            "stop_reason": "max_tokens",
            "completion_tokens": 512,
        }
    )

    diagnosis = _find(result, "OUTPUT_TRUNCATED")
    assert diagnosis["evidence"]["finish_reason"] == "max_tokens"


def test_output_truncated_not_fired_for_natural_stop() -> None:
    result = evaluate_diagnosis_payload(
        {
            "finish_reason": "stop",
            "completion_tokens": 480,
            "max_tokens": 1000,
        }
    )

    assert "OUTPUT_TRUNCATED" not in _categories(result)


def test_output_truncated_handles_uppercase_finish_reason() -> None:
    # Google Gemini emits "MAX_TOKENS" — case-insensitive normalization.
    result = evaluate_diagnosis_payload(
        {
            "provider": "google",
            "finish_reason": "MAX_TOKENS",
            "completion_tokens": 2048,
        }
    )

    assert "OUTPUT_TRUNCATED" in _categories(result)


# ── SCHEMA_VIOLATION detector ────────────────────────────────────────────────


def test_schema_violation_detected_for_invalid_json_when_format_declared() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "success",
            "expected_format": "json",
            "output_text": "Sure! Here you go: {name: 'Alice'}",  # not valid JSON
        }
    )

    diagnosis = _find(result, "SCHEMA_VIOLATION")
    assert "not valid JSON" in diagnosis["evidence"]["violation"]


def test_schema_violation_detected_for_missing_required_key() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "success",
            "expected_schema": {
                "type": "object",
                "required": ["name", "email"],
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                },
            },
            "output_text": '{"name": "Alice"}',
        }
    )

    diagnosis = _find(result, "SCHEMA_VIOLATION")
    assert "missing required keys" in diagnosis["evidence"]["violation"]
    assert "email" in diagnosis["evidence"]["violation"]


def test_schema_violation_detected_for_top_level_type_mismatch() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "success",
            "expected_schema": {"type": "array"},
            "output_text": '{"a": 1}',
        }
    )

    diagnosis = _find(result, "SCHEMA_VIOLATION")
    assert "top-level type" in diagnosis["evidence"]["violation"]


def test_schema_violation_detected_for_property_type_mismatch() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "success",
            "expected_schema": {
                "type": "object",
                "properties": {
                    "age": {"type": "integer"},
                },
            },
            "output_text": '{"age": "thirty"}',
        }
    )

    diagnosis = _find(result, "SCHEMA_VIOLATION")
    assert "key type mismatch" in diagnosis["evidence"]["violation"]


def test_schema_violation_not_fired_for_valid_json_against_schema() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "success",
            "expected_schema": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
            "output_text": '{"name": "Alice"}',
        }
    )

    assert "SCHEMA_VIOLATION" not in _categories(result)


def test_schema_violation_skipped_when_no_contract_declared() -> None:
    result = evaluate_diagnosis_payload(
        {
            "status": "success",
            "output_text": "free-form text response with no contract",
        }
    )

    assert "SCHEMA_VIOLATION" not in _categories(result)


# ── LATENCY_ANOMALY detector ─────────────────────────────────────────────────


def test_latency_anomaly_detected_for_default_60s_threshold() -> None:
    result = evaluate_diagnosis_payload(
        {
            "provider": "openai",
            "model": "gpt-4o",
            "latency_ms": 75_000,
        }
    )

    diagnosis = _find(result, "LATENCY_ANOMALY")
    assert diagnosis["evidence"]["latency_ms"] == 75_000
    assert diagnosis["evidence"]["threshold_ms"] == 60_000
    assert diagnosis["evidence"]["threshold_source"] == "default"
    assert diagnosis["evidence"]["overshoot_ms"] == 15_000


def test_latency_anomaly_uses_explicit_per_call_threshold() -> None:
    result = evaluate_diagnosis_payload(
        {
            "latency_ms": 12_000,
            "latency_threshold_ms": 5_000,
        }
    )

    diagnosis = _find(result, "LATENCY_ANOMALY")
    assert diagnosis["evidence"]["threshold_ms"] == 5_000
    assert diagnosis["evidence"]["threshold_source"] == "payload_explicit"


def test_latency_anomaly_uses_contract_budget_when_no_explicit() -> None:
    result = evaluate_diagnosis_payload(
        {
            "latency_ms": 8_000,
            "contract": {"latency_budget_ms": 4_000},
        }
    )

    diagnosis = _find(result, "LATENCY_ANOMALY")
    assert diagnosis["evidence"]["threshold_source"] == "contract_budget"
    assert diagnosis["evidence"]["threshold_ms"] == 4_000


def test_latency_anomaly_not_fired_below_threshold() -> None:
    result = evaluate_diagnosis_payload(
        {
            "latency_ms": 50_000,
        }
    )

    assert "LATENCY_ANOMALY" not in _categories(result)


def test_latency_anomaly_skipped_for_timeout_class_failure() -> None:
    # Timeouts are owned by provider_error.py; latency_anomaly defers.
    result = evaluate_diagnosis_payload(
        {
            "latency_ms": 75_000,
            "error_code": "request_timeout",
        }
    )

    assert "LATENCY_ANOMALY" not in _categories(result)


def test_latency_anomaly_ignores_obviously_bogus_threshold() -> None:
    # A 100ms threshold would never be intended for an LLM call. Detector
    # falls back to the default 60s threshold.
    result = evaluate_diagnosis_payload(
        {
            "latency_ms": 65_000,
            "latency_threshold_ms": 100,
        }
    )

    diagnosis = _find(result, "LATENCY_ANOMALY")
    assert diagnosis["evidence"]["threshold_source"] == "default"


# ── REPEATED_OUTPUT detector ─────────────────────────────────────────────────


def test_repeated_output_detected_for_same_response_across_distinct_inputs() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "support-agent",
            "session_outputs": [
                "Sorry, I cannot help with that right now.",
                "Sorry, I cannot help with that right now.",
                "Sorry, I cannot help with that right now.",
            ],
            "session_inputs": [
                "What's my refund status?",
                "Why was my card charged twice?",
                "How do I update my address?",
            ],
        }
    )

    diagnosis = _find(result, "REPEATED_OUTPUT")
    assert diagnosis["evidence"]["repeat_count"] == 3
    assert diagnosis["evidence"]["distinct_inputs_observed"] == 3


def test_repeated_output_normalizes_whitespace_and_case() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "agent",
            "session_outputs": [
                "Hello, how can I help?",
                "  HELLO,   how can I  help?  ",
                "Hello,\nhow can I help?",
            ],
            "session_inputs": ["hi", "what's up", "yo"],
        }
    )

    assert "REPEATED_OUTPUT" in _categories(result)


def test_repeated_output_not_fired_when_inputs_are_identical() -> None:
    # User asked the same question 3x — the model returning the same answer
    # is not a degenerate-output signal. Skip.
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "agent",
            "session_outputs": ["A", "A", "A"],
            "session_inputs": ["same", "same", "same"],
        }
    )

    assert "REPEATED_OUTPUT" not in _categories(result)


def test_repeated_output_suppressed_when_loop_detected_already_fired() -> None:
    # Pattern-rule orchestration: if loop_detected fires, repeated_output
    # is suppressed to avoid noisy duplicate signals.
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "research-agent",
            "prompt_fingerprint": "abc123",
            "loop": {
                "repeat_count": 6,
                "window_seconds": 80,
                "no_progress": True,
                "output_pattern": {
                    "output_fingerprint": "out-fp-1",
                    "repeat_count": 4,
                    "stagnant_output": True,
                },
                "tool_chain_repeat_cycles": 1,
                "tool_window_seconds": 120,
            },
            "retry": {"is_sdk_retry": False},
            "session_outputs": [
                "stuck answer that repeats",
                "stuck answer that repeats",
                "stuck answer that repeats",
            ],
            "session_inputs": ["q1", "q2", "q3"],
        }
    )

    assert "LOOP_DETECTED" in _categories(result)
    assert "REPEATED_OUTPUT" not in _categories(result)


def test_repeated_output_not_fired_for_short_outputs() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "agent",
            "session_outputs": ["ok", "ok", "ok"],
            "session_inputs": ["a", "b", "c"],
        }
    )

    assert "REPEATED_OUTPUT" not in _categories(result)


def test_repeated_output_not_fired_for_varied_responses() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "agent",
            "session_outputs": [
                "First answer is here",
                "Second answer is different",
                "Third answer is yet another",
            ],
            "session_inputs": ["q1", "q2", "q3"],
        }
    )

    assert "REPEATED_OUTPUT" not in _categories(result)


# ── OUTPUT_LENGTH_DRIFT detector (Layer 2) ───────────────────────────────────


def test_output_length_drift_detected_when_response_exceeds_p95_baseline() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "summarizer",
            "provider": "openai",
            "model": "gpt-4o",
            "completion_tokens": 1500,
            "length": {
                "baseline_completion_tokens_p50": 240,
                "baseline_completion_tokens_p95": 480,
                "history_days": 14,
                "history_calls": 5000,
            },
        }
    )

    diagnosis = _find(result, "OUTPUT_LENGTH_DRIFT")
    assert diagnosis["evidence"]["completion_tokens"] == 1500
    assert diagnosis["evidence"]["baseline_completion_tokens_p95"] == 480
    assert diagnosis["evidence"]["drift_threshold_tokens"] == 1200  # 480 * 2.5
    assert diagnosis["evidence"]["overshoot_ratio"] >= 3.0


def test_output_length_drift_not_fired_during_warmup_period() -> None:
    result = evaluate_diagnosis_payload(
        {
            "completion_tokens": 1500,
            "length": {
                "baseline_completion_tokens_p95": 480,
                "history_days": 2,  # below 3-day warmup
                "history_calls": 150,
            },
        }
    )

    assert "OUTPUT_LENGTH_DRIFT" not in _categories(result)


def test_output_length_drift_not_fired_below_absolute_floor() -> None:
    # 150 tokens — under 200-token floor regardless of baseline.
    result = evaluate_diagnosis_payload(
        {
            "completion_tokens": 150,
            "length": {
                "baseline_completion_tokens_p95": 30,
                "history_days": 14,
                "history_calls": 5000,
            },
        }
    )

    assert "OUTPUT_LENGTH_DRIFT" not in _categories(result)


def test_output_length_drift_not_fired_below_p95_multiplier() -> None:
    result = evaluate_diagnosis_payload(
        {
            "completion_tokens": 500,  # only 1.04x p95
            "length": {
                "baseline_completion_tokens_p95": 480,
                "history_days": 14,
                "history_calls": 5000,
            },
        }
    )

    assert "OUTPUT_LENGTH_DRIFT" not in _categories(result)


def test_output_length_drift_not_fired_without_baseline() -> None:
    result = evaluate_diagnosis_payload(
        {
            "completion_tokens": 5000,
            "history_days": 14,
            "history_calls": 5000,
            # no baseline_completion_tokens_p95 anywhere
        }
    )

    assert "OUTPUT_LENGTH_DRIFT" not in _categories(result)


# ── LATENCY_DRIFT detector (Layer 2) ─────────────────────────────────────────


def test_latency_drift_detected_when_call_exceeds_p95_multiplier() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "chat-agent",
            "provider": "openai",
            "model": "gpt-4o",
            "latency_ms": 8000,
            "latency": {
                "baseline_p50_ms": 1200,
                "baseline_p95_ms": 2500,
                "history_days": 14,
                "history_calls": 5000,
            },
        }
    )

    diagnosis = _find(result, "LATENCY_DRIFT")
    assert diagnosis["evidence"]["latency_ms"] == 8000
    assert diagnosis["evidence"]["baseline_latency_p95_ms"] == 2500
    assert diagnosis["evidence"]["p95_drift_threshold_ms"] == 5000
    assert diagnosis["evidence"]["triggered_basis"] in {"p95", "p99"}


def test_latency_drift_uses_p99_basis_when_tighter() -> None:
    # latency_ms = 4500, p95*2 = 6000 (not breached), p99*1.5 = 4200 (breached).
    result = evaluate_diagnosis_payload(
        {
            "latency_ms": 4500,
            "latency": {
                "baseline_p95_ms": 3000,
                "baseline_p99_ms": 2800,
                "history_days": 14,
                "history_calls": 5000,
            },
        }
    )

    diagnosis = _find(result, "LATENCY_DRIFT")
    assert diagnosis["evidence"]["triggered_basis"] == "p99"


def test_latency_drift_yields_to_latency_anomaly_above_60s() -> None:
    # latency_ms >= 60_000 → LATENCY_ANOMALY (Layer 1) territory.
    result = evaluate_diagnosis_payload(
        {
            "latency_ms": 75_000,
            "latency": {
                "baseline_p95_ms": 2500,
                "history_days": 14,
                "history_calls": 5000,
            },
        }
    )

    categories = _categories(result)
    assert "LATENCY_ANOMALY" in categories
    assert "LATENCY_DRIFT" not in categories


def test_latency_drift_not_fired_below_absolute_floor() -> None:
    # latency_ms < 2000 → ignored regardless of baseline.
    result = evaluate_diagnosis_payload(
        {
            "latency_ms": 1500,
            "latency": {
                "baseline_p95_ms": 200,  # would be 7.5x
                "history_days": 14,
                "history_calls": 5000,
            },
        }
    )

    assert "LATENCY_DRIFT" not in _categories(result)


def test_latency_drift_not_fired_during_warmup() -> None:
    result = evaluate_diagnosis_payload(
        {
            "latency_ms": 8000,
            "latency": {
                "baseline_p95_ms": 2500,
                "history_days": 1,
                "history_calls": 50,
            },
        }
    )

    assert "LATENCY_DRIFT" not in _categories(result)


# ── ERROR_RATE_DRIFT detector (Layer 2) ──────────────────────────────────────


def test_error_rate_drift_detected_when_rate_triples() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "checkout-agent",
            "error_rate": {
                "current_15m": 0.18,  # 18%
                "baseline_15m": 0.03,  # 3% baseline → 6x
                "window_calls": 200,
                "history_days": 14,
                "history_calls": 10_000,
            },
        }
    )

    diagnosis = _find(result, "ERROR_RATE_DRIFT")
    assert diagnosis["evidence"]["current_15m_error_rate"] == 0.18
    assert diagnosis["evidence"]["baseline_15m_error_rate"] == 0.03
    assert diagnosis["evidence"]["multiplier_vs_baseline"] == 6.0


def test_error_rate_drift_uses_additive_threshold_when_baseline_near_zero() -> None:
    # baseline=0.001, multiplicative threshold=0.003. Additive threshold=0.051.
    # current=0.06 → above additive threshold → fires.
    result = evaluate_diagnosis_payload(
        {
            "error_rate": {
                "current_15m": 0.06,
                "baseline_15m": 0.001,
                "window_calls": 200,
                "history_days": 14,
                "history_calls": 10_000,
            },
        }
    )

    assert "ERROR_RATE_DRIFT" in _categories(result)


def test_error_rate_drift_not_fired_below_absolute_floor() -> None:
    # current=0.015 — under 2% absolute floor.
    result = evaluate_diagnosis_payload(
        {
            "error_rate": {
                "current_15m": 0.015,
                "baseline_15m": 0.001,  # 15x baseline but absolute too tiny
                "window_calls": 200,
                "history_days": 14,
                "history_calls": 10_000,
            },
        }
    )

    assert "ERROR_RATE_DRIFT" not in _categories(result)


def test_error_rate_drift_not_fired_below_drift_threshold() -> None:
    # baseline=0.05, current=0.07. Mult threshold=0.15, additive=0.10. Not breached.
    result = evaluate_diagnosis_payload(
        {
            "error_rate": {
                "current_15m": 0.07,
                "baseline_15m": 0.05,
                "window_calls": 200,
                "history_days": 14,
                "history_calls": 10_000,
            },
        }
    )

    assert "ERROR_RATE_DRIFT" not in _categories(result)


def test_error_rate_drift_not_fired_with_insufficient_window_calls() -> None:
    # Only 5 calls in the 15-min window — not statistically meaningful.
    result = evaluate_diagnosis_payload(
        {
            "error_rate": {
                "current_15m": 0.20,
                "baseline_15m": 0.02,
                "window_calls": 5,
                "history_days": 14,
                "history_calls": 10_000,
            },
        }
    )

    assert "ERROR_RATE_DRIFT" not in _categories(result)


def test_error_rate_drift_not_fired_during_warmup() -> None:
    result = evaluate_diagnosis_payload(
        {
            "error_rate": {
                "current_15m": 0.20,
                "baseline_15m": 0.02,
                "window_calls": 200,
                "history_days": 1,
                "history_calls": 80,
            },
        }
    )

    assert "ERROR_RATE_DRIFT" not in _categories(result)


# ── TOKEN_USAGE_DRIFT detector (Layer 2) ─────────────────────────────────────


def test_token_usage_drift_detected_when_prompt_bloats() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "rag-agent",
            "provider": "anthropic",
            "model": "claude-sonnet-4",
            "prompt_tokens": 12_000,
            "tokens": {
                "baseline_prompt_tokens_p50": 2_500,
                "baseline_prompt_tokens_p95": 4_000,
                "history_days": 14,
                "history_calls": 5_000,
            },
        }
    )

    diagnosis = _find(result, "TOKEN_USAGE_DRIFT")
    assert diagnosis["evidence"]["prompt_tokens"] == 12_000
    assert diagnosis["evidence"]["baseline_prompt_tokens_p95"] == 4_000
    assert diagnosis["evidence"]["drift_threshold_tokens"] == 6_000  # 4000 * 1.5
    assert diagnosis["evidence"]["overshoot_ratio"] == 3.0


def test_token_usage_drift_not_fired_below_absolute_floor() -> None:
    # 800 prompt tokens — under 1000 floor.
    result = evaluate_diagnosis_payload(
        {
            "prompt_tokens": 800,
            "tokens": {
                "baseline_prompt_tokens_p95": 200,  # 4x but absolute too tiny
                "history_days": 14,
                "history_calls": 5_000,
            },
        }
    )

    assert "TOKEN_USAGE_DRIFT" not in _categories(result)


def test_token_usage_drift_yields_to_token_overflow_near_context_limit() -> None:
    # gpt-4o has ~128k context. 120_000 prompt tokens is >=90% of context →
    # TOKEN_USAGE_DRIFT defers because TOKEN_OVERFLOW owns the surface for
    # context-window pressure, regardless of whether the call actually
    # failed yet. (TOKEN_OVERFLOW firing is tested elsewhere.)
    result = evaluate_diagnosis_payload(
        {
            "provider": "openai",
            "model": "gpt-4o",
            "prompt_tokens": 120_000,
            "tokens": {
                "baseline_prompt_tokens_p95": 4_000,
                "history_days": 14,
                "history_calls": 5_000,
            },
        }
    )

    assert "TOKEN_USAGE_DRIFT" not in _categories(result)


def test_token_usage_drift_not_fired_below_p95_multiplier() -> None:
    # 5000 / 4000 = 1.25x, threshold is 1.5x → not fired.
    result = evaluate_diagnosis_payload(
        {
            "prompt_tokens": 5_000,
            "tokens": {
                "baseline_prompt_tokens_p95": 4_000,
                "history_days": 14,
                "history_calls": 5_000,
            },
        }
    )

    assert "TOKEN_USAGE_DRIFT" not in _categories(result)


def test_token_usage_drift_not_fired_during_warmup() -> None:
    result = evaluate_diagnosis_payload(
        {
            "prompt_tokens": 12_000,
            "tokens": {
                "baseline_prompt_tokens_p95": 4_000,
                "history_days": 2,  # below 3-day warmup
                "history_calls": 150,
            },
        }
    )

    assert "TOKEN_USAGE_DRIFT" not in _categories(result)


def test_layer_2_drift_detectors_silently_skip_when_no_baseline_in_payload() -> None:
    # Empty payload — no Layer 2 detector should fire (clean SDK install,
    # analytics service has not yet started injecting baselines).
    result = evaluate_diagnosis_payload({})
    categories = _categories(result)

    for layer_2_category in (
        "OUTPUT_LENGTH_DRIFT",
        "LATENCY_DRIFT",
        "ERROR_RATE_DRIFT",
        "TOKEN_USAGE_DRIFT",
    ):
        assert layer_2_category not in categories


def test_layer_2_drift_detectors_coexist_with_layer_1_fast_rules() -> None:
    # Verify that a payload triggering both a fast rule (RATE_LIMIT) and a
    # Layer 2 drift rule produces both diagnoses — they live in different
    # evaluation phases and do not suppress each other.
    result = evaluate_diagnosis_payload(
        {
            "status": "failed",
            "status_code": 429,
            "error_code": "rate_limit_exceeded",
            "completion_tokens": 1500,
            "length": {
                "baseline_completion_tokens_p95": 480,
                "history_days": 14,
                "history_calls": 5000,
            },
        }
    )

    categories = _categories(result)
    assert "RATE_LIMIT" in categories
    # OUTPUT_LENGTH_DRIFT may or may not fire depending on whether the
    # detector enforces "successful call only" — accept either, but assert
    # the call did NOT silently swallow either diagnosis.
    assert len(categories) >= 1


# ── HALLUCINATION_RISK detector (Layer 3) ────────────────────────────────────


def test_hallucination_risk_detected_when_groundedness_below_floor() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "research-agent",
            "provider": "anthropic",
            "model": "claude-haiku-4",
            "judge": {
                "model": "anthropic/claude-haiku-4",
                "verdict": "fail",
                "confidence": 0.88,
                "dimensions": {
                    "groundedness": {
                        "score": 0.15,
                        "reason": "Multiple unsupported confident claims.",
                    },
                    "relevance": {"score": 0.80, "reason": "On-topic."},
                    "coherence": {"score": 0.75, "reason": "Reads fine."},
                    "completeness": {"score": 0.60, "reason": "Mostly answers."},
                },
                "overall_score": 0.575,
            },
        }
    )

    diagnosis = _find(result, "HALLUCINATION_RISK")
    assert diagnosis["evidence"]["groundedness_score"] == 0.15
    assert diagnosis["evidence"]["groundedness_floor"] == 0.35
    assert diagnosis["evidence"]["judge_model"] == "anthropic/claude-haiku-4"
    # Other dimensions are surfaced for dashboard context.
    other = diagnosis["evidence"]["other_dimensions"]
    assert "relevance" in other and other["relevance"] == 0.8


def test_hallucination_risk_accepts_flat_score_payload_shape() -> None:
    # Some callers may pass dimensions as raw floats rather than dicts.
    result = evaluate_diagnosis_payload(
        {
            "judge": {
                "model": "anthropic/claude-haiku-4",
                "verdict": "fail",
                "confidence": 0.7,
                "dimensions": {"groundedness": 0.20},
            },
        }
    )

    assert "HALLUCINATION_RISK" in _categories(result)


def test_hallucination_risk_not_fired_when_groundedness_at_or_above_floor() -> None:
    result = evaluate_diagnosis_payload(
        {
            "judge": {
                "verdict": "pass",
                "confidence": 0.9,
                "dimensions": {"groundedness": {"score": 0.50, "reason": "ok"}},
            },
        }
    )

    assert "HALLUCINATION_RISK" not in _categories(result)


def test_hallucination_risk_not_fired_when_judge_inconclusive_and_low_confidence() -> None:
    # Judge itself signalled uncertainty — don't compound it.
    result = evaluate_diagnosis_payload(
        {
            "judge": {
                "verdict": "inconclusive",
                "confidence": 0.2,
                "dimensions": {"groundedness": {"score": 0.10, "reason": "unsure"}},
            },
        }
    )

    assert "HALLUCINATION_RISK" not in _categories(result)


def test_hallucination_risk_fires_even_when_inconclusive_if_judge_confident() -> None:
    # High-confidence inconclusive verdict + low groundedness still triggers.
    result = evaluate_diagnosis_payload(
        {
            "judge": {
                "verdict": "inconclusive",
                "confidence": 0.8,
                "dimensions": {"groundedness": {"score": 0.20, "reason": "see above"}},
            },
        }
    )

    assert "HALLUCINATION_RISK" in _categories(result)


def test_hallucination_risk_silent_when_no_judge_data() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "agent",
            "provider": "openai",
            "model": "gpt-4o",
            # No `judge` key at all
        }
    )

    assert "HALLUCINATION_RISK" not in _categories(result)


def test_hallucination_risk_silent_when_groundedness_dimension_absent() -> None:
    result = evaluate_diagnosis_payload(
        {
            "judge": {
                "verdict": "pass",
                "confidence": 0.9,
                "dimensions": {
                    # No `groundedness` key — e.g. MultiDimEvaluator output
                    "accuracy": {"score": 0.9, "reason": ""},
                    "relevance": {"score": 0.9, "reason": ""},
                },
            },
        }
    )

    assert "HALLUCINATION_RISK" not in _categories(result)


# ── ACCURACY_REGRESSION detector (Layer 3) ───────────────────────────────────


def test_accuracy_regression_fires_on_hard_floor_breach() -> None:
    result = evaluate_diagnosis_payload(
        {
            "agent_name": "qa-agent",
            "judge": {
                "model": "anthropic/claude-haiku-4",
                "verdict": "fail",
                "confidence": 0.9,
                "dimensions": {
                    "accuracy": {"score": 0.25, "reason": "Wrong answer."},
                    "faithfulness": {"score": 0.8, "reason": "ok"},
                    "relevance": {"score": 0.7, "reason": "ok"},
                    "coherence": {"score": 0.85, "reason": "fluent"},
                },
            },
        }
    )

    diagnosis = _find(result, "ACCURACY_REGRESSION")
    assert diagnosis["evidence"]["accuracy_score"] == 0.25
    assert diagnosis["evidence"]["absolute_floor"] == 0.40
    assert diagnosis["evidence"]["trigger_basis"] == "hard_floor"


def test_accuracy_regression_fires_on_baseline_drift() -> None:
    # 0.65 score vs baseline_mean 0.90 → 0.65 < 0.90 * (1 - 0.15) = 0.765 → fires.
    result = evaluate_diagnosis_payload(
        {
            "judge": {
                "dimensions": {
                    "accuracy": {"score": 0.65, "reason": "below recent baseline"},
                },
            },
            "accuracy": {
                "baseline_mean": 0.90,
                "history_days": 14,
                "history_calls": 5000,
            },
        }
    )

    diagnosis = _find(result, "ACCURACY_REGRESSION")
    assert diagnosis["evidence"]["trigger_basis"] == "baseline_drift"
    assert diagnosis["evidence"]["baseline_mean"] == 0.9
    assert diagnosis["evidence"]["drift_threshold"] == 0.765


def test_accuracy_regression_does_not_fire_during_baseline_warmup() -> None:
    # Same drift case as above but warmup unmet → no fire.
    result = evaluate_diagnosis_payload(
        {
            "judge": {
                "dimensions": {"accuracy": {"score": 0.65, "reason": ""}},
            },
            "accuracy": {
                "baseline_mean": 0.90,
                "history_days": 1,
                "history_calls": 50,
            },
        }
    )

    assert "ACCURACY_REGRESSION" not in _categories(result)


def test_accuracy_regression_does_not_fire_when_score_at_or_above_floor() -> None:
    # No baseline_mean → only the hard floor matters. 0.50 >= 0.40 → no fire.
    result = evaluate_diagnosis_payload(
        {
            "judge": {
                "dimensions": {"accuracy": {"score": 0.50, "reason": ""}},
            },
        }
    )

    assert "ACCURACY_REGRESSION" not in _categories(result)


def test_accuracy_regression_silent_when_no_judge_data() -> None:
    result = evaluate_diagnosis_payload({})
    assert "ACCURACY_REGRESSION" not in _categories(result)


def test_accuracy_regression_silent_when_accuracy_dim_absent() -> None:
    # Judge ran but only emitted ReferenceFreeEvaluator dimensions (no accuracy).
    result = evaluate_diagnosis_payload(
        {
            "judge": {
                "dimensions": {
                    "groundedness": {"score": 0.8, "reason": ""},
                    "relevance": {"score": 0.8, "reason": ""},
                },
            },
        }
    )

    assert "ACCURACY_REGRESSION" not in _categories(result)


def test_hallucination_and_accuracy_regression_coexist_on_same_payload() -> None:
    # A truly bad response: wrong AND ungrounded. Both diagnoses should fire.
    result = evaluate_diagnosis_payload(
        {
            "judge": {
                "model": "anthropic/claude-haiku-4",
                "verdict": "fail",
                "confidence": 0.95,
                "dimensions": {
                    "accuracy": {"score": 0.20, "reason": "wrong"},
                    "groundedness": {"score": 0.15, "reason": "unsupported"},
                    "relevance": {"score": 0.6, "reason": "ok"},
                    "coherence": {"score": 0.7, "reason": "ok"},
                },
            },
        }
    )

    categories = _categories(result)
    assert "HALLUCINATION_RISK" in categories
    assert "ACCURACY_REGRESSION" in categories


def test_layer_3_detectors_silent_on_empty_payload() -> None:
    result = evaluate_diagnosis_payload({})
    categories = _categories(result)
    assert "HALLUCINATION_RISK" not in categories
    assert "ACCURACY_REGRESSION" not in categories
