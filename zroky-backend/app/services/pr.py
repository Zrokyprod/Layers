"""
Pull-request draft payload builder.

Imported by fix_generator.generate_fix_suggestion; also publicly
available as app.services.pr.build_pr_draft_payload.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.services._fix_utils import _normalize_diagnosis_type, _slug


@dataclass(frozen=True)
class PullRequestDraftPayload:
    branch_name: str
    commit_message: str
    pr_title: str
    pr_description: str
    base_branch: str = "main"


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


def _evidence_summary_lines(evidence: Mapping[str, Any]) -> list[str]:
    keys = (
        "detected_by", "detection_signals", "estimated_tokens", "model_limit",
        "overflow_by", "repeat_count", "repeat_window_seconds", "prompt_fingerprint",
        "error_snippet",
    )
    lines: list[str] = []
    for key in keys:
        value = evidence.get(key)
        if value is None or value == "":
            continue
        lines.append(f"- `{key}`: `{value}`")
    return lines
