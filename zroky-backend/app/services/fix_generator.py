from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from app.services.privacy import mask_text, mask_value

logger = logging.getLogger(__name__)

_BRANCH_SANITIZE_RE = re.compile(r"[^a-z0-9._/-]+")


@dataclass(frozen=True)
class FixGenerationInput:
    diagnosis_type: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    diagnosis_confidence: float = 0.0
    call_context: Mapping[str, Any] = field(default_factory=dict)
    code_snippet: str | None = None
    diagnosis_id: str | None = None
    target_file: str | None = None
    file_hint: str | None = None


@dataclass(frozen=True)
class PullRequestDraftPayload:
    branch_name: str
    commit_message: str
    pr_title: str
    pr_description: str
    base_branch: str = "main"


@dataclass(frozen=True)
class FixSuggestion:
    fix_id: str
    title: str
    target_file: str
    file_hint: str
    anchor: str
    diff: str
    patch_unified: str
    explanation: str
    fix_rationale: str
    confidence: float
    confidence_level: str
    risk_level: str
    fix_scope: str
    blast_radius: str
    time_to_apply_estimate: str
    requires_tests_update: bool
    affected_paths: list[str]
    fix_conflicts_with: list[str]
    rollout_strategy: str
    observability_checks: list[str]
    reversibility: str
    fix_category: str
    recommended_priority: str
    fix_tags: list[str]
    expected_impact: dict[str, Any]
    review_points: list[str]
    apply_instructions: list[str]
    verification_steps: list[str]
    rollback_instructions: list[str]
    alternatives: list[dict[str, str]]
    pr: PullRequestDraftPayload
    advisory_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pr"] = asdict(self.pr)
        return payload


# ─── AI-powered fix generation ───────────────────────────────────────────────

_AI_FIX_JSON_SCHEMA = """\
Return ONLY a single JSON object with these exact keys (no markdown, no extra keys):
{
  "title": "Short action-oriented fix title (max 80 chars)",
  "diff": "Code change in --- BEFORE --- / --- AFTER --- format (see below)",
  "explanation": "1-3 sentence plain-English explanation of the fix",
  "fix_rationale": "Why this specific change prevents the diagnosed failure from recurring",
  "alternatives": [{"option": "name", "tradeoff": "one-sentence tradeoff description"}],
  "review_points": ["thing a reviewer must verify before merging"],
  "verification_steps": ["ordered step to confirm the fix works in production"],
  "rollback_instructions": ["ordered step to revert safely if the fix causes regressions"],
  "strategy_confidence": 0.85
}

Diff MUST use exactly this format (required for downstream patch generation):

--- BEFORE ---
<original code, verbatim if snippet was provided>

--- AFTER ---
<minimal change that directly addresses the diagnosed failure>

Hard rules:
- advisory_only: this diff is a DRAFT — never claim it is ready to deploy without human review
- Never include real secrets, API keys, tokens, or passwords
- Only change lines directly tied to the diagnosed failure
- strategy_confidence is a float 0.0–1.0 reflecting how specific and actionable the diff is
  (0.9+ only if real code snippet was provided and the diff is precise)
- All list fields must have at least one element
"""

_AI_FIX_SYSTEM_PROMPT = (
    "You are the Zroky AI fix engine. Zroky is a production observability platform for AI agents.\n"
    "Your job: given a structured diagnosis of a production AI failure, generate the smallest possible "
    "actionable code fix that directly addresses the root cause.\n\n"
    + _AI_FIX_JSON_SCHEMA
)

_AI_FIX_TUPLE = tuple[
    str, str, str, str,
    list[dict[str, str]], list[str], list[str], list[str],
    float,
]


def _ai_fix(request: FixGenerationInput, db: Any | None = None) -> _AI_FIX_TUPLE | None:
    """Try LLM-powered fix generation.

    Returns a 9-tuple identical in shape to the template _*_fix() functions,
    or None on any error (caller falls back to the appropriate template).
    """
    try:
        from app.services.llm_client import get_llm_client  # local import avoids circular at module load
        client = get_llm_client()
    except Exception as exc:
        logger.debug("LLM client unavailable for fix generation: %s", exc)
        return None

    evidence_safe = mask_value(dict(request.evidence))
    call_ctx_safe = mask_value(dict(request.call_context))
    snippet = _clean_snippet(request.code_snippet)

    user_payload: dict[str, Any] = {
        "diagnosis_type": request.diagnosis_type,
        "diagnosis_confidence": request.diagnosis_confidence,
        "evidence": evidence_safe,
        "call_context": call_ctx_safe,
    }
    if snippet:
        user_payload["code_snippet"] = snippet
    if request.target_file:
        user_payload["target_file"] = request.target_file

    user_content = (
        "Generate a fix for this production AI agent diagnosis:\n\n"
        + json.dumps(user_payload, indent=2, default=str)
    )

    try:
        import time as _time
        from app.services.llm_observability import record_platform_llm_call
        start = _time.perf_counter()
        response = client.chat_completions_create(
            messages=[
                {"role": "system", "content": _AI_FIX_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2000,
        )
        latency_ms = (_time.perf_counter() - start) * 1000.0
        if db is not None:
            record_platform_llm_call(
                db,
                purpose="fix_generation",
                response=response,
                latency_ms=latency_ms,
                tenant_id=request.call_context.get("project_id") if isinstance(request.call_context, dict) else None,
                diagnosis_id=request.diagnosis_id,
                request_messages=[
                    {"role": "system", "content": _AI_FIX_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
        raw = response.choices[0].message.content
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("AI fix generation failed (%s); falling back to template", type(exc).__name__)
        return None

    required_keys = ("title", "diff", "explanation", "fix_rationale", "strategy_confidence")
    if not all(k in data for k in required_keys):
        logger.warning("AI fix response missing required fields %s; falling back to template", required_keys)
        return None

    try:
        confidence = float(data["strategy_confidence"])
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.70

    def _safe_list(val: Any, default: list[str]) -> list[str]:
        return [str(x) for x in val] if isinstance(val, list) and val else default

    def _safe_dict_list(val: Any) -> list[dict[str, str]]:
        if not isinstance(val, list):
            return []
        result: list[dict[str, str]] = []
        for item in val:
            if isinstance(item, dict) and "option" in item:
                result.append({"option": str(item["option"]), "tradeoff": str(item.get("tradeoff", ""))})
        return result

    return (
        str(data["title"])[:200],
        str(data["diff"]),
        str(data["explanation"]),
        str(data["fix_rationale"]),
        _safe_dict_list(data.get("alternatives", [])),
        _safe_list(data.get("review_points"), ["Review the proposed change carefully before applying."]),
        _safe_list(data.get("verification_steps"), ["Reproduce the diagnosed failure and confirm it no longer occurs after applying the fix."]),
        _safe_list(data.get("rollback_instructions"), ["Revert the applied change and re-run the reproduction to verify original behavior."]),
        confidence,
    )


def generate_fix_suggestion(
    request: FixGenerationInput,
    *,
    base_branch: str = "main",
    db: Any | None = None,
) -> FixSuggestion:
    diagnosis_type = _normalize_diagnosis_type(request.diagnosis_type)
    fix_id = _fix_id(
        diagnosis_type=diagnosis_type,
        diagnosis_id=request.diagnosis_id,
    )

    # ── Try AI-powered generation first; template is the fallback ────────────
    ai_result = _ai_fix(request, db=db)
    if ai_result is not None:
        logger.info(
            "AI fix generated for diagnosis_type=%s diagnosis_id=%s confidence=%.2f",
            diagnosis_type,
            request.diagnosis_id,
            ai_result[8],
        )
        (
            title,
            diff,
            explanation,
            fix_rationale,
            alternatives,
            review_points,
            verification_steps,
            rollback_instructions,
            strategy_confidence,
        ) = ai_result
    elif diagnosis_type == "TOKEN_OVERFLOW":
        (
            title,
            diff,
            explanation,
            fix_rationale,
            alternatives,
            review_points,
            verification_steps,
            rollback_instructions,
            strategy_confidence,
        ) = _token_overflow_fix(request)
    elif diagnosis_type == "LOOP_DETECTED":
        (
            title,
            diff,
            explanation,
            fix_rationale,
            alternatives,
            review_points,
            verification_steps,
            rollback_instructions,
            strategy_confidence,
        ) = _loop_detected_fix(request)
    elif diagnosis_type == "RATE_LIMIT":
        (
            title,
            diff,
            explanation,
            fix_rationale,
            alternatives,
            review_points,
            verification_steps,
            rollback_instructions,
            strategy_confidence,
        ) = _rate_limit_fix(request)
    elif diagnosis_type == "AUTH_FAILURE":
        (
            title,
            diff,
            explanation,
            fix_rationale,
            alternatives,
            review_points,
            verification_steps,
            rollback_instructions,
            strategy_confidence,
        ) = _auth_failure_fix(request)
    elif diagnosis_type == "COST_SPIKE":
        (
            title,
            diff,
            explanation,
            fix_rationale,
            alternatives,
            review_points,
            verification_steps,
            rollback_instructions,
            strategy_confidence,
        ) = _cost_spike_fix(request)
    else:
        (
            title,
            diff,
            explanation,
            fix_rationale,
            alternatives,
            review_points,
            verification_steps,
            rollback_instructions,
            strategy_confidence,
        ) = _generic_fix(request)

    confidence = _derive_fix_confidence(
        diagnosis_confidence=request.diagnosis_confidence,
        strategy_confidence=strategy_confidence,
        has_code_snippet=bool(_clean_snippet(request.code_snippet)),
    )
    target_file = _target_file(request)
    file_hint = _file_hint(request, diagnosis_type)
    anchor = _anchor_from_diff(diff) or _fallback_anchor(diagnosis_type)
    patch_unified = _build_unified_patch(
        target_file=target_file,
        diff=diff,
    )
    confidence_level = _confidence_level(confidence)
    risk_level = _risk_level(diagnosis_type, confidence_level)
    fix_scope = _fix_scope(diagnosis_type)
    blast_radius = _blast_radius(fix_scope=fix_scope, target_file=target_file)
    time_to_apply_estimate = _time_to_apply_estimate(
        diagnosis_type=diagnosis_type,
        target_file=target_file,
        patch_unified=patch_unified,
    )
    requires_tests_update = _requires_tests_update(diagnosis_type)
    affected_paths = _affected_paths(request=request, target_file=target_file)
    fix_conflicts_with = _fix_conflicts_with(request)
    rollout_strategy = _rollout_strategy(diagnosis_type)
    observability_checks = _observability_checks(diagnosis_type)
    reversibility = _reversibility(
        patch_unified=patch_unified,
        target_file=target_file,
        diagnosis_type=diagnosis_type,
    )
    fix_category = _fix_category(diagnosis_type)
    recommended_priority = _recommended_priority(
        diagnosis_type=diagnosis_type,
        confidence_level=confidence_level,
    )
    fix_tags = _fix_tags(diagnosis_type)
    expected_impact = _expected_impact(
        diagnosis_type=diagnosis_type,
        confidence_level=confidence_level,
    )
    apply_instructions = _apply_instructions(
        target_file=target_file,
        anchor=anchor,
        patch_unified=patch_unified,
    )
    pr = build_pr_draft_payload(
        fix_id=fix_id,
        diagnosis_id=request.diagnosis_id,
        diagnosis_type=diagnosis_type,
        title=title,
        target_file=target_file,
        file_hint=file_hint,
        anchor=anchor,
        explanation=explanation,
        fix_rationale=fix_rationale,
        evidence=mask_value(dict(request.evidence)),
        diff=diff,
        patch_unified=patch_unified,
        confidence=confidence,
        confidence_level=confidence_level,
        risk_level=risk_level,
        fix_scope=fix_scope,
        blast_radius=blast_radius,
        time_to_apply_estimate=time_to_apply_estimate,
        requires_tests_update=requires_tests_update,
        affected_paths=affected_paths,
        fix_conflicts_with=fix_conflicts_with,
        rollout_strategy=rollout_strategy,
        observability_checks=observability_checks,
        reversibility=reversibility,
        fix_category=fix_category,
        recommended_priority=recommended_priority,
        fix_tags=fix_tags,
        expected_impact=expected_impact,
        alternatives=alternatives,
        review_points=review_points,
        apply_instructions=apply_instructions,
        verification_steps=verification_steps,
        rollback_instructions=rollback_instructions,
        base_branch=base_branch,
    )

    return FixSuggestion(
        fix_id=fix_id,
        title=title,
        target_file=target_file,
        file_hint=file_hint,
        anchor=anchor,
        diff=diff,
        patch_unified=patch_unified,
        explanation=explanation,
        fix_rationale=fix_rationale,
        confidence=confidence,
        confidence_level=confidence_level,
        risk_level=risk_level,
        fix_scope=fix_scope,
        blast_radius=blast_radius,
        time_to_apply_estimate=time_to_apply_estimate,
        requires_tests_update=requires_tests_update,
        affected_paths=affected_paths,
        fix_conflicts_with=fix_conflicts_with,
        rollout_strategy=rollout_strategy,
        observability_checks=observability_checks,
        reversibility=reversibility,
        fix_category=fix_category,
        recommended_priority=recommended_priority,
        fix_tags=fix_tags,
        expected_impact=expected_impact,
        review_points=review_points,
        apply_instructions=apply_instructions,
        verification_steps=verification_steps,
        rollback_instructions=rollback_instructions,
        alternatives=alternatives,
        pr=pr,
    )


def build_pr_draft_payload(
    *,
    fix_id: str,
    diagnosis_id: str | None,
    diagnosis_type: str,
    title: str,
    target_file: str,
    file_hint: str,
    anchor: str,
    explanation: str,
    fix_rationale: str,
    evidence: Mapping[str, Any],
    diff: str,
    patch_unified: str,
    confidence: float,
    confidence_level: str,
    risk_level: str,
    fix_scope: str,
    blast_radius: str,
    time_to_apply_estimate: str,
    requires_tests_update: bool,
    affected_paths: list[str],
    fix_conflicts_with: list[str],
    rollout_strategy: str,
    observability_checks: list[str],
    reversibility: str,
    fix_category: str,
    recommended_priority: str,
    fix_tags: list[str],
    expected_impact: dict[str, Any],
    alternatives: list[dict[str, str]],
    review_points: list[str],
    apply_instructions: list[str],
    verification_steps: list[str],
    rollback_instructions: list[str],
    base_branch: str = "main",
) -> PullRequestDraftPayload:
    normalized_type = _normalize_diagnosis_type(diagnosis_type)
    safe_id = _slug(diagnosis_id or "diagnosis", fallback="diagnosis")
    branch_name = f"zroky/fix-{normalized_type.lower()}-{safe_id}"
    pr_title = f"[ZROKY] {title}"

    evidence_lines = _evidence_summary_lines(evidence)
    pr_description = "\n".join(
        [
            "## ZROKY Diagnosis",
            f"- Fix ID: `{fix_id}`",
            f"- Diagnosis: `{normalized_type}`",
            f"- Diagnosis ID: `{diagnosis_id or 'unknown'}`",
            f"- Fix confidence: `{confidence:.2f}` (`{confidence_level}`)",
            f"- Risk level: `{risk_level}`",
            f"- Fix scope: `{fix_scope}`",
            f"- Blast radius: `{blast_radius}`",
            f"- Time to apply estimate: `{time_to_apply_estimate}`",
            f"- Requires tests update: `{str(requires_tests_update).lower()}`",
            f"- Rollout strategy: `{rollout_strategy}`",
            f"- Reversibility: `{reversibility}`",
            f"- Fix category: `{fix_category}`",
            f"- Recommended priority: `{recommended_priority}`",
            f"- Fix tags: {', '.join(f'`{tag}`' for tag in fix_tags) or '`none`'}",
            f"- Target file: `{target_file}`",
            f"- Anchor: `{anchor}`",
            f"- File hint: {file_hint}",
            f"- Affected paths: {', '.join(f'`{path}`' for path in affected_paths) or '`unknown`'}",
            f"- Potential conflicts: {', '.join(f'`{item}`' for item in fix_conflicts_with) or '`none declared`'}",
            "",
            "## Evidence",
            *(evidence_lines or ["- No structured evidence supplied."]),
            "",
            "## Why This Change",
            fix_rationale,
            "",
            "## Proposed Change",
            explanation,
            "",
            "## Apply Instructions",
            *[f"{index}. {item}" for index, item in enumerate(apply_instructions, start=1)],
            "",
            "## Expected Impact",
            *[
                f"- Prevents: {', '.join(expected_impact.get('prevents', [])) or 'n/a'}",
                f"- Improves: {', '.join(expected_impact.get('improves', [])) or 'n/a'}",
                f"- Impact confidence: `{expected_impact.get('confidence', 'unknown')}`",
            ],
            "",
            "## Verification Steps",
            *[f"{index}. {item}" for index, item in enumerate(verification_steps, start=1)],
            "",
            "## Observability Checks",
            *(f"- {item}" for item in observability_checks),
            "",
            "## Minimal Diff Draft",
            "```diff",
            diff.strip(),
            "```",
            "",
            "## Unified Patch Draft",
            "```diff",
            patch_unified.strip() or "# No patch generated because target file or anchor is unknown.",
            "```",
            "",
            "## Required Review Points",
            *(f"- {item}" for item in review_points),
            "",
            "## Alternatives",
            *(
                f"- `{item.get('option', 'unknown')}`: {item.get('tradeoff', 'No tradeoff supplied.')}"
                for item in alternatives
            ),
            "",
            "## Rollback",
            *[f"{index}. {item}" for index, item in enumerate(rollback_instructions, start=1)],
            "",
            "## Safety Notes",
            "- Advisory draft only; no code has been pushed or applied.",
            "- Confirm the affected call site before applying.",
            "- Keep the final patch scoped to the diagnosed failure.",
        ]
    )

    return PullRequestDraftPayload(
        branch_name=branch_name,
        commit_message=f"fix(zroky): address {normalized_type.lower()} diagnosis {diagnosis_id or safe_id}",
        pr_title=pr_title,
        pr_description=pr_description,
        base_branch=base_branch or "main",
    )


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


def _token_overflow_diff_from_snippet(*, snippet: str, subtype: str, token_budget: int) -> str:
    line = _first_relevant_line(snippet, ("messages", "history", "max_tokens"))
    if not line:
        return _conceptual_diff(
            "Snippet did not expose message construction.",
            [
                f"Bound message/history tokens to about {token_budget} before provider call.",
            ],
        )

    if "max_tokens" in line and "=" in line:
        after = _replace_assignment_rhs(
            line,
            f"min({_assignment_rhs(line)}, {max(256, token_budget // 4)})",
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


def _loop_diff_from_snippet(snippet: str) -> str:
    line = _first_relevant_line(snippet, ("while True", "for "))
    if not line:
        return _conceptual_diff(
            "Snippet did not expose the loop dispatch.",
            [
                "Add a bounded loop counter and break on repeated no-progress signatures.",
            ],
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


def _derive_fix_confidence(
    *,
    diagnosis_confidence: float,
    strategy_confidence: float,
    has_code_snippet: bool,
) -> float:
    diagnosis = _clamp(diagnosis_confidence or 0.5, 0.0, 1.0)
    snippet_factor = 1.0 if has_code_snippet else 0.82
    return round(_clamp(diagnosis * strategy_confidence * snippet_factor, 0.25, 0.95), 2)


def _confidence_level(confidence: float) -> str:
    if confidence >= 0.80:
        return "high"
    if confidence >= 0.55:
        return "medium"
    return "low"


def _risk_level(diagnosis_type: str, confidence_level: str) -> str:
    if confidence_level == "low":
        return "high"
    if diagnosis_type == "LOOP_DETECTED":
        return "medium"
    if diagnosis_type == "TOKEN_OVERFLOW":
        return "low" if confidence_level == "high" else "medium"
    if diagnosis_type == "RATE_LIMIT":
        return "low" if confidence_level == "high" else "medium"
    if diagnosis_type == "AUTH_FAILURE":
        return "medium"
    if diagnosis_type == "COST_SPIKE":
        return "low"
    return "medium"


def _fix_scope(diagnosis_type: str) -> str:
    if diagnosis_type == "TOKEN_OVERFLOW":
        return "local"
    if diagnosis_type == "RATE_LIMIT":
        return "local"
    if diagnosis_type == "AUTH_FAILURE":
        return "module"
    if diagnosis_type == "COST_SPIKE":
        return "system"
    if diagnosis_type == "LOOP_DETECTED":
        return "module"
    return "local"


def _expected_impact(*, diagnosis_type: str, confidence_level: str) -> dict[str, Any]:
    if diagnosis_type == "TOKEN_OVERFLOW":
        return {
            "prevents": ["TOKEN_OVERFLOW errors", "provider context-length rejections"],
            "improves": ["request success rate", "latency stability"],
            "confidence": confidence_level,
        }
    if diagnosis_type == "RATE_LIMIT":
        return {
            "prevents": ["RATE_LIMIT errors", "request failures due to throttling"],
            "improves": ["request reliability", "transient failure handling"],
            "confidence": confidence_level,
        }
    if diagnosis_type == "AUTH_FAILURE":
        return {
            "prevents": ["AUTH_FAILURE errors", "unauthorized request rejections"],
            "improves": ["security posture", "credential management"],
            "confidence": confidence_level,
        }
    if diagnosis_type == "COST_SPIKE":
        return {
            "prevents": ["unexpected cost overruns", "budget exhaustion"],
            "improves": ["cost predictability", "resource efficiency"],
            "confidence": confidence_level,
        }
    if diagnosis_type == "LOOP_DETECTED":
        return {
            "prevents": ["runaway agent loops", "repeated no-progress tool calls"],
            "improves": ["agent reliability", "cost predictability"],
            "confidence": confidence_level,
        }
    return {
        "prevents": ["recurrence of the diagnosed failure if the selected fix is correct"],
        "improves": ["debuggability"],
        "confidence": confidence_level,
    }


def _blast_radius(*, fix_scope: str, target_file: str) -> str:
    if target_file == "unknown":
        return "medium"
    if fix_scope == "local":
        return "low"
    if fix_scope == "module":
        return "medium"
    return "high"


def _affected_paths(*, request: FixGenerationInput, target_file: str) -> list[str]:
    paths: list[str] = []
    if target_file and target_file != "unknown":
        paths.append(target_file)
    additional_paths = _as_text_list(request.call_context.get("affected_paths"))
    for path in additional_paths:
        if path not in paths:
            paths.append(path)
    return paths


def _fix_conflicts_with(request: FixGenerationInput) -> list[str]:
    raw = request.call_context.get("fix_conflicts_with")
    return _as_text_list(raw)


def _time_to_apply_estimate(
    *,
    diagnosis_type: str,
    target_file: str,
    patch_unified: str,
) -> str:
    if target_file == "unknown" or not patch_unified:
        return "15-30 minutes"
    if diagnosis_type == "LOOP_DETECTED":
        return "15-30 minutes"
    if diagnosis_type == "TOKEN_OVERFLOW":
        return "5-10 minutes"
    if diagnosis_type == "RATE_LIMIT":
        return "5-15 minutes"
    if diagnosis_type == "AUTH_FAILURE":
        return "10-20 minutes"
    if diagnosis_type == "COST_SPIKE":
        return "20-40 minutes"
    return "10-20 minutes"


def _rollout_strategy(diagnosis_type: str) -> str:
    strategies = {
        "TOKEN_OVERFLOW": "single-call",
        "RATE_LIMIT": "gradual",
        "AUTH_FAILURE": "guarded",
        "COST_SPIKE": "gradual",
        "LOOP_DETECTED": "guarded",
    }
    return strategies.get(diagnosis_type, "guarded")


def _requires_tests_update(diagnosis_type: str) -> bool:
    return diagnosis_type in {"TOKEN_OVERFLOW", "LOOP_DETECTED", "RATE_LIMIT", "AUTH_FAILURE", "COST_SPIKE"}


def _observability_checks(diagnosis_type: str) -> list[str]:
    if diagnosis_type == "TOKEN_OVERFLOW":
        return [
            "Monitor TOKEN_OVERFLOW error rate after deployment.",
            "Track request success rate for the affected route.",
            "Track response latency and response-quality complaints.",
        ]
    if diagnosis_type == "RATE_LIMIT":
        return [
            "Monitor RATE_LIMIT error rate and retry success rate.",
            "Track p99 latency under rate limiting conditions.",
        ]
    if diagnosis_type == "AUTH_FAILURE":
        return [
            "Monitor AUTH_FAILURE error rate and credential rotation success.",
            "Track authentication success rate after deployment.",
        ]
    if diagnosis_type == "COST_SPIKE":
        return [
            "Monitor cost per request and total spend trends.",
            "Track cache hit rates if caching is implemented.",
        ]
    if diagnosis_type == "LOOP_DETECTED":
        return [
            "Monitor LOOP_DETECTED recurrence after deployment.",
            "Track guard-trigger counts and agent task completion rate.",
            "Watch cost per task for unexpected increases or drops.",
        ]
    return [
        "Monitor recurrence of the diagnosed failure.",
        "Track error rate and latency for the affected path.",
    ]


def _fix_tags(diagnosis_type: str) -> list[str]:
    if diagnosis_type == "TOKEN_OVERFLOW":
        return ["token", "prompt", "context-limit"]
    if diagnosis_type == "RATE_LIMIT":
        return ["rate-limit", "retry", "backoff"]
    if diagnosis_type == "AUTH_FAILURE":
        return ["auth", "credentials", "security"]
    if diagnosis_type == "COST_SPIKE":
        return ["cost", "budget", "optimization"]
    if diagnosis_type == "LOOP_DETECTED":
        return ["agent-loop", "guardrail", "no-progress"]
    return ["diagnosis", "manual-review"]


def _fix_category(diagnosis_type: str) -> str:
    categories = {
        "TOKEN_OVERFLOW": "reliability",
        "RATE_LIMIT": "reliability",
        "AUTH_FAILURE": "security",
        "COST_SPIKE": "cost",
        "LOOP_DETECTED": "safety",
    }
    return categories.get(diagnosis_type, "reliability")


def _recommended_priority(*, diagnosis_type: str, confidence_level: str) -> str:
    if confidence_level == "low":
        return "P2"
    if diagnosis_type == "TOKEN_OVERFLOW":
        return "P0"
    if diagnosis_type == "LOOP_DETECTED":
        return "P1"
    if diagnosis_type == "RATE_LIMIT":
        return "P1"
    if diagnosis_type == "AUTH_FAILURE":
        return "P0"
    if diagnosis_type == "COST_SPIKE":
        return "P1"
    return "P1"


def _reversibility(*, patch_unified: str, target_file: str, diagnosis_type: str) -> str:
    # When no patch is generated (empty patch_unified), return moderate
    if not patch_unified:
        return "moderate"
    if target_file == "unknown":
        return "hard"
    reversibility_map = {
        "TOKEN_OVERFLOW": "easy",
        "RATE_LIMIT": "easy",
        "AUTH_FAILURE": "moderate",
        "COST_SPIKE": "easy",
        "LOOP_DETECTED": "moderate",
    }
    return reversibility_map.get(diagnosis_type, "moderate")


def _apply_instructions(*, target_file: str, anchor: str, patch_unified: str) -> list[str]:
    if target_file == "unknown":
        return [
            "Locate the file described by file_hint.",
            f"Find the relevant anchor or equivalent code: {anchor}.",
            "Apply the AFTER block manually after confirming it matches the call site.",
            "Run the scenario that previously triggered the diagnosis.",
        ]

    if patch_unified:
        return [
            f"Open `{target_file}`.",
            f"Locate the anchor line: `{anchor}`.",
            "Apply the unified patch draft or replace the BEFORE block with the AFTER block.",
            "Run the scenario that previously triggered the diagnosis.",
        ]

    return [
        f"Open `{target_file}`.",
        f"Locate the anchor or equivalent code: `{anchor}`.",
        "Apply the conceptual advisory change manually.",
        "Run the scenario that previously triggered the diagnosis.",
    ]


def _fix_id(*, diagnosis_type: str, diagnosis_id: str | None) -> str:
    safe_id = _slug(diagnosis_id or "diagnosis", fallback="diagnosis")
    return f"fix-{diagnosis_type.lower()}-{safe_id}"


def _target_file(request: FixGenerationInput) -> str:
    for value in (
        request.target_file,
        request.call_context.get("target_file"),
        request.call_context.get("file_path"),
        request.evidence.get("target_file"),
        request.evidence.get("file_path"),
    ):
        normalized = _as_text(value)
        if normalized:
            return normalized
    return "unknown"


def _file_hint(request: FixGenerationInput, diagnosis_type: str) -> str:
    explicit_hint = _as_text(request.file_hint)
    if explicit_hint:
        return explicit_hint

    if _target_file(request) != "unknown":
        return "Review the target file around the anchor before applying the patch."
    if diagnosis_type == "TOKEN_OVERFLOW":
        return "Apply where messages/history/max_tokens are constructed before the provider call."
    if diagnosis_type == "RATE_LIMIT":
        return "Apply at the provider client request site where rate limiting occurs."
    if diagnosis_type == "AUTH_FAILURE":
        return "Apply at the credential management or authentication flow code."
    if diagnosis_type == "COST_SPIKE":
        return "Apply cost controls at the provider call site or request routing layer."
    if diagnosis_type == "LOOP_DETECTED":
        return "Apply at the agent or tool dispatch loop that repeats without progress."
    return "Apply at the smallest call site directly responsible for the diagnosed behavior."


def _fallback_anchor(diagnosis_type: str) -> str:
    if diagnosis_type == "TOKEN_OVERFLOW":
        return "messages construction before provider call"
    if diagnosis_type == "RATE_LIMIT":
        return "provider request site"
    if diagnosis_type == "AUTH_FAILURE":
        return "credential configuration"
    if diagnosis_type == "COST_SPIKE":
        return "model request configuration"
    if diagnosis_type == "LOOP_DETECTED":
        return "agent/tool dispatch loop"
    return "unknown"


def _anchor_from_diff(diff: str) -> str | None:
    before, _after = _extract_before_after(diff)
    if before:
        return before.splitlines()[0].strip() or None
    return None


def _build_unified_patch(*, target_file: str, diff: str) -> str:
    if target_file == "unknown":
        return ""

    before, after = _extract_before_after(diff)
    if not before or not after:
        return ""

    before_lines = before.splitlines()
    after_lines = after.splitlines()
    old_count = max(1, len(before_lines))
    new_count = max(1, len(after_lines))
    hunk = [
        f"diff --git a/{target_file} b/{target_file}",
        f"--- a/{target_file}",
        f"+++ b/{target_file}",
        f"@@ -1,{old_count} +1,{new_count} @@",
    ]
    hunk.extend(f"-{line}" for line in before_lines)
    hunk.extend(f"+{line}" for line in after_lines)
    return "\n".join(hunk)


def _extract_before_after(diff: str) -> tuple[str | None, str | None]:
    if "--- BEFORE ---" not in diff or "--- AFTER ---" not in diff:
        return None, None

    before_part, after_part = diff.split("--- AFTER ---", 1)
    before = before_part.replace("--- BEFORE ---", "", 1).strip("\n")
    after = after_part.strip("\n")
    if not before.strip() or not after.strip():
        return None, None
    return before, after


def _conceptual_diff(header: str, lines: list[str]) -> str:
    rendered = ["--- ADVISORY ---", f"# {header}"]
    rendered.extend(f"# - {line}" for line in lines)
    return "\n".join(rendered)


def _before_after_diff(*, before: str, after: str) -> str:
    return "\n".join(
        [
            "--- BEFORE ---",
            before.rstrip(),
            "",
            "--- AFTER ---",
            after.rstrip(),
        ]
    )


def _first_relevant_line(snippet: str, needles: tuple[str, ...]) -> str | None:
    for line in snippet.splitlines():
        lowered = line.lower()
        if any(needle.lower() in lowered for needle in needles):
            return line
    return None


def _replace_assignment_rhs(line: str, replacement: str) -> str:
    if "=" not in line:
        return line
    left, _right = line.split("=", 1)
    suffix = "," if line.rstrip().endswith(",") else ""
    return f"{left.rstrip()} = {replacement}{suffix}"


def _assignment_rhs(line: str) -> str:
    if "=" not in line:
        return "messages"
    rhs = line.split("=", 1)[1].strip().rstrip(",")
    return rhs or "messages"


def _token_budget(model_limit: int) -> int:
    if model_limit <= 0:
        return 3000
    return max(512, int(model_limit * 0.75))


def _evidence_summary_lines(evidence: Mapping[str, Any]) -> list[str]:
    keys = (
        "detected_by",
        "detection_signals",
        "estimated_tokens",
        "model_limit",
        "overflow_by",
        "repeat_count",
        "repeat_window_seconds",
        "prompt_fingerprint",
        "error_snippet",
    )
    lines: list[str] = []
    for key in keys:
        value = evidence.get(key)
        if value is None or value == "":
            continue
        lines.append(f"- `{key}`: `{value}`")
    return lines


def _normalize_diagnosis_type(value: str) -> str:
    normalized = _as_text(value, fallback="UNKNOWN").upper().replace("-", "_").replace(" ", "_")
    return normalized or "UNKNOWN"


def _slug(value: str, *, fallback: str) -> str:
    normalized = _as_text(value).lower().replace(" ", "-")
    normalized = _BRANCH_SANITIZE_RE.sub("-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-./")
    return normalized or fallback


def _clean_snippet(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    masked = mask_text(value.strip())
    return masked if masked is not None else ""


def _as_text(value: Any, *, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return mask_text(value.strip()) or fallback
    try:
        text = mask_text(str(value).strip())
    except Exception:
        return fallback
    return text or fallback


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return 0
    return 0


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list | tuple | set):
        result: list[str] = []
        for item in value:
            text = _as_text(item)
            if text and text not in result:
                result.append(text)
        return result
    text = _as_text(value)
    return [text] if text else []


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def _rate_limit_diff_from_snippet(snippet: str, *, retry_after: int) -> str:
    line = _first_relevant_line(snippet, ("request", "post", "get", "client", "call"))
    if line:
        return _before_after_diff(
            before=line,
            after=f"<existing_retry_wrapper>(\n    lambda: {line},\n    max_retries=3,\n    base_delay=1.0,\n)",
        )
    return _before_after_diff(
        before="# Original request code",
        after=(
            "# Add retry logic around the rate-limited request\n"
            "response = <existing_retry_wrapper>(\n"
            "    make_request,\n"
            "    max_retries=3,\n"
            "    base_delay=1.0,\n"
            ")"
        ),
    )


def _auth_failure_diff_from_snippet(snippet: str, *, status_code: int) -> str:
    line = _first_relevant_line(snippet, ("api_key", "token", "auth", "authorization", "credential"))
    if line and "=" in line:
        return _before_after_diff(
            before=line,
            after="api_key = <existing_credential_manager>.get_valid_key()  # Rotatable, validated",
        )
    return _before_after_diff(
        before="# Original authentication code",
        after=(
            "# Add credential validation and rotation\n"
            "api_key = <existing_credential_manager>.get_valid_key()\n"
            "if not api_key:\n"
            "    raise AuthenticationError(\"No valid credentials available\")"
        ),
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
