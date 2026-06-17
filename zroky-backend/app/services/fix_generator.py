from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from app.services._internal.fix_generator_helpers import (
    _affected_paths,
    _anchor_from_diff,
    _apply_instructions,
    _blast_radius,
    _build_unified_patch,
    _clean_snippet,
    _confidence_level,
    _derive_fix_confidence,
    _evidence_summary_lines,
    _expected_impact,
    _fallback_anchor,
    _file_hint,
    _fix_category,
    _fix_conflicts_with,
    _fix_id,
    _fix_scope,
    _fix_tags,
    _normalize_diagnosis_type,
    _observability_checks,
    _recommended_priority,
    _requires_tests_update,
    _reversibility,
    _risk_level,
    _rollout_strategy,
    _slug,
    _target_file,
    _time_to_apply_estimate,
)
from app.services._internal.fix_generator_strategies import (
    _auth_failure_fix,
    _cost_spike_fix,
    _generic_fix,
    _loop_detected_fix,
    _rate_limit_fix,
    _token_overflow_fix,
)
from app.services.privacy import mask_value

logger = logging.getLogger(__name__)


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


