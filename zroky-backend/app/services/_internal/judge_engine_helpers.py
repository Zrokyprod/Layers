import json
from typing import Any, Mapping, Optional

from app.services._internal.judge_engine_types import VALID_VERDICTS, VERDICT_INCONCLUSIVE, Verdict

_SYSTEM_PROMPT = (
    "You are a quality-assurance judge for AI agent outputs. "
    "Compare the actual output against the expected output and any context. "
    'Respond ONLY with valid JSON of shape {"verdict":"pass"|"fail"|"inconclusive",'
    '"confidence":0.0-1.0,"reason":"<one sentence>"}. '
    'Use "pass" when the actual output is semantically equivalent to the expected. '
    'Use "fail" when it is materially wrong, missing, or hallucinated. '
    'Use "inconclusive" only if you cannot determine equivalence.'
)


def _build_user_prompt(
    *,
    actual: str,
    expected: str,
    context: Mapping[str, Any] | None,
) -> str:
    """Compose the user-side prompt for a judge call.

    Caps each field at a generous length so we never blow the context
    window even with very large agent responses. The cap is intentionally
    larger than the shadow judge's 800 chars because replay traces can
    legitimately be longer.
    """
    parts: list[str] = []
    parts.append(f"expected:\n{(expected or '')[:4000]}")
    parts.append(f"actual:\n{(actual or '')[:4000]}")
    if context:
        try:
            ctx_json = json.dumps(context, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            ctx_json = str(context)
        parts.append(f"context:\n{ctx_json[:2000]}")
    return "\n\n".join(parts)


def _parse_verdict_json(raw: str) -> tuple[str, float, str]:
    """Parse the judge's JSON response into (verdict, confidence, reason).

    Tolerant: strips ```json fences, falls back to inconclusive on any
    parse failure so the caller never sees an exception from the engine
    itself (LLMs lie about JSON).
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        # Strip first fence + optional `json` tag, then last fence.
        text = text.lstrip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
        if "```" in text:
            text = text.split("```", 1)[0]
        text = text.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return VERDICT_INCONCLUSIVE, 0.0, "judge_output_unparseable"
    if not isinstance(data, dict):
        return VERDICT_INCONCLUSIVE, 0.0, "judge_output_not_object"
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in VALID_VERDICTS:
        verdict = VERDICT_INCONCLUSIVE
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    reason = str(data.get("reason", "") or "").strip()
    return verdict, confidence, reason


# ── evaluators ─────────────────────────────────────────────────────────────



_MULTIDIM_DIMENSIONS: tuple[str, ...] = (
    "accuracy",
    "faithfulness",
    "relevance",
    "coherence",
)

_REFREE_DIMENSIONS: tuple[str, ...] = (
    "relevance",
    "coherence",
    "groundedness",
    "completeness",
)

_MULTIDIM_SYSTEM_PROMPT = (
    "You are a multi-dimensional quality-assurance judge for AI agent outputs. "
    "Compare the actual output against the expected output and any context provided. "
    "Score four dimensions on a 0.0-1.0 scale: "
    "accuracy (semantic match with expected), "
    "faithfulness (no facts added beyond expected/context), "
    "relevance (addresses the question in context), "
    "coherence (internally consistent and logically sound). "
    'Respond ONLY with valid JSON: '
    '{"verdict":"pass"|"fail"|"inconclusive","confidence":0.0-1.0,"reason":"<one sentence>",'
    '"dimensions":{"accuracy":{"score":0.0-1.0,"reason":"<one sentence>"},'
    '"faithfulness":{"score":0.0-1.0,"reason":"<one sentence>"},'
    '"relevance":{"score":0.0-1.0,"reason":"<one sentence>"},'
    '"coherence":{"score":0.0-1.0,"reason":"<one sentence>"}}}. '
    'Use "pass" when mean dimension score >= 0.7 and no dimension is below 0.4. '
    'Use "fail" when mean dimension score < 0.5 or any dimension is below 0.25. '
    'Use "inconclusive" otherwise.'
)

_REFREE_SYSTEM_PROMPT = (
    "You are a reference-free quality judge for AI agent outputs. "
    "You have NO golden/expected output. Judge the output given only the input "
    "question/task (in context) and the output itself. "
    "Score four dimensions on a 0.0-1.0 scale: "
    "relevance (addresses the input question), "
    "coherence (internally consistent and logically sound), "
    "groundedness (avoids unverifiable confident claims; 1.0=grounded/hedged, "
    "0.0=hallucination risk), "
    "completeness (sufficiently answers the question). "
    'Respond ONLY with valid JSON: '
    '{"verdict":"pass"|"fail"|"inconclusive","confidence":0.0-1.0,"reason":"<one sentence>",'
    '"dimensions":{"relevance":{"score":0.0-1.0,"reason":"<one sentence>"},'
    '"coherence":{"score":0.0-1.0,"reason":"<one sentence>"},'
    '"groundedness":{"score":0.0-1.0,"reason":"<one sentence>"},'
    '"completeness":{"score":0.0-1.0,"reason":"<one sentence>"}}}. '
    'Use "pass" when mean dimension score >= 0.7 and groundedness >= 0.6. '
    'Use "fail" when mean dimension score < 0.5 or groundedness < 0.35. '
    'Use "inconclusive" otherwise.'
)


def _build_refree_user_prompt(
    *,
    actual: str,
    context: Mapping[str, Any] | None,
) -> str:
    """Compose the user-side prompt for a reference-free judge call.

    Pulls ``original_prompt`` from context (populated by replay_executor's
    ``_build_judge_context``) as the "input" the agent was answering.
    Remaining context keys are forwarded as supplementary data.
    """
    parts: list[str] = []
    ctx = dict(context or {})
    input_text = str(ctx.pop("original_prompt", "") or "").strip()
    if input_text:
        parts.append(f"input:\n{input_text[:4000]}")
    parts.append(f"actual:\n{(actual or '')[:4000]}")
    if ctx:
        try:
            ctx_json = json.dumps(ctx, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            ctx_json = str(ctx)
        parts.append(f"context:\n{ctx_json[:2000]}")
    return "\n\n".join(parts)


def _parse_multidim_json(
    raw: str,
    expected_dims: tuple[str, ...],
) -> tuple[str, float, str, dict[str, dict[str, Any]], "float | None"]:
    """Parse a multi-dimensional judge JSON response.

    Returns ``(verdict, confidence, reason, dimensions, overall_score)``.
    - ``dimensions`` maps dim-name → ``{"score": float, "reason": str}``.
      Missing dimension keys are filled with ``{"score": 0.0, "reason": "missing"}``.
    - ``overall_score`` is the unweighted mean of all dimension scores, or
      ``None`` when no valid dimension scores are present.
    - On any parse failure returns an inconclusive verdict with empty
      dimensions so callers never see an exception.
    """
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
        return VERDICT_INCONCLUSIVE, 0.0, "judge_output_unparseable", {}, None

    if not isinstance(data, dict):
        return VERDICT_INCONCLUSIVE, 0.0, "judge_output_not_object", {}, None

    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in VALID_VERDICTS:
        verdict = VERDICT_INCONCLUSIVE
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    reason = str(data.get("reason", "") or "").strip()

    raw_dims = data.get("dimensions")
    dimensions: dict[str, dict[str, Any]] = {}
    if isinstance(raw_dims, dict):
        for dim in expected_dims:
            raw_dim = raw_dims.get(dim)
            if isinstance(raw_dim, dict):
                try:
                    score = float(raw_dim.get("score", 0.0))
                    score = max(0.0, min(1.0, score))
                except (TypeError, ValueError):
                    score = 0.0
                dim_reason = str(raw_dim.get("reason", "") or "").strip()
                dimensions[dim] = {"score": score, "reason": dim_reason}
            else:
                dimensions[dim] = {"score": 0.0, "reason": "missing"}
    else:
        for dim in expected_dims:
            dimensions[dim] = {"score": 0.0, "reason": "missing"}

    scores = [d["score"] for d in dimensions.values()]
    overall_score: Any = (sum(scores) / len(scores)) if scores else None

    return verdict, confidence, reason, dimensions, overall_score


# ── helper accessors for Verdict.metadata["dimensions"] ──────────────────


def get_dimensions(verdict: Verdict) -> dict[str, dict[str, Any]]:
    """Extract the dimensions dict from a multi-dim Verdict's metadata.

    Returns ``{}`` when the verdict carries no dimension data (e.g. it came
    from a single/ensemble/stub evaluator).
    """
    meta = verdict.metadata
    if not isinstance(meta, dict):
        return {}
    dims = meta.get("dimensions")
    return dims if isinstance(dims, dict) else {}


def get_overall_score(verdict: Verdict) -> Optional[float]:
    """Return the pre-computed overall dimension score, or None."""
    meta = verdict.metadata
    if not isinstance(meta, dict):
        return None
    val = meta.get("overall_score")
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def has_dimensions(verdict: Verdict) -> bool:
    """True when the verdict carries multi-dimensional score data."""
    return bool(get_dimensions(verdict))


