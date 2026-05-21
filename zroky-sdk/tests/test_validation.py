# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

import copy
import time

import zroky


def test_validate_long_input_triggers_token_overflow() -> None:
    payload = {
        "model": "gpt-3.5-turbo",
        "api_key": "sk-test-1234567890abcdef",
        "messages": [{"role": "user", "content": "x" * 16000}],
    }

    result = zroky.validate(payload)

    assert result["valid"] is False
    warning_types = {warning["type"] for warning in result["warnings"]}
    assert "TOKEN_OVERFLOW" in warning_types

    token_warning = next(
        warning for warning in result["warnings"] if warning["type"] == "TOKEN_OVERFLOW"
    )
    assert token_warning["confidence"] >= 0.9
    assert "Estimated prompt size" in token_warning["message"]


def test_validate_normal_input_returns_no_warnings() -> None:
    payload = {
        "model": "gpt-4o",
        "api_key": "sk-test-1234567890abcdef",
        "messages": [{"role": "user", "content": "Summarize this sentence."}],
    }

    result = zroky.validate(payload)

    assert result == {"valid": True, "warnings": []}


def test_validate_missing_api_key_triggers_auth_risk() -> None:
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello"}],
    }

    result = zroky.validate(payload)

    assert result["valid"] is False
    warning_types = {warning["type"] for warning in result["warnings"]}
    assert "AUTH_RISK" in warning_types


def test_validate_valid_api_key_is_silent_for_auth_risk() -> None:
    payload = {
        "model": "gpt-4o",
        "api_key": "sk-valid-1234567890abcdef",
        "messages": [{"role": "user", "content": "Hello"}],
    }

    result = zroky.validate(payload)
    warning_types = {warning["type"] for warning in result["warnings"]}
    assert "AUTH_RISK" not in warning_types


def test_validate_does_not_mutate_payload() -> None:
    payload = {
        "model": "gpt-4",
        "api_key": "sk-test-1234567890abcdef",
        "meta": {"recent_calls": 5},
        "messages": [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Hello"},
        ],
    }
    snapshot = copy.deepcopy(payload)

    _ = zroky.validate(payload)

    assert payload == snapshot


def test_validate_unknown_model_reports_unknown_context_limit() -> None:
    payload = {
        "model": "unknown-model",
        "api_key": "sk-test-1234567890abcdef",
        "messages": [{"role": "user", "content": "x" * 16000}],
    }

    result = zroky.validate(payload)

    warning_types = {warning["type"] for warning in result["warnings"]}
    assert "TOKEN_OVERFLOW" not in warning_types
    assert "TOKEN_CONTEXT_LIMIT_UNKNOWN" in warning_types

    warning = next(
        item for item in result["warnings"] if item["type"] == "TOKEN_CONTEXT_LIMIT_UNKNOWN"
    )
    assert warning["model_context_limit"] is None
    assert warning["model_context_limit_source"] == "unknown"
    assert warning["model_context_limit_catalog_version"] == "model_context_limits_2026_05_05"


def test_token_overflow_does_not_trigger_at_70_percent() -> None:
    payload = {
        "model": "gpt-4",
        "api_key": "sk-test-1234567890abcdef",
        "messages": [{"role": "user", "content": "short"}],
    }

    warning = zroky.check_token_overflow(payload | {"meta": {}}, estimated_tokens=5734)  # type: ignore[arg-type]
    assert warning is None


def test_token_overflow_triggers_at_90_percent_threshold() -> None:
    payload = {
        "model": "gpt-4",
        "api_key": "sk-test-1234567890abcdef",
        "messages": [{"role": "user", "content": "short"}],
    }

    warning = zroky.check_token_overflow(payload | {"meta": {}}, estimated_tokens=7372)  # type: ignore[arg-type]
    assert warning is not None
    assert warning["type"] == "TOKEN_OVERFLOW"
    assert warning["confidence"] >= 0.9


def test_rate_limit_risk_triggers_only_for_heavy_or_burst_cases() -> None:
    normal_payload = {
        "model": "gpt-4",
        "api_key": "sk-test-1234567890abcdef",
        "meta": {"recent_calls": 2},
        "messages": [{"role": "user", "content": "normal request"}],
    }
    burst_payload = {
        "model": "gpt-4",
        "api_key": "sk-test-1234567890abcdef",
        "meta": {"recent_calls": 25},
        "messages": [{"role": "user", "content": "normal request"}],
    }

    normal_warning = zroky.check_rate_limit_risk(normal_payload)
    burst_warning = zroky.check_rate_limit_risk(burst_payload)
    heavy_warning = zroky.check_rate_limit_risk(normal_payload, estimated_tokens=7000)  # type: ignore[arg-type]

    assert normal_warning is None
    assert burst_warning is not None and burst_warning["type"] == "RATE_LIMIT_RISK"
    assert heavy_warning is not None and heavy_warning["type"] == "RATE_LIMIT_RISK"


def test_estimate_tokens_handles_non_string_content() -> None:
    payload = {
        "model": "gpt-4o",
        "api_key": "sk-test-1234567890abcdef",
        "messages": [
            {"role": "user", "content": 12345},
            {"role": "assistant", "content": {"text": "nested"}},
            {"role": "user", "content": ["a", "b", "c"]},
        ],
    }

    estimate = zroky.estimate_tokens(payload)

    assert isinstance(estimate, int)
    assert estimate > 0

    result = zroky.validate(payload)
    assert isinstance(result["warnings"], list)


def test_print_validation_shows_warning_lines(capsys) -> None:
    validation_result = {
        "valid": False,
        "warnings": [
            {
                "type": "TOKEN_OVERFLOW",
                "confidence": 0.92,
                "message": "Estimated prompt size is high.",
                "suggested_fix": "Truncate input.",
            }
        ],
    }

    zroky.print_validation(validation_result)
    output = capsys.readouterr().out

    assert "[ZROKY] ⚠️ TOKEN_OVERFLOW risk detected (confidence: 0.92)" in output
    assert "Suggested fix: Truncate input." in output


def test_print_validation_suppresses_repeated_warning_spam(capsys) -> None:
    validation_result = {
        "valid": False,
        "warnings": [
            {
                "type": "TOKEN_OVERFLOW",
                "confidence": 0.92,
                "message": "Spam-check marker: token risk.",
                "suggested_fix": "Truncate input.",
            }
        ],
    }

    for _ in range(5):
        zroky.print_validation(validation_result)

    output = capsys.readouterr().out
    warning_count = output.count("[ZROKY] ⚠️ TOKEN_OVERFLOW risk detected")
    assert 1 <= warning_count <= 2


def test_print_validation_shows_safe_line(capsys) -> None:
    zroky.print_validation({"valid": True, "warnings": []})
    output = capsys.readouterr().out

    assert "[ZROKY] ✅ Payload looks safe" in output


def test_validate_real_world_mixed_payload_is_stable() -> None:
    payload = {
        "model": "gpt-4o",
        "api_key": "sk-test-1234567890abcdef",
        "meta": {"recent_calls": 22},
        "tools": [
            {"type": "function", "function": {"name": "search"}},
            {"type": "function", "function": {"name": "calculator"}},
        ],
        "messages": [
            {"role": "system", "content": "You are a precise assistant."},
            {"role": "user", "content": "Analyze this report and summarize risk trends."},
            {"role": "assistant", "content": "Sure, share the report details."},
            {"role": "user", "content": "x" * 20000},
        ],
    }

    result = zroky.validate(payload)

    assert isinstance(result, dict)
    assert isinstance(result.get("valid"), bool)
    warnings = result.get("warnings")
    assert isinstance(warnings, list)
    for warning in warnings:
        assert isinstance(warning.get("type"), str)
        assert isinstance(warning.get("message"), str)
        assert isinstance(warning.get("suggested_fix"), str)


def test_validate_performance_sanity() -> None:
    payload = {
        "model": "gpt-4o",
        "api_key": "sk-test-1234567890abcdef",
        "messages": [{"role": "user", "content": "Quick summary request."}],
    }

    start = time.perf_counter()
    for _ in range(2000):
        result = zroky.validate(payload)
        assert isinstance(result["warnings"], list)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0
