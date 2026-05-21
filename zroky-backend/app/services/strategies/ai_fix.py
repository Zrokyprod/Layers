"""
LLM-powered fix generation strategy.
Falls back to None on any error so callers use template strategies.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.services.privacy import mask_value
from app.services._fix_utils import _clean_snippet

logger = logging.getLogger(__name__)

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

FixTuple = tuple[
    str, str, str, str,
    list[dict[str, str]], list[str], list[str], list[str],
    float,
]


def _ai_fix(request: Any, db: Any | None = None) -> FixTuple | None:
    """Try LLM-powered fix generation.

    Returns a 9-tuple identical in shape to the template strategy functions,
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
