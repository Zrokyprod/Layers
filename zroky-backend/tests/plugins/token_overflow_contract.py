"""
Contract + labeled eval set for the TOKEN_OVERFLOW detector plugin.

Rules:
  - Every fixture must have a unique id.
  - True-positive fixtures declare expected_category = "TOKEN_OVERFLOW".
  - False-positive (negative) fixtures declare expected_category = None.
  - Confidence range is only asserted for true-positive fixtures.
"""
from __future__ import annotations

import pytest

from app.services.detectors.token_overflow import detect
from app.services.detectors._registry import load_detectors

# ── contract: entry-point loads and satisfies Protocol ───────────────────────

def test_entry_point_registered_and_loadable() -> None:
    detectors = load_detectors()
    assert "token_overflow" in detectors, "token_overflow not found in detector registry"
    fn = detectors["token_overflow"]
    assert callable(fn)


def test_entry_point_returns_correct_interface() -> None:
    detectors = load_detectors()
    result = detectors["token_overflow"](
        {"error_code": "TOKEN_OVERFLOW", "provider": "openai", "model": "gpt-4o"}
    )
    assert result is not None
    assert result["category"] == "TOKEN_OVERFLOW"
    assert 0.0 < result["confidence"] <= 1.0
    assert "evidence" in result
    assert "fix" in result


# ── labeled eval fixtures ─────────────────────────────────────────────────────

_FIXTURES: list[pytest.param] = [
    # ── TRUE POSITIVES ────────────────────────────────────────────────────────
    pytest.param(
        {"error_code": "TOKEN_OVERFLOW", "provider": "openai", "model": "gpt-4o"},
        "TOKEN_OVERFLOW", (0.94, 1.0),
        id="tp_error_code_direct",
    ),
    pytest.param(
        {"error": {"code": "TOKEN_OVERFLOW"}, "provider": "openai"},
        "TOKEN_OVERFLOW", (0.94, 1.0),
        id="tp_error_code_nested_path",
    ),
    pytest.param(
        {"failure_reason": {"classification": "TOKEN_OVERFLOW"}},
        "TOKEN_OVERFLOW", (0.94, 1.0),
        id="tp_error_code_failure_reason_classification",
    ),
    pytest.param(
        {"failure_reason": {"provider_error_code": "token_overflow"}},
        "TOKEN_OVERFLOW", (0.94, 1.0),
        id="tp_error_code_failure_reason_provider_error_code",
    ),
    pytest.param(
        {"error_message": "This request exceeds the maximum context length: too many tokens."},
        "TOKEN_OVERFLOW", (0.75, 0.90),
        id="tp_error_message_too_many_tokens",
    ),
    pytest.param(
        {"error_message": "context length exceeded: 5000 tokens vs limit 4096"},
        "TOKEN_OVERFLOW", (0.75, 0.90),
        id="tp_error_message_context_length_exceeded",
    ),
    pytest.param(
        {"error_message": "maximum context length for this model is 4096 tokens"},
        "TOKEN_OVERFLOW", (0.75, 0.90),
        id="tp_error_message_maximum_context_length",
    ),
    pytest.param(
        {"error_message": "max_tokens is too large: 8192 > 4096"},
        "TOKEN_OVERFLOW", (0.75, 0.90),
        id="tp_error_message_max_tokens_too_large",
    ),
    pytest.param(
        {
            "prompt_tokens": 5000,
            "model_limit_tokens": 4096,
            "conversation_turns": 1,
        },
        "TOKEN_OVERFLOW", (0.94, 1.0),
        id="tp_usage_over_limit_single_call",
    ),
    pytest.param(
        {
            "system_prompt_tokens": 2500,
            "user_message_tokens": 2000,
            "model_limit_tokens": 4096,
        },
        "TOKEN_OVERFLOW", (0.94, 1.0),
        id="tp_combined_system_user_over_limit",
    ),
    pytest.param(
        {
            "estimated_prompt_tokens": 3700,
            "model_context_limit": 4096,
        },
        "TOKEN_OVERFLOW", (0.65, 0.90),
        id="tp_estimate_90pct_explicit_limit",
    ),
    pytest.param(
        {
            "estimated_prompt_tokens": 3950,
            "model_context_limit": 4096,
        },
        "TOKEN_OVERFLOW", (0.75, 0.90),
        id="tp_estimate_96pct_explicit_limit",
    ),
    pytest.param(
        {
            "estimated_prompt_tokens": 4050,
            "model_context_limit": 4096,
        },
        "TOKEN_OVERFLOW", (0.80, 0.90),
        id="tp_estimate_99pct_explicit_limit",
    ),
    pytest.param(
        {
            "model": "gpt-3.5-turbo",
            "estimated_prompt_tokens": 3900,
        },
        "TOKEN_OVERFLOW", (0.65, 0.90),
        id="tp_estimate_gpt35_catalog_limit",
    ),
    pytest.param(
        {
            "model": "gpt-4o",
            "estimated_prompt_tokens": 120000,
        },
        "TOKEN_OVERFLOW", (0.65, 0.90),
        id="tp_estimate_gpt4o_catalog_limit_128k",
    ),
    pytest.param(
        {
            "prompt_tokens": 5000,
            "model_limit_tokens": 4096,
            "conversation_turns": 9,
            "history_tokens": 2300,
        },
        "TOKEN_OVERFLOW", (0.94, 1.0),
        id="tp_conversation_accumulation_subtype",
    ),
    pytest.param(
        {
            "usage": {"prompt_tokens": 5500, "estimated_prompt_tokens": 5500},
            "model_context_limit": 4096,
        },
        "TOKEN_OVERFLOW", (0.65, 1.0),
        id="tp_usage_nested_dict",
    ),
    pytest.param(
        {
            "status": "failed",
            "provider": "anthropic",
            "model": "claude-3-opus-20240229",
            "error_code": "TOKEN_OVERFLOW",
        },
        "TOKEN_OVERFLOW", (0.94, 1.0),
        id="tp_anthropic_provider_error_code",
    ),
    # ── FALSE POSITIVES (must return None) ───────────────────────────────────
    pytest.param(
        {"prompt_tokens": 2000, "model_limit_tokens": 4096},
        None, None,
        id="fp_50pct_under_limit",
    ),
    pytest.param(
        {"estimated_prompt_tokens": 3600, "model_context_limit": 4096},
        None, None,
        id="fp_estimate_below_90pct_threshold",
    ),
    pytest.param(
        {},
        None, None,
        id="fp_empty_payload",
    ),
    pytest.param(
        {"status": "success", "provider": "openai", "model": "gpt-4o"},
        None, None,
        id="fp_successful_call",
    ),
    pytest.param(
        {"status_code": 500, "error_message": "Internal server error"},
        None, None,
        id="fp_generic_500_no_token_signals",
    ),
    pytest.param(
        {"status_code": 429, "error_code": "RATE_LIMIT_EXCEEDED"},
        None, None,
        id="fp_rate_limit_not_token_overflow",
    ),
    pytest.param(
        {"status_code": 401, "error_code": "invalid_api_key"},
        None, None,
        id="fp_auth_failure_not_token_overflow",
    ),
]


@pytest.mark.parametrize("payload,expected_category,confidence_range", _FIXTURES)
def test_token_overflow_fixture(
    payload: dict,
    expected_category: str | None,
    confidence_range: tuple[float, float] | None,
) -> None:
    result = detect(payload)

    if expected_category is None:
        assert result is None, (
            f"Expected None (false-positive guard) but got: {result}"
        )
    else:
        assert result is not None, f"Expected {expected_category} diagnosis but got None"
        assert result["category"] == expected_category
        assert "evidence" in result
        assert "fix" in result
        if confidence_range is not None:
            lo, hi = confidence_range
            assert lo <= result["confidence"] <= hi, (
                f"Confidence {result['confidence']:.3f} outside [{lo}, {hi}]"
            )
