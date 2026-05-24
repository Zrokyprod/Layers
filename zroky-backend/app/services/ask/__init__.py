"""Ask Zroky — natural-language Q&A over the user's own AI agent telemetry.

Public surface:
    answer_question(db, *, project_id, question, context)
        -> AskAnswer with narrative, evidence, suggested actions, confidence.

Internally composes:
    intent_router.classify_intent(question)
    data_retriever.collect_evidence(db, project_id, intent, context)
    answer_synthesizer.synthesize(question, intent, evidence)
"""
from __future__ import annotations

from .intent_router import Intent, classify_intent
from .data_retriever import EvidenceBundle, collect_evidence
from .answer_synthesizer import AskAnswer, synthesize

__all__ = [
    "Intent",
    "classify_intent",
    "EvidenceBundle",
    "collect_evidence",
    "AskAnswer",
    "synthesize",
    "answer_question",
]


def answer_question(
    db,
    *,
    project_id: str,
    question: str,
    context: dict | None = None,
) -> "AskAnswer":
    """Single entry point used by the /v1/ask route."""
    intent = classify_intent(question)
    evidence = collect_evidence(
        db,
        project_id=project_id,
        intent=intent,
        question=question,
        context=context or {},
    )
    return synthesize(question=question, intent=intent, evidence=evidence)
