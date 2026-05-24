"""Calls Claude Haiku via OpenRouter to turn evidence into a plain-English answer.

Mirrors the contract used by `services.ablation.synthesis` so we share the
same OpenRouter wiring and JSON-parsing helpers, just specialized for
free-form Q&A instead of axis tables.

Output schema is stable so the dashboard can render it the same way every
time.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from openai import OpenAI

from app.core.config import get_settings

from .data_retriever import EvidenceBundle, EvidenceLink
from .intent_router import Intent

logger = logging.getLogger(__name__)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_MODEL = "anthropic/claude-haiku-4"
_MAX_TOKENS = 600


@dataclass
class AskAnswer:
    answer: str
    suggested_actions: list[str]
    confidence: float
    intent: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    used_llm: bool = True
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_SYSTEM_PROMPT = """You are Zroky, the AI reliability copilot for developers running AI agents in production.

You answer questions strictly from the evidence provided — never invent numbers, call IDs, or
agent names. If the evidence is empty or insufficient, say so plainly and suggest the next
diagnostic step the developer should take.

Rules:
1. Be concrete. Use exact numbers from the evidence (cost, latency, counts).
2. Use plain English. Avoid jargon like "p95", "fingerprint", "ablation" unless the user used
   that word first.
3. Stay under 4 sentences for the answer.
4. Suggested actions must be imperative and immediately actionable
   (e.g. "Open call abc-123 to see the prompt", "Switch to claude-3-haiku for the checkout agent").
5. Output ONLY valid JSON with these exact keys:
   {
     "answer": "<2-4 sentences in plain English>",
     "suggested_actions": ["<action 1>", "<action 2>"],
     "confidence": <float 0.0-1.0>
   }
"""


def synthesize(
    *, question: str, intent: Intent, evidence: EvidenceBundle
) -> AskAnswer:
    """Call Haiku to produce the user-facing answer."""
    user_prompt = _build_user_prompt(question, evidence)

    settings = get_settings()
    api_key = settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY
    if not api_key:
        return _fallback(intent, evidence, reason="no_api_key")

    try:
        client = OpenAI(
            base_url=_OPENROUTER_BASE_URL,
            api_key=api_key,
            default_headers={
                "HTTP-Referer": settings.FRONTEND_URL or "https://zroky.ai",
                "X-Title": settings.APP_NAME or "Zroky AI",
            },
        )
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=_MAX_TOKENS,
        )
        raw = response.choices[0].message.content or "{}"
        parsed = _parse_json(raw)
        answer_text = str(parsed.get("answer") or "").strip()
        if not answer_text:
            return _fallback(intent, evidence, reason="empty_llm_answer")
        actions = parsed.get("suggested_actions") or []
        if not isinstance(actions, list):
            actions = [str(actions)]
        actions = [str(a).strip() for a in actions if str(a).strip()][:5]
        confidence = _clamp_confidence(parsed.get("confidence"))
        return AskAnswer(
            answer=answer_text,
            suggested_actions=actions,
            confidence=confidence,
            intent=intent.name,
            evidence=[_link_to_dict(link) for link in evidence.links],
            used_llm=True,
        )
    except Exception as exc:  # noqa: BLE001 — broad on purpose, fallback covers
        logger.warning("ask zroky synthesis failed: %s", exc)
        return _fallback(intent, evidence, reason=f"llm_error:{type(exc).__name__}")


# ── prompt building ─────────────────────────────────────────────────────────


def _build_user_prompt(question: str, evidence: EvidenceBundle) -> str:
    summary_block = (
        json.dumps(evidence.summary, default=str, separators=(",", ":"))
        if evidence.summary
        else "{}"
    )
    rows_block = (
        json.dumps(evidence.rows, default=str, separators=(",", ":"))
        if evidence.rows
        else "[]"
    )
    return (
        f"User question: {question}\n\n"
        f"Detected intent: {evidence.intent} "
        f"(window: last {evidence.window_days} days)\n\n"
        f"Summary metrics:\n{summary_block}\n\n"
        f"Top evidence rows (max 8):\n{rows_block}\n\n"
        "Answer the user's question in plain English using only this evidence. "
        "If evidence is empty, explicitly say there is not enough data yet and "
        "suggest installing the SDK or generating traffic."
    )


# ── fallback (no LLM available) ─────────────────────────────────────────────


def _fallback(intent: Intent, evidence: EvidenceBundle, *, reason: str) -> AskAnswer:
    if not evidence.rows and not evidence.summary:
        return AskAnswer(
            answer=(
                "I do not have enough data yet to answer that. Make sure the Zroky SDK "
                "is installed in your agent and that traffic has reached the dashboard."
            ),
            suggested_actions=[
                "Install the Zroky SDK in your agent",
                "Open Settings → API Keys to copy your project key",
            ],
            confidence=0.2,
            intent=intent.name,
            evidence=[],
            used_llm=False,
            fallback_reason=reason,
        )

    summary = evidence.summary
    pieces: list[str] = []
    if "total_calls" in summary:
        pieces.append(
            f"In the last {evidence.window_days} day(s) your project recorded "
            f"{summary['total_calls']} calls "
            f"with {summary.get('error_count', 0)} errors "
            f"(${summary.get('total_cost_usd', 0):.4f} spent)."
        )
    if intent.name == "cost" and evidence.rows:
        top = evidence.rows[0]
        pieces.append(
            f"The most expensive call was ${top.get('cost_usd', 0):.4f} on "
            f"{top.get('agent_name') or top.get('model') or 'an unknown agent'}."
        )
    if intent.name == "latency" and evidence.rows:
        top = evidence.rows[0]
        pieces.append(
            f"The slowest call took {top.get('latency_ms', 0):.0f} ms on "
            f"{top.get('agent_name') or top.get('model') or 'an unknown agent'}."
        )
    if intent.name == "failure" and evidence.rows:
        pieces.append(
            f"Top open anomaly: {evidence.rows[0].get('failure_code')} occurred "
            f"{evidence.rows[0].get('occurrence_count')} times."
        )

    answer = " ".join(pieces) if pieces else (
        "I have raw evidence but the language model is unavailable to summarize it. "
        "Open the listed evidence links for details."
    )
    return AskAnswer(
        answer=answer,
        suggested_actions=["Open the linked evidence to investigate further."],
        confidence=0.5,
        intent=intent.name,
        evidence=[_link_to_dict(link) for link in evidence.links],
        used_llm=False,
        fallback_reason=reason,
    )


# ── helpers ─────────────────────────────────────────────────────────────────


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                return {}
    return {}


def _clamp_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5
    if confidence < 0.0:
        return 0.0
    if confidence > 1.0:
        return 1.0
    return confidence


def _link_to_dict(link: EvidenceLink) -> dict[str, Any]:
    return {"kind": link.kind, "id": link.id, "label": link.label, "href": link.href}
