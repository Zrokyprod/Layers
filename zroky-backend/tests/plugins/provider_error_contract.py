"""
Contract + labeled eval set for the PROVIDER_ERROR detector plugin.

PROVIDER_ERROR is the fallback detector — it must NOT fire when a more
specific detector (TOKEN_OVERFLOW, RATE_LIMIT, AUTH_FAILURE) already owns
the signal.
"""
from __future__ import annotations

import pytest

from app.services.detectors.provider_error import detect
from app.services.detectors._registry import load_detectors


def test_entry_point_registered_and_loadable() -> None:
    detectors = load_detectors()
    assert "provider_error" in detectors
    assert callable(detectors["provider_error"])


def test_entry_point_returns_correct_interface() -> None:
    detectors = load_detectors()
    result = detectors["provider_error"]({"status_code": 500, "provider": "openai"})
    assert result is not None
    assert result["category"] == "PROVIDER_ERROR"
    assert 0.0 < result["confidence"] <= 1.0
    assert "evidence" in result
    assert "fix" in result


_FIXTURES: list[pytest.param] = [
    # ── TRUE POSITIVES ────────────────────────────────────────────────────────
    pytest.param(
        {"status_code": 500, "provider": "openai"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_generic_500",
    ),
    pytest.param(
        {"status_code": 503, "provider": "anthropic"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_service_unavailable_503",
    ),
    pytest.param(
        {"status_code": 502, "provider": "cohere"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_bad_gateway_502",
    ),
    pytest.param(
        {"status_code": 504, "provider": "openai"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_gateway_timeout_504_subtype_timeout",
    ),
    pytest.param(
        {"status_code": 408, "error_message": "Request timed out"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_request_timeout_408",
    ),
    pytest.param(
        {"error_code": "server_error", "status_code": 500},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_error_code_server_error",
    ),
    pytest.param(
        {"error_code": "internal_error"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_error_code_internal_error",
    ),
    pytest.param(
        {"error_message": "timeout waiting for upstream response"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_error_message_timeout",
    ),
    pytest.param(
        {"error_message": "Connection reset by peer"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_error_message_network_reset",
    ),
    pytest.param(
        {"error_message": "DNS resolution failed for api.openai.com"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_error_message_dns_failure",
    ),
    pytest.param(
        {"error_code": "content_filter", "provider": "azure"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_content_filter_subtype",
    ),
    pytest.param(
        {"error_message": "content policy violation: request rejected"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_error_message_content_policy",
    ),
    pytest.param(
        {"status_code": 400, "error_message": "Invalid request parameters"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_bad_request_400",
    ),
    pytest.param(
        {"status": "failed", "provider": "openai", "model": "gpt-4"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_status_failed",
    ),
    pytest.param(
        {
            "failure_reason": {
                "http_status": 500,
                "provider_error_code": "server_error",
                "provider_request_id": "req_abc123",
            }
        },
        "PROVIDER_ERROR", (0.70, 0.90),
        id="tp_structured_failure_reason",
    ),
    pytest.param(
        {"status": "timeout", "provider": "openai"},
        "PROVIDER_ERROR", (0.60, 0.90),
        id="tp_status_timeout",
    ),
    # ── FALSE POSITIVES — must yield None (owned by more specific detectors) ─
    pytest.param(
        {"status_code": 429},
        None, None,
        id="fp_rate_limit_429_excluded",
    ),
    pytest.param(
        {"status_code": 401},
        None, None,
        id="fp_auth_401_excluded",
    ),
    pytest.param(
        {"status_code": 403},
        None, None,
        id="fp_auth_403_excluded",
    ),
    pytest.param(
        {"error_code": "TOKEN_OVERFLOW"},
        None, None,
        id="fp_token_overflow_excluded",
    ),
    pytest.param(
        {"error_code": "RATE_LIMIT"},
        None, None,
        id="fp_rate_limit_code_excluded",
    ),
    pytest.param(
        {"error_code": "AUTH_FAILURE"},
        None, None,
        id="fp_auth_failure_code_excluded",
    ),
    pytest.param(
        {},
        None, None,
        id="fp_empty_payload",
    ),
    pytest.param(
        {"status": "success"},
        None, None,
        id="fp_successful_call",
    ),
]


@pytest.mark.parametrize("payload,expected_category,confidence_range", _FIXTURES)
def test_provider_error_fixture(
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
            assert lo <= result["confidence"] <= hi, (
                f"confidence {result['confidence']:.3f} not in [{lo}, {hi}]"
            )


def test_subtype_timeout_for_504() -> None:
    result = detect({"status_code": 504, "provider": "openai"})
    assert result is not None
    assert result["subtype"] == "timeout"


def test_subtype_network_for_connection_reset() -> None:
    result = detect({"error_message": "Connection reset by peer"})
    assert result is not None
    assert result["subtype"] == "network"
