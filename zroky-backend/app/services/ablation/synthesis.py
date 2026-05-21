"""LLM synthesis — converts axis confidence table into actionable narrative.

Fires ONE Claude Haiku call per ablation job (only when at least one axis
has confidence ≥ HIGH_CONF_THRESHOLD).  Returns structured JSON with:
  - root_cause_narrative  (2-3 sentence explanation for a human)
  - fix_suggestion        (specific, actionable next step)
  - fix_difficulty        easy | medium | hard
  - synthesis_confidence  0.0-1.0  (how certain the LLM is)

Uses the same OpenRouter client pattern as judge_engine.py.
Output is cached by axis_fingerprint in the job row to avoid
redundant calls on retries.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_SYNTHESIS_MODEL = "anthropic/claude-haiku-4"
HIGH_CONF_THRESHOLD = 0.50


@dataclass
class SynthesisResult:
    root_cause_narrative: str
    fix_suggestion: str
    fix_difficulty: str
    synthesis_confidence: float
    axis_fingerprint: str
    skipped: bool = False
    skip_reason: str = ""


_SYSTEM_PROMPT = """You are an expert AI reliability engineer who diagnoses root causes of LLM failures.

Given statistical evidence about which axis (variable) best explains a failure, produce a concise,
actionable root-cause analysis. Be specific: name the axis, cite the evidence numbers, and give
a concrete fix.  Do NOT be vague.  Do NOT hedge with "it might be" when evidence is strong.

Output ONLY valid JSON with these exact keys:
{
  "root_cause_narrative": "<2-3 sentences explaining the root cause with evidence numbers>",
  "fix_suggestion": "<specific action: e.g. 'Pin model to anthropic/claude-3-sonnet in this agent'>",
  "fix_difficulty": "easy|medium|hard",
  "synthesis_confidence": <float 0.0-1.0>
}"""


def synthesise_root_cause(
    *,
    determinism_class: str,
    agent_name: str | None,
    diagnosis_categories: list[str],
    scored_axes: list[dict],
    control_group_size: int,
) -> SynthesisResult:
    """Call Claude Haiku to synthesise a root-cause narrative.

    Parameters
    ----------
    determinism_class:     One of deterministic / stochastic / environmental / unknown.
    agent_name:            Name of the failing agent (for context).
    diagnosis_categories:  List of detector names that fired (e.g. HALLUCINATION_RISK).
    scored_axes:           List of dicts with keys axis_type, axis_label, confidence, evidence.
    control_group_size:    Number of control traces used.
    """
    top_axes = [a for a in scored_axes if a["confidence"] >= HIGH_CONF_THRESHOLD]
    fp = _fingerprint(scored_axes)

    if not top_axes:
        return SynthesisResult(
            root_cause_narrative="Insufficient statistical evidence to identify a specific root cause.",
            fix_suggestion="Collect more traces (at least 5 failures and 12 control successes) for this agent.",
            fix_difficulty="medium",
            synthesis_confidence=0.0,
            axis_fingerprint=fp,
            skipped=True,
            skip_reason="no_high_confidence_axes",
        )

    axis_table = "\n".join(
        f"  [{a['axis_type']}] {a['axis_label']}  confidence={a['confidence']:.2f}"
        for a in scored_axes[:6]
    )

    user_prompt = f"""Failure context:
  Agent:              {agent_name or 'unknown'}
  Determinism class:  {determinism_class}
  Detector(s) fired:  {', '.join(diagnosis_categories) or 'none'}
  Control group:      {control_group_size} similar successful traces

Axis analysis (sorted by confidence):
{axis_table}

Primary suspect axis: [{top_axes[0]['axis_type']}] {top_axes[0]['axis_label']}
  Evidence: {json.dumps(top_axes[0].get('evidence', {}), separators=(',', ':'))}

Synthesise the root cause."""

    settings = get_settings()
    try:
        client = OpenAI(
            base_url=_OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            default_headers={
                "HTTP-Referer": settings.FRONTEND_URL or "https://zroky.ai",
                "X-Title": settings.APP_NAME or "Zroky AI",
            },
        )
        response = client.chat.completions.create(
            model=_SYNTHESIS_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=512,
        )
        raw = response.choices[0].message.content or "{}"
        parsed = _parse_llm_json(raw)
        return SynthesisResult(
            root_cause_narrative=parsed.get("root_cause_narrative", "Parse error — see raw response."),
            fix_suggestion=parsed.get("fix_suggestion", "Review top axis evidence above."),
            fix_difficulty=_validate_difficulty(parsed.get("fix_difficulty")),
            synthesis_confidence=float(parsed.get("synthesis_confidence", 0.5)),
            axis_fingerprint=fp,
        )
    except Exception as exc:
        logger.warning("ablation synthesis error: %s", exc)
        top = top_axes[0]
        return SynthesisResult(
            root_cause_narrative=(
                f"Statistical analysis identified '{top['axis_type']}' as the top causal axis "
                f"(confidence {top['confidence']:.0%}). "
                f"Determinism class: {determinism_class}. "
                f"LLM narrative generation failed — see axis evidence for details."
            ),
            fix_suggestion=(
                f"Investigate the '{top['axis_type']}' axis: {top['axis_label']}."
            ),
            fix_difficulty="medium",
            synthesis_confidence=float(top["confidence"]) * 0.7,
            axis_fingerprint=fp,
        )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _parse_llm_json(raw: str) -> dict:
    text = raw.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON object
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return {}


def _validate_difficulty(value) -> str:
    if value in ("easy", "medium", "hard"):
        return value
    return "medium"


def _fingerprint(scored_axes: list[dict]) -> str:
    key = json.dumps(
        [(a["axis_type"], round(a["confidence"], 2)) for a in scored_axes],
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(key.encode()).hexdigest()[:16]
