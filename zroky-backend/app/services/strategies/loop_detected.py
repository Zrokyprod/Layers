"""LOOP_DETECTED template fix strategy."""
from __future__ import annotations

from typing import Any

from app.services._fix_utils import _as_int, _clean_snippet
from app.services.strategies._diff import (
    _before_after_diff,
    _conceptual_diff,
    _first_relevant_line,
)
from app.services.strategies.ai_fix import FixTuple


def generate(request: Any) -> FixTuple:
    return _loop_detected_fix(request)


def _loop_detected_fix(request: Any) -> FixTuple:
    evidence = request.evidence
    repeat_count = _as_int(evidence.get("repeat_count"))
    window_seconds = _as_int(evidence.get("repeat_window_seconds"))
    snippet = _clean_snippet(request.code_snippet)

    if snippet:
        diff = _loop_diff_from_snippet(snippet)
        strategy_confidence = 0.84 if "AFTER" in diff else 0.66
    else:
        diff = _conceptual_diff(
            "No code snippet was provided. Apply at the agent/tool dispatch loop.",
            [
                "Add a bounded step limit.",
                "Break when the same prompt fingerprint repeats without progress.",
                "Emit a visible failure state instead of silently continuing.",
            ],
        )
        strategy_confidence = 0.62

    observed = (
        f" The diagnosis observed {repeat_count} repeats in {window_seconds}s."
        if repeat_count and window_seconds
        else ""
    )
    explanation = (
        "The agent appears to repeat work without progress."
        f"{observed} The fix adds an explicit loop guard so repeated no-progress dispatch stops predictably "
        "and remains reviewable by a human operator."
    )
    fix_rationale = "A bounded no-progress guard stops repeated dispatch before it becomes a production loop."
    alternatives = [
        {"option": "max_tool_cycles", "tradeoff": "Simple and deterministic, but may stop legitimate long tool workflows."},
        {"option": "fingerprint_progress_guard", "tradeoff": "More precise loop detection, but requires storing recent signatures."},
        {"option": "human_escalation", "tradeoff": "Keeps users safe, but adds operational review latency."},
    ]
    review_points = [
        "Confirm the step limit does not stop legitimate long-running workflows.",
        "Verify repeated failures surface a clear user-visible or operator-visible state.",
        "Run a loop reproduction and a known-good multi-step task before merging.",
    ]
    verification_steps = [
        "Run the loop reproduction that triggered LOOP_DETECTED.",
        "Confirm the loop exits through the new guard instead of repeating indefinitely.",
        "Run a valid multi-step agent workflow to confirm it still completes.",
    ]
    rollback_instructions = [
        "Revert the applied loop-guard diff.",
        "Restore the original dispatch loop behavior.",
        "Re-enable monitoring for LOOP_DETECTED recurrence before retrying another fix.",
    ]
    return (
        "Fix LOOP_DETECTED with a bounded no-progress guard",
        diff,
        explanation,
        fix_rationale,
        alternatives,
        review_points,
        verification_steps,
        rollback_instructions,
        strategy_confidence,
    )


def _loop_diff_from_snippet(snippet: str) -> str:
    line = _first_relevant_line(snippet, ("while True", "for "))
    if not line:
        return _conceptual_diff(
            "Snippet did not expose the loop dispatch.",
            ["Add a bounded loop counter and break on repeated no-progress signatures."],
        )
    stripped = line.strip()
    indent = line[: len(line) - len(line.lstrip())]
    if stripped.startswith("while True"):
        after = f"{indent}for _zroky_step in range(<configured_max_agent_steps>):"
    else:
        after = (
            f"{line}\n"
            f"{indent}    if <existing_no_progress_guard>(prompt_fingerprint):\n"
            f"{indent}        break"
        )
    return _before_after_diff(before=line, after=after)
