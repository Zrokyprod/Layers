"""Ask Zroky — natural-language Q&A endpoint.

POST /v1/ask
    body: { question: str, context?: { call_id?: str, anomaly_id?: str } }
    returns:
        {
            answer: str,
            suggested_actions: [str, ...],
            confidence: float,
            intent: str,
            evidence: [{ kind, id, label, href }, ...],
            used_llm: bool,
            fallback_reason: str | null,
        }

Tenant scoping is enforced via `require_tenant_id`; all data retrieval
filters by project_id so cross-tenant leakage is impossible.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.services.ask import answer_question

router = APIRouter(prefix="/v1/ask")
logger = logging.getLogger(__name__)

_MAX_QUESTION_LENGTH = 1000


class AskContext(BaseModel):
    call_id: str | None = Field(default=None, max_length=64)
    anomaly_id: str | None = Field(default=None, max_length=64)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=_MAX_QUESTION_LENGTH)
    context: AskContext | None = None


class AskEvidence(BaseModel):
    kind: str
    id: str
    label: str
    href: str


class AskResponse(BaseModel):
    answer: str
    suggested_actions: list[str]
    confidence: float
    intent: str
    evidence: list[AskEvidence]
    used_llm: bool
    fallback_reason: str | None = None


@router.post("", response_model=AskResponse)
@limiter.limit("30/minute")
def ask_zroky(
    request: Request,
    body: AskRequest,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> AskResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question must not be empty.",
        )

    context = body.context.model_dump(exclude_none=True) if body.context else {}

    try:
        result = answer_question(
            db,
            project_id=tenant_id,
            question=question,
            context=context,
        )
    except Exception:
        logger.exception("ask zroky orchestration failed for tenant=%s", tenant_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to answer question. Please retry.",
        )

    return AskResponse(**result.to_dict())


# ── Ask feedback ──────────────────────────────────────────────────────────────


class AskFeedbackRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=_MAX_QUESTION_LENGTH)
    answer: str = Field(..., min_length=1, max_length=5000)
    helpful: bool
    intent: str = Field(default="", max_length=64)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class AskFeedbackResponse(BaseModel):
    accepted: bool


@router.post("/feedback", response_model=AskFeedbackResponse)
@limiter.limit("60/minute")
def submit_ask_feedback(
    request: Request,
    body: AskFeedbackRequest,
    tenant_id: str = Depends(require_tenant_id),
) -> AskFeedbackResponse:
    """Record thumbs-up / thumbs-down signal for an Ask Zroky answer."""
    logger.info(
        "ask_feedback tenant=%s helpful=%s intent=%s confidence=%.2f",
        tenant_id,
        body.helpful,
        body.intent,
        body.confidence,
    )
    return AskFeedbackResponse(accepted=True)
