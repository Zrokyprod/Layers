"""TOKEN_OVERFLOW template fix strategy."""
from __future__ import annotations

from typing import Any

from app.services._fix_utils import _as_int, _as_text, _clean_snippet
from app.services.strategies._diff import (
    _before_after_diff,
    _conceptual_diff,
    _first_relevant_line,
    _replace_assignment_rhs,
    _assignment_rhs,
    _token_budget,
)
from app.services.strategies.ai_fix import FixTuple


def generate(request: Any) -> FixTuple:
    return _token_overflow_fix(request)


def _token_overflow_fix(request: Any) -> FixTuple:
    evidence = request.evidence
    estimated_tokens = _as_int(evidence.get("estimated_tokens") or evidence.get("estimated_prompt_tokens"))
    model_limit = _as_int(evidence.get("model_limit") or evidence.get("model_context_limit"))
    subtype = _as_text(evidence.get("subtype") or request.call_context.get("subtype"))
    snippet = _clean_snippet(request.code_snippet)
    token_budget = _token_budget(model_limit)

    if snippet:
        diff = _token_overflow_diff_from_snippet(
            snippet=snippet, subtype=subtype, token_budget=token_budget,
        )
        strategy_confidence = 0.92 if "AFTER" in diff else 0.72
    else:
        diff = _conceptual_diff(
            "No code snippet was provided. Apply at the provider call site that builds messages.",
            [
                f"Bound prompt/history before provider call to about {token_budget} tokens.",
                "Prefer an existing truncation or summarization helper from the codebase.",
            ],
        )
        strategy_confidence = 0.68

    root = (
        f"Prompt size was estimated at {estimated_tokens} tokens against a {model_limit} token limit."
        if estimated_tokens and model_limit
        else "The provider reported or implied a context/token overflow."
    )
    explanation = (
        f"{root} The fix keeps the provider request under a bounded prompt budget before the call. "
        "This is advisory only: review the call site and use existing tokenizer/summarizer helpers so behavior is explicit."
    )
    fix_rationale = "Bounding prompt input prevents the provider request from exceeding the model context window."
    alternatives = [
        {"option": "reduce_max_tokens", "tradeoff": "Less room for detailed model output, but no prompt content is removed."},
        {"option": "switch_model", "tradeoff": "Larger context window, usually with higher cost or latency."},
        {"option": "summarize_history", "tradeoff": "Preserves intent better than truncation, but may lose exact prior wording."},
    ]
    review_points = [
        "Ensure prompt truncation or summarization preserves required user intent and safety context.",
        "Verify reserved output/max_tokens still meets response requirements.",
        "Run the failing high-token scenario and confirm the provider no longer returns a context error.",
    ]
    verification_steps = [
        "Run the same request that previously failed with TOKEN_OVERFLOW.",
        "Confirm no TOKEN_OVERFLOW or context-length error occurs.",
        "Check response quality is acceptable after prompt bounding.",
    ]
    rollback_instructions = [
        "Revert the applied diff.",
        "Restore the original message construction or max_tokens logic.",
        "Re-run the previously failing request to confirm rollback behavior is understood.",
    ]
    return (
        "Fix TOKEN_OVERFLOW by bounding prompt size",
        diff,
        explanation,
        fix_rationale,
        alternatives,
        review_points,
        verification_steps,
        rollback_instructions,
        strategy_confidence,
    )


def _token_overflow_diff_from_snippet(*, snippet: str, subtype: str, token_budget: int) -> str:
    line = _first_relevant_line(snippet, ("messages", "history", "max_tokens"))
    if not line:
        return _conceptual_diff(
            "Snippet did not expose message construction.",
            [f"Bound message/history tokens to about {token_budget} before provider call."],
        )
    if "max_tokens" in line and "=" in line:
        after = _replace_assignment_rhs(
            line, f"min({_assignment_rhs(line)}, {max(256, token_budget // 4)})",
        )
    elif "history" in line.lower() or subtype == "conversation_accumulation":
        after = _replace_assignment_rhs(
            line,
            f"<existing_history_summary_helper>({_assignment_rhs(line)}, token_budget={token_budget})",
        )
    else:
        after = _replace_assignment_rhs(
            line,
            f"<existing_prompt_budget_helper>({_assignment_rhs(line)}, token_budget={token_budget})",
        )
    return _before_after_diff(before=line, after=after)
