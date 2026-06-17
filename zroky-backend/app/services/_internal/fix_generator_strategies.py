from __future__ import annotations

from typing import TYPE_CHECKING

from app.services._internal.fix_generator_helpers import (
    _as_float,
    _as_int,
    _as_text,
    _auth_failure_diff_from_snippet,
    _clean_snippet,
    _conceptual_diff,
    _cost_spike_diff_from_snippet,
    _loop_diff_from_snippet,
    _normalize_diagnosis_type,
    _rate_limit_diff_from_snippet,
    _token_budget,
    _token_overflow_diff_from_snippet,
)

if TYPE_CHECKING:
    from app.services.fix_generator import FixGenerationInput

def _token_overflow_fix(
    request: FixGenerationInput,
) -> tuple[str, str, str, str, list[dict[str, str]], list[str], list[str], list[str], float]:
    evidence = request.evidence
    estimated_tokens = _as_int(evidence.get("estimated_tokens") or evidence.get("estimated_prompt_tokens"))
    model_limit = _as_int(evidence.get("model_limit") or evidence.get("model_context_limit"))
    subtype = _as_text(evidence.get("subtype") or request.call_context.get("subtype"))
    snippet = _clean_snippet(request.code_snippet)
    token_budget = _token_budget(model_limit)

    if snippet:
        diff = _token_overflow_diff_from_snippet(
            snippet=snippet,
            subtype=subtype,
            token_budget=token_budget,
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
        {
            "option": "reduce_max_tokens",
            "tradeoff": "Less room for detailed model output, but no prompt content is removed.",
        },
        {
            "option": "switch_model",
            "tradeoff": "Larger context window, usually with higher cost or latency.",
        },
        {
            "option": "summarize_history",
            "tradeoff": "Preserves intent better than truncation, but may lose exact prior wording.",
        },
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


def _loop_detected_fix(
    request: FixGenerationInput,
) -> tuple[str, str, str, str, list[dict[str, str]], list[str], list[str], list[str], float]:
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
        {
            "option": "max_tool_cycles",
            "tradeoff": "Simple and deterministic, but may stop legitimate long tool workflows.",
        },
        {
            "option": "fingerprint_progress_guard",
            "tradeoff": "More precise loop detection, but requires storing recent signatures.",
        },
        {
            "option": "human_escalation",
            "tradeoff": "Keeps users safe, but adds operational review latency.",
        },
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


def _rate_limit_fix(
    request: FixGenerationInput,
) -> tuple[str, str, str, str, list[dict[str, str]], list[str], list[str], list[str], float]:
    evidence = request.evidence
    provider = _as_text(evidence.get("provider") or request.call_context.get("provider"))
    retry_after = _as_int(evidence.get("retry_after_seconds"))
    snippet = _clean_snippet(request.code_snippet)

    if snippet:
        diff = _rate_limit_diff_from_snippet(snippet, retry_after=retry_after)
        strategy_confidence = 0.88 if "AFTER" in diff else 0.70
    else:
        diff = _conceptual_diff(
            "No code snippet was provided. Apply at the provider client initialization or request site.",
            [
                "Add exponential backoff with jitter for 429 responses.",
                f"Respect retry-after headers if provider sends them (current: {retry_after}s)." if retry_after else "Respect retry-after headers if provider sends them.",
                "Consider circuit breaker for sustained rate limiting.",
            ],
        )
        strategy_confidence = 0.65

    explanation = (
        f"Provider {provider or 'unknown'} returned rate limit signals. "
        "The fix adds retry logic with exponential backoff to gracefully handle transient rate limits."
    )
    fix_rationale = "Exponential backoff with jitter prevents thundering herd while respecting provider limits."
    alternatives = [
        {
            "option": "increase_rate_limit_quota",
            "tradeoff": "Requires provider account upgrade; may increase costs but eliminates client-side complexity.",
        },
        {
            "option": "request_batching",
            "tradeoff": "Reduces request count but adds latency and complexity for real-time use cases.",
        },
        {
            "option": "circuit_breaker",
            "tradeoff": "Prevents hammering failing endpoints but requires careful tuning of thresholds.",
        },
    ]
    review_points = [
        "Ensure max retry count and total timeout align with SLA requirements.",
        "Verify jitter prevents synchronized retries across multiple instances.",
        "Check that retry-after header parsing handles edge cases (missing, malformed, too large).",
    ]
    verification_steps = [
        "Simulate 429 responses and verify backoff behavior.",
        "Confirm retry-after header is respected when present.",
        "Measure p99 latency under rate limit conditions.",
    ]
    rollback_instructions = [
        "Remove or disable the retry wrapper.",
        "Restore original synchronous request behavior.",
        "Verify rate limit errors surface immediately again.",
    ]

    return (
        "Fix RATE_LIMIT with exponential backoff and retry logic",
        diff,
        explanation,
        fix_rationale,
        alternatives,
        review_points,
        verification_steps,
        rollback_instructions,
        strategy_confidence,
    )


def _auth_failure_fix(
    request: FixGenerationInput,
) -> tuple[str, str, str, str, list[dict[str, str]], list[str], list[str], list[str], float]:
    evidence = request.evidence
    provider = _as_text(evidence.get("provider") or request.call_context.get("provider"))
    status_code = _as_int(evidence.get("status_code"))
    snippet = _clean_snippet(request.code_snippet)

    if snippet:
        diff = _auth_failure_diff_from_snippet(snippet, status_code=status_code)
        strategy_confidence = 0.90 if "AFTER" in diff else 0.72
    else:
        diff = _conceptual_diff(
            "No code snippet was provided. Review credential management and authentication flow.",
            [
                "Verify API keys/secrets are correctly configured and not expired.",
                "Check for missing or malformed authorization headers.",
                "Implement credential rotation mechanism.",
            ],
        )
        strategy_confidence = 0.60

    auth_type = "token" if status_code == 401 else "permission" if status_code == 403 else "credential"
    explanation = (
        f"Authentication failed for provider {provider or 'unknown'} ({status_code or 'unknown'}). "
        f"The fix addresses {auth_type} issues to restore API access."
    )
    fix_rationale = "Proper credential management and error handling prevents auth failures and enables graceful degradation."
    alternatives = [
        {
            "option": "credential_rotation",
            "tradeoff": "More secure but requires infrastructure to distribute new keys.",
        },
        {
            "option": "fallback_provider",
            "tradeoff": "Maintains availability but increases complexity and cost.",
        },
        {
            "option": "graceful_degradation",
            "tradeoff": "Keeps app functional but with reduced capabilities.",
        },
    ]
    review_points = [
        "Verify credentials are not logged or exposed in error messages.",
        "Check that credential rotation does not cause downtime.",
        "Ensure auth errors are surfaced to operators, not silently swallowed.",
    ]
    verification_steps = [
        "Confirm API calls succeed with valid credentials.",
        "Verify graceful handling when credentials are invalid.",
        "Test credential rotation without service restart.",
    ]
    rollback_instructions = [
        "Revert credential changes.",
        "Restore previous authentication configuration.",
        "Verify auth failures return with previous behavior.",
    ]

    return (
        "Fix AUTH_FAILURE with proper credential handling",
        diff,
        explanation,
        fix_rationale,
        alternatives,
        review_points,
        verification_steps,
        rollback_instructions,
        strategy_confidence,
    )


def _cost_spike_fix(
    request: FixGenerationInput,
) -> tuple[str, str, str, str, list[dict[str, str]], list[str], list[str], list[str], float]:
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
        {
            "option": "model_downgrade",
            "tradeoff": "Lower cost but potentially reduced response quality.",
        },
        {
            "option": "request_caching",
            "tradeoff": "Reduces duplicate costs but adds cache complexity.",
        },
        {
            "option": "usage_quotas",
            "tradeoff": "Hard spending caps but may reject legitimate requests.",
        },
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


def _generic_fix(
    request: FixGenerationInput,
) -> tuple[str, str, str, str, list[dict[str, str]], list[str], list[str], list[str], float]:
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
        [
            {
                "option": "manual_review",
                "tradeoff": "Safest path when evidence is incomplete, but slower to resolve.",
            }
        ],
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
