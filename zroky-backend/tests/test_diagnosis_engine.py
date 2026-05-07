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


def test_rate_limit_uses_provider_status_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.diagnosis_engine.resolve_provider_status_context",
        lambda **_kwargs: {
            "provider_status": "degraded",
            "provider_latency_p95_ms": 1450,
            "provider_latency_p99_ms": 2600,
            "status_fetch_timeout_ms": 777,
            "status_cache_ttl_seconds": 222,
            "status_fallback_used": True,
        },
    )

    result = evaluate_diagnosis_payload(
        {
            "provider": "openai",
            "status_code": 429,
            "error_code": "rate_limit_exceeded",
        }
    )

    diagnosis = _find(result, "RATE_LIMIT")
    evidence = diagnosis["evidence"]
    assert evidence["provider_status"] == "degraded"
    assert evidence["provider_latency_p95_ms"] == 1450
    assert evidence["provider_latency_p99_ms"] == 2600
    assert evidence["status_fetch_timeout_ms"] == 777
    assert evidence["status_cache_ttl_seconds"] == 222


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
