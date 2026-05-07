"""FastAPI routes for the Zroky zero-hallucination assistant."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id
from app.db.session import get_db_session
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse
from app.services.assistant_engine import clear_history, run_assistant

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=AssistantChatResponse)
def chat(
    body: AssistantChatRequest,
    db: Session = Depends(get_db_session),
    project_id: str = Depends(require_tenant_id),
) -> AssistantChatResponse:
    """
    Send a message to the Zroky assistant.

    The assistant answers ONLY questions about this project's AI monitoring data
    (costs, errors, loops, alerts, diagnoses, fixes). All answers are grounded in
    real DB data fetched via tools — no hallucination.

    - `session_id`: caller-generated string (e.g. UUID). Scopes conversation memory.
      Use the same session_id across turns to maintain context.
    - `message`: the user's question (max 2000 chars).
    """
    try:
        return run_assistant(
            message=body.message,
            session_id=body.session_id,
            project_id=project_id,
            db=db,
        )
    except Exception as exc:
        logger.error("Assistant error project=%s: %s", project_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Assistant encountered an unexpected error.",
        ) from exc


@router.delete("/chat/{session_id}", status_code=status.HTTP_200_OK)
def clear_chat(
    session_id: str,
    project_id: str = Depends(require_tenant_id),
) -> dict[str, bool]:
    """Clear conversation history for a session. Safe to call anytime."""
    clear_history(project_id, session_id)
    return {"cleared": True}
