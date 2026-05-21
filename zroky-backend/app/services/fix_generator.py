"""
fix_generator — thin orchestrator.

Strategy logic: app.services.strategies.*
Fix assessment: app.services.verify
PR draft:       app.services.pr
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from app.services.privacy import mask_value
from app.services._fix_utils import _clean_snippet, _normalize_diagnosis_type
from app.services.strategies import (
    FixTuple,
    _ai_fix,
    generate_token_overflow,
    generate_loop_detected,
    generate_rate_limit,
    generate_auth_failure,
    generate_cost_spike,
    generate_generic,
)
from app.services.strategies._diff import _anchor_from_diff, _build_unified_patch
from app.services.verify import (
    _affected_paths,
    _apply_instructions,
    _blast_radius,
    _confidence_level,
    _derive_fix_confidence,
    _expected_impact,
    _fallback_anchor,
    _file_hint,
    _fix_category,
    _fix_conflicts_with,
    _fix_id,
    _fix_scope,
    _fix_tags,
    _observability_checks,
    _recommended_priority,
    _requires_tests_update,
    _reversibility,
    _risk_level,
    _rollout_strategy,
    _target_file,
    _time_to_apply_estimate,
)
from app.services.pr import PullRequestDraftPayload, build_pr_draft_payload

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


# ── Strategy dispatch ─────────────────────────────────────────────────────────

_STRATEGY_MAP = {
    "TOKEN_OVERFLOW": generate_token_overflow,
    "LOOP_DETECTED": generate_loop_detected,
    "RATE_LIMIT": generate_rate_limit,
    "AUTH_FAILURE": generate_auth_failure,
    "COST_SPIKE": generate_cost_spike,
}


def generate_fix_suggestion(
    request: FixGenerationInput,
    *,
    base_branch: str = "main",
    db: Any | None = None,
) -> FixSuggestion:
    diagnosis_type = _normalize_diagnosis_type(request.diagnosis_type)
    fix_id_val = _fix_id(diagnosis_type=diagnosis_type, diagnosis_id=request.diagnosis_id)

    ai_result = _ai_fix(request, db=db)
    if ai_result is not None:
        logger.info(
            "AI fix generated for diagnosis_type=%s diagnosis_id=%s confidence=%.2f",
            diagnosis_type, request.diagnosis_id, ai_result[8],
        )
        (title, diff, explanation, fix_rationale, alternatives,
         review_points, verification_steps, rollback_instructions, strategy_confidence) = ai_result
    else:
        strategy_fn = _STRATEGY_MAP.get(diagnosis_type, generate_generic)
        (title, diff, explanation, fix_rationale, alternatives,
         review_points, verification_steps, rollback_instructions, strategy_confidence) = strategy_fn(request)

    confidence = _derive_fix_confidence(
        diagnosis_confidence=request.diagnosis_confidence,
        strategy_confidence=strategy_confidence,
        has_code_snippet=bool(_clean_snippet(request.code_snippet)),
    )
    target_file = _target_file(request)
    file_hint = _file_hint(request, diagnosis_type)
    anchor = _anchor_from_diff(diff) or _fallback_anchor(diagnosis_type)
    patch_unified = _build_unified_patch(target_file=target_file, diff=diff)
    confidence_level = _confidence_level(confidence)
    risk_level = _risk_level(diagnosis_type, confidence_level)
    fix_scope = _fix_scope(diagnosis_type)
    blast_radius = _blast_radius(fix_scope=fix_scope, target_file=target_file)
    time_to_apply_estimate = _time_to_apply_estimate(
        diagnosis_type=diagnosis_type, target_file=target_file, patch_unified=patch_unified,
    )
    requires_tests_update = _requires_tests_update(diagnosis_type)
    affected_paths = _affected_paths(request=request, target_file=target_file)
    fix_conflicts_with = _fix_conflicts_with(request)
    rollout_strategy = _rollout_strategy(diagnosis_type)
    observability_checks = _observability_checks(diagnosis_type)
    reversibility = _reversibility(
        patch_unified=patch_unified, target_file=target_file, diagnosis_type=diagnosis_type,
    )
    fix_category = _fix_category(diagnosis_type)
    recommended_priority = _recommended_priority(
        diagnosis_type=diagnosis_type, confidence_level=confidence_level,
    )
    fix_tags = _fix_tags(diagnosis_type)
    expected_impact = _expected_impact(
        diagnosis_type=diagnosis_type, confidence_level=confidence_level,
    )
    apply_instructions = _apply_instructions(
        target_file=target_file, anchor=anchor, patch_unified=patch_unified,
    )
    pr = build_pr_draft_payload(
        fix_id=fix_id_val,
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
        fix_id=fix_id_val,
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

