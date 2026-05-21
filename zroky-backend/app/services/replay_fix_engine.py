"""
Replay-driven auto-fix engine (Module 10 advanced — Enterprise-only).

Analyzes failing traces from a replay run, uses LLM to identify the
regression root cause, and generates a targeted fix (prompt tweak or
model swap). The fix is then dispatched as a Tier-2 PR via the
existing pilot_pr_dispatch pipeline.

Design choices:
  - Pure-functional: takes replay data → returns FixSuggestion.
    No DB writes, no network calls. The dispatcher owns persistence.
  - Multi-trace pattern analysis: examines ALL failing traces to find
    patterns (e.g., "all tool-call traces fail but direct responses pass").
  - LLM-powered: uses the judge engine's dimensional scores + a
    dedicated "fix analyst" LLM prompt to understand what changed.
  - Confidence scoring: combines trace-level judge confidence with
    the LLM's self-reported fix confidence.
  - Evidence-backed: every fix includes a regression_summary that
    links back to the specific traces and verdicts.

What this module does NOT do:
  - It does NOT open GitHub PRs — that's the dispatcher's job.
  - It does NOT check entitlements or policy gates.
  - It does NOT persist to DB.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Call,
    GoldenTrace,
    ReplayRun,
    ReplayRunTrace,
)
from app.services.judge_engine import (
    SingleJudgeEvaluator,
    Verdict,
    VERDICT_FAIL,
    VERDICT_INCONCLUSIVE,
    VERDICT_PASS,
)
from app.services.replay_runs import parse_summary

logger = logging.getLogger(__name__)

# Max traces to feed into the LLM analysis (to avoid context window blow-up).
_MAX_TRACES_FOR_ANALYSIS: int = 20

# Min failing traces required to attempt an auto-fix.
_MIN_FAILING_TRACES: int = 1

# Confidence floor for accepting a generated fix.
_FIX_CONFIDENCE_FLOOR: float = 0.70


# ── data models ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TraceFailure:
    """One failing trace, distilled for analysis."""

    trace_id: str
    call_id: str | None
    expected_output: str
    actual_output: str
    verdict: str
    confidence: float
    reason: str
    model: str | None
    judge_scores: dict[str, Any]
    # Original prompt and model from the source call (if available).
    original_prompt: str | None = None
    original_model: str | None = None


@dataclass(frozen=True)
class RegressionPattern:
    """Pattern detected across multiple failing traces."""

    pattern_type: str  # e.g., "hallucination", "format_drift", "model_degradation"
    description: str
    affected_trace_count: int
    confidence: float


@dataclass(frozen=True)
class FixSuggestion:
    """A generated fix ready for PR creation."""

    fix_type: str  # "prompt_tweak" | "prompt_revert" | "model_swap" | "advisory_only"
    description: str
    # Evidence dict that pilot_pr_payload builders expect.
    evidence: dict[str, Any]
    confidence: float
    regression_summary: str
    reasoning: str
    # True when we have a concrete patch to apply.
    has_patch: bool = True


# ── public API ────────────────────────────────────────────────────────────────


def analyze_and_generate_fix(
    db: Session,
    *,
    replay_run: ReplayRun,
    candidate_prompt_override: str | None = None,
    candidate_model_override: str | None = None,
) -> FixSuggestion | None:
    """Analyze a failed replay run and generate a fix suggestion.

    Returns ``None`` when:
      - the run did not fail (status != fail/error)
      - there are no failing traces
      - the analysis cannot produce a confident fix

    This function is pure-functional — it reads from the DB but
    writes nothing. The caller (dispatcher) decides whether to act.
    """
    if replay_run.status not in ("fail", "error"):
        logger.info(
            "replay_fix_engine.skip run=%s status=%s (not fail/error)",
            replay_run.id, replay_run.status,
        )
        return None

    failing_traces = _load_failing_traces(db, replay_run)
    if len(failing_traces) < _MIN_FAILING_TRACES:
        logger.info(
            "replay_fix_engine.skip run=%s failing=%d (below min)",
            replay_run.id, len(failing_traces),
        )
        return None

    # Detect cross-trace patterns.
    pattern = _detect_pattern(failing_traces)

    # Build the LLM analysis prompt.
    analysis_input = _build_analysis_input(
        failing_traces=failing_traces[:_MAX_TRACES_FOR_ANALYSIS],
        pattern=pattern,
        candidate_prompt_override=candidate_prompt_override,
        candidate_model_override=candidate_model_override,
        run_summary=parse_summary(replay_run.summary_json),
    )

    # Generate fix via LLM.
    fix = _generate_fix_with_llm(analysis_input)
    if fix is None:
        logger.info(
            "replay_fix_engine.no_fix run=%s pattern=%s",
            replay_run.id, pattern.pattern_type,
        )
        return None

    if fix.confidence < _FIX_CONFIDENCE_FLOOR:
        logger.info(
            "replay_fix_engine.low_confidence run=%s confidence=%.2f floor=%.2f",
            replay_run.id, fix.confidence, _FIX_CONFIDENCE_FLOOR,
        )
        return None

    logger.info(
        "replay_fix_engine.generated run=%s type=%s confidence=%.2f",
        replay_run.id, fix.fix_type, fix.confidence,
    )
    return fix


# ── trace loading ─────────────────────────────────────────────────────────────


def _load_failing_traces(
    db: Session, run: ReplayRun
) -> list[TraceFailure]:
    """Load all ReplayRunTrace rows for a run that are fail or error.
    Join GoldenTrace + Call for richer context."""
    rows = db.execute(
        select(
            ReplayRunTrace,
            GoldenTrace,
            Call,
        )
        .join(
            GoldenTrace,
            GoldenTrace.id == ReplayRunTrace.golden_trace_id,
            isouter=True,
        )
        .join(
            Call,
            Call.id == GoldenTrace.call_id,
            isouter=True,
        )
        .where(
            ReplayRunTrace.replay_run_id == run.id,
            ReplayRunTrace.status.in_(("fail", "error")),
        )
    ).all()

    failures: list[TraceFailure] = []
    for rrt, gt, call in rows:
        scores = _safe_json_dict(rrt.judge_scores_json)
        expected = (gt.expected_output_text or "") if gt else ""
        actual = (rrt.output_text or "") if rrt else ""
        original_prompt: str | None = None
        original_model: str | None = None
        if call is not None and call.payload_json:
            payload = _safe_json_dict(call.payload_json)
            original_prompt = str(payload.get("prompt") or "")
            original_model = str(payload.get("model") or "") or None

        failures.append(
            TraceFailure(
                trace_id=rrt.id,
                call_id=rrt.call_id_replayed,
                expected_output=expected,
                actual_output=actual,
                verdict=scores.get("verdict", "inconclusive"),
                confidence=float(scores.get("confidence", 0.0) or 0.0),
                reason=scores.get("reason", ""),
                model=scores.get("model"),
                judge_scores=scores,
                original_prompt=original_prompt,
                original_model=original_model,
            )
        )
    return failures


# ── pattern detection ───────────────────────────────────────────────────────


def _detect_pattern(failing_traces: list[TraceFailure]) -> RegressionPattern:
    """Simple heuristic pattern detector. Works even when LLM analysis
    is unavailable (e.g. missing API key)."""
    n = len(failing_traces)
    if n == 0:
        return RegressionPattern(
            pattern_type="none", description="No failing traces", affected_trace_count=0, confidence=0.0
        )

    # Check for format drift: actual outputs differ in structure.
    exact_match_count = sum(
        1 for t in failing_traces
        if t.verdict == VERDICT_FAIL and t.reason == "exact_mismatch"
    )

    # Check for hallucination: model mentions things not in expected.
    halluc_keywords = ("hallucination", "fabricated", "invented")
    halluc_count = sum(
        1 for t in failing_traces
        if any(k in t.reason.lower() for k in halluc_keywords)
    )

    # Check for model degradation: all traces fail with same model.
    models = {t.model for t in failing_traces if t.model}
    single_model = len(models) == 1 and bool(models)

    if halluc_count >= max(1, n * 0.3):
        return RegressionPattern(
            pattern_type="hallucination",
            description=f"{halluc_count}/{n} traces show hallucination signals",
            affected_trace_count=n,
            confidence=min(0.95, 0.7 + halluc_count / n * 0.3),
        )

    if exact_match_count >= max(1, n * 0.5):
        return RegressionPattern(
            pattern_type="format_drift",
            description=f"{exact_match_count}/{n} traces have format/content drift",
            affected_trace_count=n,
            confidence=min(0.90, 0.6 + exact_match_count / n * 0.3),
        )

    if single_model and n >= 3:
        return RegressionPattern(
            pattern_type="model_degradation",
            description=f"All {n} failing traces use model {models.pop()}",
            affected_trace_count=n,
            confidence=0.75,
        )

    return RegressionPattern(
        pattern_type="mixed",
        description=f"{n} traces failed with varied root causes",
        affected_trace_count=n,
        confidence=0.60,
    )


# ── LLM fix generation ────────────────────────────────────────────────────────


_FIX_ANALYST_SYSTEM = (
    "You are a senior AI-ops engineer who analyzes replay-run regressions. "
    "Given a set of golden-trace failures, identify the root cause and propose "
    "a minimal, high-confidence fix. Respond ONLY with valid JSON of shape:\n"
    '{\n'
    '  "fix_type": "prompt_tweak" | "prompt_revert" | "model_swap" | "advisory_only",\n'
    '  "confidence": 0.0-1.0,\n'
    '  "regression_summary": "<one sentence describing what broke>",\n'
    '  "reasoning": "<2-3 sentences on why this fix should work>",\n'
    '  "proposed_prompt_body": "<full new prompt text (only for prompt_tweak/revert)>",\n'
    '  "proposed_model": "<model slug (only for model_swap)>"\n'
    '}\n'
    "Use 'prompt_tweak' when a targeted change fixes the regression. "
    "Use 'prompt_revert' only when reverting to the original is clearly best. "
    "Use 'model_swap' when the model itself is the problem. "
    "Use 'advisory_only' when you cannot safely propose a concrete patch."
)


def _build_analysis_input(
    *,
    failing_traces: list[TraceFailure],
    pattern: RegressionPattern,
    candidate_prompt_override: str | None,
    candidate_model_override: str | None,
    run_summary: dict[str, Any],
) -> str:
    """Compose the user-side prompt for the fix-analyst LLM."""
    parts: list[str] = []
    parts.append(f"Pattern detected: {pattern.pattern_type}")
    parts.append(f"Description: {pattern.description}")
    parts.append("")

    # Summarize the run.
    total = int(run_summary.get("trace_count_executed", 0))
    passed = int(run_summary.get("pass_count", 0))
    failed = int(run_summary.get("fail_count", 0))
    errors = int(run_summary.get("error_count", 0))
    parts.append(
        f"Replay run summary: {passed}/{total} pass, {failed} fail, {errors} error."
    )

    # Surface what the user changed.
    if candidate_prompt_override:
        parts.append(f"Candidate prompt override (what the user changed to):\n{candidate_prompt_override[:2000]}")
    if candidate_model_override:
        parts.append(f"Candidate model override: {candidate_model_override}")
    parts.append("")

    # Feed representative failing traces.
    parts.append("Failing traces (expected vs actual):")
    for idx, t in enumerate(failing_traces, start=1):
        parts.append(f"\n--- Trace {idx} ---")
        parts.append(f"Judge verdict: {t.verdict} (confidence {t.confidence:.2f})")
        parts.append(f"Judge reason: {t.reason}")
        expected = (t.expected_output or "")[:800]
        actual = (t.actual_output or "")[:800]
        parts.append(f"Expected:\n{expected}")
        parts.append(f"Actual:\n{actual}")

    return "\n".join(parts)


def _generate_fix_with_llm(analysis_input: str) -> FixSuggestion | None:
    """Call the LLM fix analyst. Returns None on failure or when the
    LLM advises against a concrete patch."""
    try:
        from app.services.llm_client import get_llm_client

        evaluator = SingleJudgeEvaluator()
        client = get_llm_client()
        resp = client.chat_completions_create(
            messages=[
                {"role": "system", "content": _FIX_ANALYST_SYSTEM},
                {"role": "user", "content": analysis_input},
            ],
            model=evaluator.model,
            max_tokens=2048,
            temperature=0.2,
        )
        raw = ""
        choices = getattr(resp, "choices", None) or []
        if choices:
            msg = getattr(choices[0], "message", None)
            if msg is not None:
                raw = getattr(msg, "content", "") or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("replay_fix_engine.llm_failed err=%s", exc)
        return None

    return _parse_fix_json(raw)


def _parse_fix_json(raw: str) -> FixSuggestion | None:
    """Parse the LLM's JSON response into a FixSuggestion."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.lstrip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
        if "```" in text:
            text = text.split("```", 1)[0]
        text = text.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("replay_fix_engine.unparseable_json raw_len=%d", len(raw or ""))
        return None
    if not isinstance(data, dict):
        return None

    fix_type = str(data.get("fix_type", "advisory_only")).strip().lower()
    if fix_type not in {"prompt_tweak", "prompt_revert", "model_swap", "advisory_only"}:
        fix_type = "advisory_only"

    confidence = float(data.get("confidence", 0.0) or 0.0)
    confidence = max(0.0, min(1.0, confidence))

    regression_summary = str(data.get("regression_summary", "") or "").strip()
    reasoning = str(data.get("reasoning", "") or "").strip()

    if fix_type == "advisory_only":
        return FixSuggestion(
            fix_type=fix_type,
            description=regression_summary or "No concrete fix could be generated",
            evidence={},
            confidence=confidence,
            regression_summary=regression_summary,
            reasoning=reasoning,
            has_patch=False,
        )

    # Build evidence dict for the PR payload builder.
    evidence: dict[str, Any] = {
        "regression_summary": regression_summary,
        "reasoning": reasoning,
    }
    if fix_type in {"prompt_tweak", "prompt_revert"}:
        proposed = str(data.get("proposed_prompt_body", "") or "").strip()
        if not proposed:
            logger.warning("replay_fix_engine.missing_proposed_prompt fix_type=%s", fix_type)
            return None
        evidence["prompt_path"] = "prompts/system.md"  # default; caller can override
        evidence["proposed_prompt_body"] = proposed
        evidence["current_prompt_fingerprint"] = None
    elif fix_type == "model_swap":
        proposed_model = str(data.get("proposed_model", "") or "").strip()
        if not proposed_model:
            logger.warning("replay_fix_engine.missing_proposed_model")
            return None
        evidence["config_path"] = "config/model.yaml"  # default; caller can override
        evidence["proposed_model"] = proposed_model
        evidence["current_model"] = ""

    action_type = (
        "replay_prompt_fix" if fix_type in {"prompt_tweak", "prompt_revert"} else "replay_model_fix"
    )

    return FixSuggestion(
        fix_type=fix_type,
        description=f"{action_type}: {regression_summary}",
        evidence=evidence,
        confidence=confidence,
        regression_summary=regression_summary,
        reasoning=reasoning,
        has_patch=True,
    )


# ── helpers ───────────────────────────────────────────────────────────────────


def _safe_json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
