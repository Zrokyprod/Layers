"""
Fix verification and assessment helpers.

Pure functions — no I/O, no DB access, no LLM calls.
Consumed by fix_generator.generate_fix_suggestion and pr.build_pr_draft_payload.
"""
from __future__ import annotations

from typing import Any

from app.services._fix_utils import _as_text, _as_text_list, _clean_snippet, _clamp


# ── Confidence ───────────────────────────────────────────────────────────────

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


# ── Risk / scope ─────────────────────────────────────────────────────────────

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


def _blast_radius(*, fix_scope: str, target_file: str) -> str:
    if target_file == "unknown":
        return "medium"
    if fix_scope == "local":
        return "low"
    if fix_scope == "module":
        return "medium"
    return "high"


# ── Impact / tags / category / priority ──────────────────────────────────────

def _expected_impact(*, diagnosis_type: str, confidence_level: str) -> dict[str, Any]:
    if diagnosis_type == "TOKEN_OVERFLOW":
        return {"prevents": ["TOKEN_OVERFLOW errors", "provider context-length rejections"], "improves": ["request success rate", "latency stability"], "confidence": confidence_level}
    if diagnosis_type == "RATE_LIMIT":
        return {"prevents": ["RATE_LIMIT errors", "request failures due to throttling"], "improves": ["request reliability", "transient failure handling"], "confidence": confidence_level}
    if diagnosis_type == "AUTH_FAILURE":
        return {"prevents": ["AUTH_FAILURE errors", "unauthorized request rejections"], "improves": ["security posture", "credential management"], "confidence": confidence_level}
    if diagnosis_type == "COST_SPIKE":
        return {"prevents": ["unexpected cost overruns", "budget exhaustion"], "improves": ["cost predictability", "resource efficiency"], "confidence": confidence_level}
    if diagnosis_type == "LOOP_DETECTED":
        return {"prevents": ["runaway agent loops", "repeated no-progress tool calls"], "improves": ["agent reliability", "cost predictability"], "confidence": confidence_level}
    return {"prevents": ["recurrence of the diagnosed failure if the selected fix is correct"], "improves": ["debuggability"], "confidence": confidence_level}


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
    return {
        "TOKEN_OVERFLOW": "reliability",
        "RATE_LIMIT": "reliability",
        "AUTH_FAILURE": "security",
        "COST_SPIKE": "cost",
        "LOOP_DETECTED": "safety",
    }.get(diagnosis_type, "reliability")


def _recommended_priority(*, diagnosis_type: str, confidence_level: str) -> str:
    if confidence_level == "low":
        return "P2"
    if diagnosis_type in {"TOKEN_OVERFLOW", "AUTH_FAILURE"}:
        return "P0"
    if diagnosis_type in {"LOOP_DETECTED", "RATE_LIMIT", "COST_SPIKE"}:
        return "P1"
    return "P1"


# ── Rollout / reversibility ───────────────────────────────────────────────────

def _rollout_strategy(diagnosis_type: str) -> str:
    return {
        "TOKEN_OVERFLOW": "single-call",
        "RATE_LIMIT": "gradual",
        "AUTH_FAILURE": "guarded",
        "COST_SPIKE": "gradual",
        "LOOP_DETECTED": "guarded",
    }.get(diagnosis_type, "guarded")


def _requires_tests_update(diagnosis_type: str) -> bool:
    return diagnosis_type in {"TOKEN_OVERFLOW", "LOOP_DETECTED", "RATE_LIMIT", "AUTH_FAILURE", "COST_SPIKE"}


def _observability_checks(diagnosis_type: str) -> list[str]:
    if diagnosis_type == "TOKEN_OVERFLOW":
        return ["Monitor TOKEN_OVERFLOW error rate after deployment.", "Track request success rate for the affected route.", "Track response latency and response-quality complaints."]
    if diagnosis_type == "RATE_LIMIT":
        return ["Monitor RATE_LIMIT error rate and retry success rate.", "Track p99 latency under rate limiting conditions."]
    if diagnosis_type == "AUTH_FAILURE":
        return ["Monitor AUTH_FAILURE error rate and credential rotation success.", "Track authentication success rate after deployment."]
    if diagnosis_type == "COST_SPIKE":
        return ["Monitor cost per request and total spend trends.", "Track cache hit rates if caching is implemented."]
    if diagnosis_type == "LOOP_DETECTED":
        return ["Monitor LOOP_DETECTED recurrence after deployment.", "Track guard-trigger counts and agent task completion rate.", "Watch cost per task for unexpected increases or drops."]
    return ["Monitor recurrence of the diagnosed failure.", "Track error rate and latency for the affected path."]


def _reversibility(*, patch_unified: str, target_file: str, diagnosis_type: str) -> str:
    if not patch_unified:
        return "moderate"
    if target_file == "unknown":
        return "hard"
    return {
        "TOKEN_OVERFLOW": "easy",
        "RATE_LIMIT": "easy",
        "AUTH_FAILURE": "moderate",
        "COST_SPIKE": "easy",
        "LOOP_DETECTED": "moderate",
    }.get(diagnosis_type, "moderate")


# ── Time / paths ──────────────────────────────────────────────────────────────

def _time_to_apply_estimate(*, diagnosis_type: str, target_file: str, patch_unified: str) -> str:
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


def _affected_paths(*, request: Any, target_file: str) -> list[str]:
    paths: list[str] = []
    if target_file and target_file != "unknown":
        paths.append(target_file)
    for path in _as_text_list(request.call_context.get("affected_paths")):
        if path not in paths:
            paths.append(path)
    return paths


def _fix_conflicts_with(request: Any) -> list[str]:
    return _as_text_list(request.call_context.get("fix_conflicts_with"))


# ── Apply instructions ────────────────────────────────────────────────────────

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


# ── Fix ID / target / hint / anchor ──────────────────────────────────────────

def _fix_id(*, diagnosis_type: str, diagnosis_id: str | None) -> str:
    from app.services._fix_utils import _slug
    safe_id = _slug(diagnosis_id or "diagnosis", fallback="diagnosis")
    return f"fix-{diagnosis_type.lower()}-{safe_id}"


def _target_file(request: Any) -> str:
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


def _file_hint(request: Any, diagnosis_type: str) -> str:
    explicit_hint = _as_text(request.file_hint)
    if explicit_hint:
        return explicit_hint
    if _target_file(request) != "unknown":
        return "Review the target file around the anchor before applying the patch."
    hints = {
        "TOKEN_OVERFLOW": "Apply where messages/history/max_tokens are constructed before the provider call.",
        "RATE_LIMIT": "Apply at the provider client request site where rate limiting occurs.",
        "AUTH_FAILURE": "Apply at the credential management or authentication flow code.",
        "COST_SPIKE": "Apply cost controls at the provider call site or request routing layer.",
        "LOOP_DETECTED": "Apply at the agent or tool dispatch loop that repeats without progress.",
    }
    return hints.get(diagnosis_type, "Apply at the smallest call site directly responsible for the diagnosed behavior.")


def _fallback_anchor(diagnosis_type: str) -> str:
    return {
        "TOKEN_OVERFLOW": "messages construction before provider call",
        "RATE_LIMIT": "provider request site",
        "AUTH_FAILURE": "credential configuration",
        "COST_SPIKE": "model request configuration",
        "LOOP_DETECTED": "agent/tool dispatch loop",
    }.get(diagnosis_type, "unknown")
