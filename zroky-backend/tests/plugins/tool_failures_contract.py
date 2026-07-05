from __future__ import annotations

from app.services.detectors.tool_failures import (
    detect_tool_argument_mismatch,
    detect_tool_call_failure,
    detect_tool_selection_failure,
)


def test_tool_failures_contract_callables() -> None:
    assert callable(detect_tool_argument_mismatch)
    assert callable(detect_tool_call_failure)
    assert callable(detect_tool_selection_failure)
