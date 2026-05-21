"""
Contract + labeled eval set for the RATE_LIMIT detector plugin.
"""
from __future__ import annotations

import pytest

from app.services.detectors.rate_limit import detect
from app.services.detectors._registry import load_detectors

_CONFIDENCE = 0.95


def test_entry_point_registered_and_loadable() -> None:
    detectors = load_detectors()
    assert "rate_limit" in detectors
    assert callable(detectors["rate_limit"])


def test_entry_point_returns_correct_interface() -> None:
    detectors = load_detectors()
    result = detectors["rate_limit"]({"status_code": 429, "provider": "openai"})
    assert result is not None
    assert result["category"] == "RATE_LIMIT"
    assert 0.0 < result["confidence"] <= 1.0
    assert "evidence" in result
    assert "fix" in result


_FIXTURES: list[pytest.param] = [
    # ── TRUE POSITIVES ────────────────────────────────────────────────────────
    pytest.param(
        {"status_code": 429, "provider": "openai"},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_status_429_openai",
    ),
    pytest.param(
        {"response": {"status_code": 429}},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_response_nested_status_429",
    ),
    pytest.param(
        {"failure_reason": {"http_status": 429}},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_failure_reason_http_status_429",
    ),
    pytest.param(
        {"error_code": "RATE_LIMIT_EXCEEDED"},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_error_code_rate_limit_exceeded",
    ),
    pytest.param(
        {"error_code": "too_many_requests"},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_error_code_too_many_requests",
    ),
    pytest.param(
        {"error_code": "quota_exceeded"},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_error_code_quota_exceeded",
    ),
    pytest.param(
        {"error": {"code": "rate_limit"}},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_error_nested_code_rate_limit",
    ),
    pytest.param(
        {"error": {"type": "too_many_requests"}},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_error_nested_type_too_many_requests",
    ),
    pytest.param(
        {"failure_reason": {"provider_error_code": "rate_limit_exceeded"}},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_failure_reason_provider_error_code",
    ),
    pytest.param(
        {"failure_reason": {"classification": "rate_limit"}},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_failure_reason_classification",
    ),
    pytest.param(
        {"error_message": "Rate limit exceeded. Please retry after 30 seconds."},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_error_message_rate_limit_exceeded",
    ),
    pytest.param(
        {"error_message": "Too many requests in 60 seconds."},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_error_message_too_many_requests",
    ),
    pytest.param(
        {"error_message": "API quota exceeded for project."},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_error_message_quota",
    ),
    pytest.param(
        {
            "status_code": 429,
            "provider": "anthropic",
            "failure_reason": {"retry_after_seconds": 30.0},
        },
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_with_retry_after_anthropic",
    ),
    pytest.param(
        {
            "status_code": 429,
            "provider": "openai",
            "failure_reason": {"provider_request_id": "req_abc123"},
        },
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_with_provider_request_id",
    ),
    pytest.param(
        {"error_code": "RATE_LIMIT", "provider": "cohere"},
        "RATE_LIMIT", (_CONFIDENCE, 1.0),
        id="tp_error_code_rate_limit_cohere",
    ),
    # ── FALSE POSITIVES ───────────────────────────────────────────────────────
    pytest.param(
        {"status_code": 401, "error_code": "invalid_api_key"},
        None, None,
        id="fp_auth_401",
    ),
    pytest.param(
        {"status_code": 403},
        None, None,
        id="fp_forbidden_403",
    ),
    pytest.param(
        {"status_code": 500, "error_message": "Internal server error"},
        None, None,
        id="fp_internal_server_error",
    ),
    pytest.param(
        {"status_code": 503},
        None, None,
        id="fp_service_unavailable",
    ),
    pytest.param(
        {"error_code": "TOKEN_OVERFLOW"},
        None, None,
        id="fp_token_overflow_not_rate_limit",
    ),
    pytest.param(
        {},
        None, None,
        id="fp_empty_payload",
    ),
    pytest.param(
        {"status": "success", "provider": "openai"},
        None, None,
        id="fp_successful_call",
    ),
]


@pytest.mark.parametrize("payload,expected_category,confidence_range", _FIXTURES)
def test_rate_limit_fixture(
    payload: dict,
    expected_category: str | None,
    confidence_range: tuple[float, float] | None,
) -> None:
    result = detect(payload)

    if expected_category is None:
        assert result is None, f"Expected None but got: {result}"
    else:
        assert result is not None
        assert result["category"] == expected_category
        assert "evidence" in result
        assert "fix" in result
        if confidence_range is not None:
            lo, hi = confidence_range
            assert lo <= result["confidence"] <= hi
