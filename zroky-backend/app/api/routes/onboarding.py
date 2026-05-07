import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.db.models import DiagnosisJob
from app.db.session import get_db_session
from app.observability.metrics import record_diagnosis_job
from app.schemas.dashboard import OnboardingTriggerRequest, OnboardingTriggerResponse
from app.services.privacy import mask_error_message, mask_payload
from app.worker.tasks import process_diagnosis

router = APIRouter(prefix="/v1/onboarding")
logger = logging.getLogger(__name__)


def _payload_text_field(payload: dict[str, Any], key: str) -> str | None:
    raw = payload.get(key)
    if not isinstance(raw, str):
        return None

    value = raw.strip()
    return value or None


def _build_synthetic_payload(category: str) -> dict:
    base_payload = {
        "source": "synthetic_onboarding",
        "provider": "synthetic",
        "model": "synthetic-v1",
        "call_type": "chat",
        "agent_name": "onboarding-agent",
        "user_id": "onboarding-user",
        "prompt_tokens": 120,
        "completion_tokens": 40,
        "total_tokens": 160,
        "cost_usd": 0.01,
        "latency_ms": 120,
    }

    if category == "TOKEN_OVERFLOW":
        base_payload.update(
            {
                "prompt_tokens": 4300,
                "completion_tokens": 0,
                "total_tokens": 4300,
                "model_limit_tokens": 4096,
                "system_prompt_tokens": 900,
                "user_message_tokens": 3400,
                "conversation_turns": 1,
            }
        )
    elif category == "RATE_LIMIT":
        base_payload.update(
            {
                "status_code": 429,
                "error_code": "rate_limit_exceeded",
                "provider_latency_trend_ms": {"p95": 2200, "p99": 4100},
            }
        )
    elif category == "AUTH_FAILURE":
        base_payload.update(
            {
                "status_code": 401,
                "error_code": "invalid_api_key",
            }
        )
    elif category == "LOOP_DETECTED":
        base_payload.update(
            {
                "prompt_fingerprint": "synthetic-loop-signature",
                "loop": {
                    "repeat_count": 6,
                    "window_seconds": 80,
                    "no_progress": True,
                    "tool_chain_repeat_cycles": 4,
                    "tool_window_seconds": 110,
                },
            }
        )
    elif category == "COST_SPIKE":
        base_payload.update(
            {
                "cost": {
                    "current_15m_spend_usd": 120.0,
                    "baseline_15m_spend_usd": 20.0,
                    "history_days": 14,
                    "history_calls": 1200,
                    "model_spend_coefficient": 1.1,
                }
            }
        )

    return base_payload


@router.post("/trigger-test-failure", response_model=OnboardingTriggerResponse)
def trigger_test_failure(
    body: OnboardingTriggerRequest,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> OnboardingTriggerResponse:
    diagnosis_id = f"diag_onboarding_{uuid4().hex[:12]}"
    payload = _build_synthetic_payload(body.category)
    agent_name = _payload_text_field(payload, "agent_name")
    prompt_fingerprint = _payload_text_field(payload, "prompt_fingerprint")

    payload = mask_payload(payload)
    job = DiagnosisJob(
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        status="queued",
        agent_name=agent_name,
        prompt_fingerprint=prompt_fingerprint,
        payload_json=json.dumps(payload, separators=(",", ":")),
    )
    db.add(job)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        record_diagnosis_job("already_exists")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Synthetic diagnosis already exists. Please retry.",
        )

    try:
        process_diagnosis.delay(tenant_id, diagnosis_id, payload)
    except Exception as exc:
        logger.exception("Failed to enqueue synthetic onboarding diagnosis")
        job.status = "enqueue_failed"
        job.error_message = mask_error_message(exc)
        db.add(job)
        db.commit()
        record_diagnosis_job("enqueue_failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Queue is unavailable. Please retry shortly.",
        ) from exc

    record_diagnosis_job("queued")
    return OnboardingTriggerResponse(
        diagnosis_id=diagnosis_id,
        status="queued",
        synthetic=True,
        message="Synthetic failure created. Open dashboard diagnosis card for fix guidance.",
    )
