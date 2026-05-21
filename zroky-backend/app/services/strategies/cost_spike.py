"""COST_SPIKE template fix strategy."""
from __future__ import annotations

from typing import Any

from app.services._fix_utils import _as_float, _clean_snippet
from app.services.strategies._diff import (
    _before_after_diff,
    _conceptual_diff,
    _first_relevant_line,
)
from app.services.strategies.ai_fix import FixTuple


def generate(request: Any) -> FixTuple:
    return _cost_spike_fix(request)


def _cost_spike_fix(request: Any) -> FixTuple:
    evidence = request.evidence
    current_spend = _as_float(evidence.get("current_spend"))
    baseline = _as_float(evidence.get("baseline_spend"))
    snippet = _clean_snippet(request.code_snippet)

    if snippet:
        diff = _cost_spike_diff_from_snippet(snippet)
        strategy_confidence = 0.85 if "AFTER" in diff else 0.68
    else:
        diff = _conceptual_diff(
            "No code snippet was provided. Apply cost controls at the provider call site.",
            [
                "Add cost-per-request tracking and alerting thresholds.",
                "Implement request caching for repeated similar queries.",
                "Consider model downgrading for non-critical requests.",
            ],
        )
        strategy_confidence = 0.62

    increase_pct = ((current_spend - baseline) / baseline * 100) if baseline > 0 else 0
    explanation = (
        f"Cost spike detected: ${current_spend:.2f} vs baseline ${baseline:.2f} "
        f"({increase_pct:.0f}% increase). "
        "The fix adds cost controls and optimization strategies."
    )
    fix_rationale = "Proactive cost controls prevent runaway spending while maintaining service quality."
    alternatives = [
        {"option": "model_downgrade", "tradeoff": "Lower cost but potentially reduced response quality."},
        {"option": "request_caching", "tradeoff": "Reduces duplicate costs but adds cache complexity."},
        {"option": "usage_quotas", "tradeoff": "Hard spending caps but may reject legitimate requests."},
    ]
    review_points = [
        "Ensure cost alerts trigger before hard limits are hit.",
        "Verify caching does not return stale results for time-sensitive queries.",
        "Check that model downgrades maintain acceptable quality.",
    ]
    verification_steps = [
        "Monitor cost per request after deployment.",
        "Verify alerts fire at configured thresholds.",
        "Measure cache hit rates and cost reduction.",
    ]
    rollback_instructions = [
        "Remove cost controls.",
        "Restore original model selection logic.",
        "Verify spending returns to previous patterns.",
    ]
    return (
        "Fix COST_SPIKE with cost controls and optimizations",
        diff,
        explanation,
        fix_rationale,
        alternatives,
        review_points,
        verification_steps,
        rollback_instructions,
        strategy_confidence,
    )


def _cost_spike_diff_from_snippet(snippet: str) -> str:
    line = _first_relevant_line(snippet, ("model", "gpt", "claude", "completion", "request"))
    if line and "=" in line:
        return _before_after_diff(
            before=line,
            after="# Add cost tracking and model selection based on cost\nresponse = <existing_cost_aware_client>.request_with_budget(",
        )
    return _before_after_diff(
        before="# Original model request",
        after=(
            "# Add cost tracking and budget controls\n"
            "if <existing_cost_tracker>.estimate_cost(request) > budget_limit:\n"
            "    request = <existing_cost_optimizer>.downgrade_if_possible(request)\n"
            "response = client.request(request)"
        ),
    )
