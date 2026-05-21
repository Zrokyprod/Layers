"""
Contract + labeled eval set for the AUTH_FAILURE detector plugin.
"""
from __future__ import annotations

import pytest

from app.services.detectors.auth_failure import detect
from app.services.detectors._registry import load_detectors

_CONFIDENCE = 0.99


def test_entry_point_registered_and_loadable() -> None:
    detectors = load_detectors()
    assert "auth_failure" in detectors
    assert callable(detectors["auth_failure"])


def test_entry_point_returns_correct_interface() -> None:
    detectors = load_detectors()
    result = detectors["auth_failure"]({"status_code": 401, "provider": "openai"})
    assert result is not None
    assert result["category"] == "AUTH_FAILURE"
    assert 0.0 < result["confidence"] <= 1.0
    assert "evidence" in result
    assert "fix" in result


_FIXTURES: list[pytest.param] = [
    # ── TRUE POSITIVES ────────────────────────────────────────────────────────
    pytest.param(
        {"status_code": 401, "provider": "openai"},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_status_401_openai",
    ),
    pytest.param(
        {"status_code": 403, "provider": "anthropic"},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_status_403_anthropic",
    ),
    pytest.param(
        {"response": {"status_code": 401}},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_response_nested_401",
    ),
    pytest.param(
        {"failure_reason": {"http_status": 403}},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_failure_reason_http_403",
    ),
    pytest.param(
        {"error_code": "invalid_api_key"},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_error_code_invalid_api_key",
    ),
    pytest.param(
        {"error_code": "INVALID_KEY"},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_error_code_invalid_key",
    ),
    pytest.param(
        {"error_code": "expired_key"},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_error_code_expired_key",
    ),
    pytest.param(
        {"error_code": "expired_token"},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_error_code_expired_token",
    ),
    pytest.param(
        {"error_code": "UNAUTHORIZED"},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_error_code_unauthorized",
    ),
    pytest.param(
        {"error_code": "FORBIDDEN"},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_error_code_forbidden",
    ),
    pytest.param(
        {"error": {"code": "invalid_api_key"}},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_error_nested_code_invalid_api_key",
    ),
    pytest.param(
        {"failure_reason": {"classification": "auth_failure"}},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_failure_reason_classification",
    ),
    pytest.param(
        {"failure_reason": {"provider_error_code": "unauthorized"}},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_failure_reason_provider_error_code",
    ),
    pytest.param(
        {"error_message": "Unauthorized: invalid API key provided."},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_error_message_unauthorized",
    ),
    pytest.param(
        {"error_message": "Invalid API key. Please check your credentials."},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_error_message_invalid_api_key",
    ),
    pytest.param(
        {"error_message": "Authentication failed: token has expired."},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_error_message_auth_failed",
    ),
    pytest.param(
        {"error_message": "Access forbidden for this resource."},
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_error_message_forbidden",
    ),
    pytest.param(
        {
            "status_code": 401,
            "provider": "openai",
            "failure_reason": {"provider_request_id": "req_xyz789"},
        },
        "AUTH_FAILURE", (_CONFIDENCE, 1.0),
        id="tp_with_provider_request_id",
    ),
    # ── FALSE POSITIVES ───────────────────────────────────────────────────────
    pytest.param(
        {"status_code": 429, "error_code": "rate_limit_exceeded"},
        None, None,
        id="fp_rate_limit_429",
    ),
    pytest.param(
        {"status_code": 500},
        None, None,
        id="fp_server_error_500",
    ),
    pytest.param(
        {"status_code": 503},
        None, None,
        id="fp_service_unavailable",
    ),
    pytest.param(
        {"error_code": "TOKEN_OVERFLOW"},
        None, None,
        id="fp_token_overflow",
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
    pytest.param(
        {"error_message": "Internal server error occurred."},
        None, None,
        id="fp_generic_error_message",
    ),
]


@pytest.mark.parametrize("payload,expected_category,confidence_range", _FIXTURES)
def test_auth_failure_fixture(
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
