"""
Contract + labeled eval set for the COST_SPIKE detector plugin.

Cost spike requires warmup (history_days >= 3, history_calls >= 200).
Trigger: current_15m_spend > max(3 * baseline, baseline + 25 USD).
Returns a 2-tuple; detect_entry() wraps it to satisfy the Detector Protocol.
"""
from __future__ import annotations

import pytest

from app.services.detectors.cost_spike import detect, detect_entry
from app.services.detectors._registry import load_detectors

_CONFIDENCE = 0.90

# Warmup-ready baseline
_WARMUP = {"history_days": 5.0, "history_calls": 300}


def test_entry_point_registered_and_loadable() -> None:
    detectors = load_detectors()
    assert "cost_spike" in detectors
    assert callable(detectors["cost_spike"])


def test_entry_point_shim_returns_dict_or_none() -> None:
    """detect_entry must return dict | None (Protocol-compatible)."""
    result = detect_entry(
        {
            "current_15m_spend_usd": 200.0,
            "baseline_15m_spend_usd": 5.0,
            **_WARMUP,
        }
    )
    assert result is not None
    assert result["category"] == "COST_SPIKE"


def test_raw_detect_returns_tuple() -> None:
    """Raw detect() must return tuple[dict | None, dict | None]."""
    primary, informational = detect(
        {
            "current_15m_spend_usd": 200.0,
            "baseline_15m_spend_usd": 5.0,
            **_WARMUP,
        }
    )
    assert primary is not None
    assert primary["category"] == "COST_SPIKE"
    assert informational is None


# ── labeled eval fixtures — test via detect_entry for Protocol consistency ────

_FIXTURES: list[pytest.param] = [
    # ── TRUE POSITIVES ────────────────────────────────────────────────────────
    pytest.param(
        {
            "current_15m_spend_usd": 200.0,
            "baseline_15m_spend_usd": 5.0,
            **_WARMUP,
        },
        "COST_SPIKE", (_CONFIDENCE, 1.0),
        id="tp_massive_spike_over_hard_floor",
    ),
    pytest.param(
        {
            "current_15m_spend_usd": 60.0,
            "baseline_15m_spend_usd": 10.0,
            **_WARMUP,
        },
        "COST_SPIKE", (_CONFIDENCE, 1.0),
        id="tp_3x_baseline_exceeds_hard_floor",
    ),
    pytest.param(
        {
            "current_15m_spend_usd": 50.0,
            "baseline_15m_spend_usd": 0.0,
            **_WARMUP,
        },
        "COST_SPIKE", (_CONFIDENCE, 1.0),
        id="tp_zero_baseline_over_hard_floor_25",
    ),
    pytest.param(
        {
            "cost": {
                "current_15m_spend_usd": 100.0,
                "baseline_15m_spend_usd": 8.0,
            },
            **_WARMUP,
        },
        "COST_SPIKE", (_CONFIDENCE, 1.0),
        id="tp_nested_cost_dict",
    ),
    pytest.param(
        {
            "spend": {"current_15m": 80.0, "baseline_15m": 5.0},
            **_WARMUP,
        },
        "COST_SPIKE", (_CONFIDENCE, 1.0),
        id="tp_spend_nested_dict",
    ),
    pytest.param(
        {
            "current_15m_spend_usd": 120.0,
            "baseline_15m_spend_usd": 10.0,
            "model_spend_coefficient": 2.0,
            **_WARMUP,
        },
        "COST_SPIKE", (_CONFIDENCE, 1.0),
        id="tp_with_model_coefficient",
    ),
    # ── FALSE POSITIVES — must return None ───────────────────────────────────
    pytest.param(
        {},
        None, None,
        id="fp_empty_payload",
    ),
    pytest.param(
        {"current_15m_spend_usd": 0.0, "baseline_15m_spend_usd": 0.0},
        None, None,
        id="fp_both_zero",
    ),
    pytest.param(
        {"current_15m_spend_usd": 0.0, "baseline_15m_spend_usd": 5.0},
        None, None,
        id="fp_zero_current_spend",
    ),
    pytest.param(
        {
            "current_15m_spend_usd": 20.0,
            "baseline_15m_spend_usd": 10.0,
            **_WARMUP,
        },
        None, None,
        id="fp_2x_baseline_below_hard_floor_threshold",
    ),
    pytest.param(
        {
            "current_15m_spend_usd": 5.0,
            "baseline_15m_spend_usd": 10.0,
            **_WARMUP,
        },
        None, None,
        id="fp_spend_decrease",
    ),
    pytest.param(
        {
            "current_15m_spend_usd": 100.0,
            "baseline_15m_spend_usd": 5.0,
            "history_days": 1.0,
            "history_calls": 50,
        },
        None, None,
        id="fp_warmup_not_ready",
    ),
    pytest.param(
        {
            "current_15m_spend_usd": 100.0,
            "baseline_15m_spend_usd": 5.0,
            "history_days": 5.0,
            "history_calls": 100,
        },
        None, None,
        id="fp_warmup_calls_below_200",
    ),
    pytest.param(
        {
            "current_15m_spend_usd": 100.0,
            "baseline_15m_spend_usd": 5.0,
            "history_days": 2.0,
            "history_calls": 300,
        },
        None, None,
        id="fp_warmup_days_below_3",
    ),
]


@pytest.mark.parametrize("payload,expected_category,confidence_range", _FIXTURES)
def test_cost_spike_fixture(
    payload: dict,
    expected_category: str | None,
    confidence_range: tuple[float, float] | None,
) -> None:
    result = detect_entry(payload)

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


def test_informational_surge_warning_before_warmup() -> None:
    """Pre-warmup surge emits informational-only, no COST_SPIKE diagnosis."""
    primary, info = detect(
        {
            "current_15m_spend_usd": 50.0,
            "baseline_15m_spend_usd": 5.0,
            "history_days": 1.0,
            "history_calls": 50,
        }
    )
    assert primary is None
    assert info is not None
    assert info["type"] == "COST_SURGE_WARNING"


def test_evidence_contains_threshold_fields() -> None:
    primary, _ = detect(
        {
            "current_15m_spend_usd": 100.0,
            "baseline_15m_spend_usd": 5.0,
            **_WARMUP,
        }
    )
    assert primary is not None
    ev = primary["evidence"]
    assert "hard_threshold_15m_spend_usd" in ev
    assert "current_15m_spend_usd" in ev
    assert ev["warmup_gate_met"] is True
