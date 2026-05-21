"""
Contract + labeled eval set for the LOOP_DETECTED detector plugin.

Loop detection is a multi-signal pattern rule (score >= 0.65 required).
Signals: prompt_repeat, output_fingerprint, tool_cycle, retry_pattern.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.detectors.loop import detect, detect_entry
from app.services.detectors._registry import load_detectors

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_entry_point_registered_and_loadable() -> None:
    detectors = load_detectors()
    assert "loop_detected" in detectors
    assert callable(detectors["loop_detected"])


def test_entry_point_shim_accepts_now_kwarg() -> None:
    """detect_entry must accept optional now= kwarg."""
    result = detect_entry(
        {
            "repeat_count": 6,
            "repeat_window_seconds": 60,
            "no_progress": True,
            "prompt_fingerprint": "fp-abc",
        },
        now=_NOW,
    )
    assert result is not None
    assert result["category"] == "LOOP_DETECTED"


def test_entry_point_shim_defaults_to_current_utc_when_now_omitted() -> None:
    """detect_entry without now= kwarg must not raise."""
    result = detect_entry(
        {
            "repeat_count": 6,
            "repeat_window_seconds": 60,
            "no_progress": True,
        }
    )
    assert result is None or result["category"] == "LOOP_DETECTED"


# ── helpers ───────────────────────────────────────────────────────────────────

def _detect(payload: dict) -> dict | None:
    return detect(payload, _NOW)


# ── labeled eval fixtures ─────────────────────────────────────────────────────

_FIXTURES: list[pytest.param] = [
    # ── TRUE POSITIVES ────────────────────────────────────────────────────────
    pytest.param(
        {
            "repeat_count": 6,
            "repeat_window_seconds": 60,
            "no_progress": True,
            "prompt_fingerprint": "fp-abc",
        },
        "LOOP_DETECTED", (0.65, 1.0),
        id="tp_prompt_repeat_with_no_progress",
    ),
    pytest.param(
        {
            "loop": {
                "repeat_count": 7,
                "window_seconds": 45,
                "no_progress": True,
                "prompt_fingerprint": "fp-loop-a",
            }
        },
        "LOOP_DETECTED", (0.65, 1.0),
        id="tp_loop_nested_dict_high_repeat",
    ),
    pytest.param(
        {
            "repeat_count": 5,
            "repeat_window_seconds": 90,
            "no_progress": True,
            "output_fingerprint": "out-fp-xyz",
            "loop": {
                "output_pattern": {
                    "repeat_count": 4,
                    "output_fingerprint": "out-fp-xyz",
                }
            },
        },
        "LOOP_DETECTED", (0.65, 1.0),
        id="tp_output_fingerprint_exact_repeat",
    ),
    pytest.param(
        {
            "repeat_count": 4,
            "loop": {
                "output_pattern": {
                    "near_repeated_output": True,
                    "output_similarity_score": 0.90,
                    "repeat_count": 4,
                }
            },
        },
        "LOOP_DETECTED", (0.65, 1.0),
        id="tp_output_similarity_repeat",
    ),
    pytest.param(
        {
            "tool_chain_repeat_cycles": 4,
            "tool_window_seconds": 120,
            "loop": {
                "tool_cycle": {"repeat_count": 4, "state_changed": False},
            },
        },
        "LOOP_DETECTED", (0.65, 1.0),
        id="tp_tool_cycle_no_state_change",
    ),
    pytest.param(
        {
            "retry_count": 4,
            "loop": {
                "retry_pattern": {
                    "retry_count": 4,
                    "dominant_retry_reason_count": 4,
                }
            },
        },
        "LOOP_DETECTED", (0.65, 1.0),
        id="tp_retry_pattern_dominant_reason",
    ),
    pytest.param(
        {
            "retry_count": 4,
            "max_steps_reached": True,
            "loop": {
                "retry_pattern": {"retry_count": 4},
            },
        },
        "LOOP_DETECTED", (0.65, 1.0),
        id="tp_retry_max_steps_reached",
    ),
    pytest.param(
        {
            "repeat_count": 8,
            "repeat_window_seconds": 30,
            "no_progress": True,
            "agent_name": "my_agent_v2",
            "prompt_fingerprint": "fp-multi",
        },
        "LOOP_DETECTED", (0.65, 1.0),
        id="tp_high_repeat_named_agent",
    ),
    pytest.param(
        {
            "loop": {
                "repeat_count": 10,
                "window_seconds": 20,
                "no_progress": True,
                "agent_name": "loop_prone_agent",
            }
        },
        "LOOP_DETECTED", (0.65, 1.0),
        id="tp_very_high_repeat_count",
    ),
    # ── FALSE POSITIVES ───────────────────────────────────────────────────────
    pytest.param(
        {
            "loop": {
                "loop_resolved": True,
                "repeat_count": 6,
                "no_progress": True,
            }
        },
        None, None,
        id="fp_loop_resolved_true",
    ),
    pytest.param(
        {"loop_resolved": True, "repeat_count": 10},
        None, None,
        id="fp_loop_resolved_flat",
    ),
    pytest.param(
        {},
        None, None,
        id="fp_empty_payload",
    ),
    pytest.param(
        {"repeat_count": 1, "no_progress": False},
        None, None,
        id="fp_single_repeat_no_no_progress",
    ),
    pytest.param(
        {"repeat_count": 0},
        None, None,
        id="fp_zero_repeat_count",
    ),
    pytest.param(
        {
            "repeat_count": 6,
            "repeat_window_seconds": 60,
            "no_progress": False,
        },
        None, None,
        id="fp_repeat_without_no_progress_flag",
    ),
    pytest.param(
        {
            "tool_chain_repeat_cycles": 4,
            "loop": {
                "tool_cycle": {"repeat_count": 4, "state_changed": True},
            },
        },
        None, None,
        id="fp_tool_cycle_with_state_change",
    ),
    pytest.param(
        {"status": "success"},
        None, None,
        id="fp_successful_call",
    ),
    pytest.param(
        {
            "retry_count": 2,
            "loop": {
                "retry_pattern": {"retry_count": 2, "dominant_retry_reason_count": 1},
            },
        },
        None, None,
        id="fp_low_retry_count",
    ),
    pytest.param(
        {
            "loop": {
                "output_pattern": {
                    "near_repeated_output": True,
                    "output_similarity_score": 0.50,
                    "repeat_count": 4,
                }
            },
        },
        None, None,
        id="fp_output_similarity_below_threshold",
    ),
]


@pytest.mark.parametrize("payload,expected_category,confidence_range", _FIXTURES)
def test_loop_detected_fixture(
    payload: dict,
    expected_category: str | None,
    confidence_range: tuple[float, float] | None,
) -> None:
    result = _detect(payload)

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
