"""Generic/fallback fix strategy for unrecognised diagnosis types."""
from __future__ import annotations

from typing import Any

from app.services._fix_utils import _normalize_diagnosis_type
from app.services.strategies._diff import _conceptual_diff
from app.services.strategies.ai_fix import FixTuple


def generate(request: Any) -> FixTuple:
    return _generic_fix(request)


def _generic_fix(request: Any) -> FixTuple:
    diagnosis_type = _normalize_diagnosis_type(request.diagnosis_type)
    diff = _conceptual_diff(
        "No deterministic code strategy is registered for this diagnosis.",
        [
            "Inspect the evidence and affected call site.",
            "Apply the smallest behavior-preserving remediation.",
            "Add a regression test around the diagnosed failure mode.",
        ],
    )
    explanation = (
        f"{diagnosis_type} does not yet have a deterministic fix strategy. "
        "Return options for human review rather than inventing a patch."
    )
    fix_rationale = "No safe deterministic code edit can be selected from the available diagnosis evidence."
    return (
        f"Review {diagnosis_type} diagnosis",
        diff,
        explanation,
        fix_rationale,
        [{"option": "manual_review", "tradeoff": "Safest path when evidence is incomplete, but slower to resolve."}],
        [
            "Confirm the affected file and call path before editing.",
            "Do not apply a patch unless the diagnosis evidence maps to the code location.",
        ],
        [
            "Reproduce the diagnosed behavior before making changes.",
            "Apply the smallest manually reviewed change.",
            "Re-run the reproduction and related regression tests.",
        ],
        [
            "Revert the manually applied change.",
            "Restore the original code path and re-run the reproduction.",
        ],
        0.45,
    )
