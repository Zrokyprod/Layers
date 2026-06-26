import json
import logging
import os
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes._internal.ingest_payload import (
    NON_TERMINAL_JOB_STATUSES,
    _build_call_record,
    _mark_cost_degraded,
    _payload_from_ingest_event,
    _persist_inline_outcome,
    _project_pii_patterns,
    _resolve_idempotency_key,
)
from app.core.config import get_settings
from app.db.models import Call, DiagnosisJob, ProjectAlert
from app.observability.metrics import record_diagnosis_job
from app.schemas.ingest import IngestBatchRequest, IngestBatchResponse
from app.services.billing_metering import increment_event_count
from app.services.billing_quota import check_quota
from app.services.cost_buckets import enrich_payload_with_cost_buckets
from app.services.alerts import auto_send_pending_alerts_to_slack, reset_slack_delivery_for_new_occurrence
from app.services.ingest_protection import IngestRateLimitDecision, evaluate_ingest_rate_limit
from app.services.privacy import mask_error_message, mask_payload
from app.services.redis_client import get_redis_client
from app.services.release_identity import resolve_release_identity
from app.services.trace_graph import upsert_trace_graph_for_call
from app.worker.tasks import process_diagnosis

logger = logging.getLogger(__name__)

def _find_existing_call(
    *,
    db: Session,
    tenant_id: str,
    event_id: str,
    call_id: str,
) -> Call | None:
    return db.execute(
        select(Call).where(
            Call.project_id == tenant_id,
            or_(Call.event_id == event_id, Call.id == call_id),
        ).limit(1)
    ).scalar_one_or_none()


def _find_job_for_call(*, db: Session, tenant_id: str, call: Call) -> DiagnosisJob | None:
    job = db.execute(
        select(DiagnosisJob).where(
            DiagnosisJob.tenant_id == tenant_id,
            DiagnosisJob.call_id == call.id,
        )
    ).scalar_one_or_none()
    if job is not None:
        return job
    return db.execute(
        select(DiagnosisJob).where(
            DiagnosisJob.tenant_id == tenant_id,
            DiagnosisJob.diagnosis_id == call.id,
        )
    ).scalar_one_or_none()


def _enqueue_diagnosis_job(job: DiagnosisJob) -> None:
    process_diagnosis.delay(job.tenant_id, job.diagnosis_id, None if job.call_id else {})


def _retry_enqueue_for_existing_call(*, db: Session, tenant_id: str, call: Call) -> str:
    job = _find_job_for_call(db=db, tenant_id=tenant_id, call=call)
    if job is None:
        return "skipped"

    if str(job.status).strip().lower() not in NON_TERMINAL_JOB_STATUSES:
        return "skipped"

    try:
        _enqueue_diagnosis_job(job)
        job.error_message = None
        db.add(job)
        db.commit()
        record_diagnosis_job("queued")
        return "queued"
    except Exception as exc:
        logger.exception("Failed to enqueue existing ingest diagnosis task")
        job.error_message = mask_error_message(exc)
        db.add(job)
        db.commit()
        record_diagnosis_job("enqueue_failed")
        return "failed"


_REDIS_IDEM_PREFIX = "zroky:ingest:idem:"
_REDIS_IDEM_TTL = 86400  # 24 hours


def _extract_redis_idempotency_key(
    *,
    request: Request,
    event: dict,
    call_id: str,
    tenant_id: str,
) -> str:
    """Return the idempotency key to use for the Redis fast-path check.

    Priority: X-Idempotency-Key header → event_id / request_id → call_id.
    """
    return _build_redis_idempotency_key(
        event=event,
        call_id=call_id,
        tenant_id=tenant_id,
        header_key=request.headers.get("X-Idempotency-Key"),
    )


def _build_redis_idempotency_key(
    *,
    event: dict,
    call_id: str,
    tenant_id: str,
    header_key: str | None = None,
) -> str:
    """Return the Redis idempotency key for HTTP and trusted stream ingest."""
    event_key, _ = _resolve_idempotency_key(event=event, call_id=call_id)
    header_key = (header_key or "").strip()
    if header_key:
        return f"{tenant_id}:{header_key[:128]}:{event_key}"
    return f"{tenant_id}:{event_key}"


def _check_redis_idempotency(key: str) -> bool:
    """Return True when *key* is present in the Redis idempotency cache.

    Failure to reach Redis is treated as a cache miss (allow through) so
    the database remains the authoritative idempotency guard.
    """
    if _redis_idempotency_disabled_for_tests():
        return False
    rc = get_redis_client()
    if rc is None:
        return False
    try:
        return bool(rc.get(f"{_REDIS_IDEM_PREFIX}{key}"))
    except Exception:
        logger.debug("Redis idempotency check failed; allowing through", exc_info=True)
        return False


def _set_redis_idempotency(key: str) -> None:
    """Record *key* in the Redis idempotency cache with a 24-hour TTL."""
    if _redis_idempotency_disabled_for_tests():
        return
    rc = get_redis_client()
    if rc is None:
        return
    try:
        rc.set(f"{_REDIS_IDEM_PREFIX}{key}", "1", ex=_REDIS_IDEM_TTL)
    except Exception:
        logger.debug("Redis idempotency set failed; continuing", exc_info=True)


def _redis_idempotency_disabled_for_tests() -> bool:
    return os.getenv("TESTING", "").strip().lower() == "true"


def _upsert_backpressure_alert(
    *,
    db: Session,
    tenant_id: str,
    decision: IngestRateLimitDecision,
) -> None:
    evidence = {
        "reason": decision.reason,
        "request_count": decision.request_count,
        "soft_limit_rpm": decision.soft_limit_rpm,
        "burst_limit_rpm": decision.burst_limit_rpm,
        "retry_after_seconds": decision.retry_after_seconds,
    }
    alert_query = select(ProjectAlert).where(
        ProjectAlert.tenant_id == tenant_id,
        ProjectAlert.diagnosis_id == "ingest-backpressure",
        ProjectAlert.category == "INGEST_BACKPRESSURE",
    )
    alert = db.execute(alert_query).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    title = "Ingest backpressure mode enabled due to sustained rate-limit breaches."
    if alert is None:
        alert = ProjectAlert(
            tenant_id=tenant_id,
            diagnosis_id="ingest-backpressure",
            category="INGEST_BACKPRESSURE",
            severity="high",
            status="OPEN",
            source="ingest_rate_limiter",
            title=title,
            evidence_json=json.dumps(evidence, separators=(",", ":")),
        )
        db.add(alert)
    else:
        was_resolved = alert.status == "RESOLVED"
        alert.status = "OPEN"
        alert.resolved_at = None
        alert.updated_at = now
        alert.title = title
        alert.evidence_json = json.dumps(evidence, separators=(",", ":"))
        if was_resolved:
            reset_slack_delivery_for_new_occurrence(alert)
        db.add(alert)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to commit backpressure alert")
        raise

    try:
        auto_send_pending_alerts_to_slack(
            db,
            tenant_id=tenant_id,
            diagnosis_id="ingest-backpressure",
            categories=["INGEST_BACKPRESSURE"],
            agent_name="ingest_rate_limiter",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to record/send ingest backpressure Slack alert")


def process_ingest_batch_for_tenant(
    *,
    body: IngestBatchRequest,
    tenant_id: str,
    db: Session,
    idempotency_header: str | None = None,
    enforce_rate_limit: bool = True,
    enforce_quota: bool = True,
) -> IngestBatchResponse:
    """Persist a canonical ingest batch for HTTP routes and trusted workers."""
    if enforce_rate_limit:
        decision = evaluate_ingest_rate_limit(tenant_id)
        if not decision.allowed:
            if decision.backpressure_activated:
                try:
                    _upsert_backpressure_alert(db=db, tenant_id=tenant_id, decision=decision)
                except Exception:
                    logger.exception("Failed to upsert backpressure alert")

            detail = (
                "Ingest backpressure active for this project. Please retry after cooldown."
                if decision.backpressure_active
                else "Ingest rate limit exceeded for this project. Please retry shortly."
            )
            headers = {}
            if decision.retry_after_seconds is not None:
                headers["Retry-After"] = str(decision.retry_after_seconds)
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail, headers=headers)

    settings = get_settings()
    if enforce_quota and settings.BILLING_ENFORCE_QUOTA:
        quota = check_quota(db, tenant_id)
        if not quota.allowed:
            if quota.reason == "check_error":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "Billing quota metering is unavailable, so production ingest "
                        "is paused instead of silently bypassing paid-plan limits."
                    ),
                    headers={"X-Quota-Policy": "strict"},
                )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Monthly event quota exceeded: {quota.current_count:,} of "
                    f"{quota.plan_limit:,} calls used this month. "
                    "Upgrade your plan or contact support."
                ),
                headers={"X-Quota-Used": str(quota.current_count), "X-Quota-Limit": str(quota.plan_limit)},
            )

    accepted = 0
    queued = 0
    duplicates = 0
    enqueue_failed = 0
    metered = 0
    metering_failed = 0
    metering_warnings: list[str] = []
    custom_pii_patterns = _project_pii_patterns(db, tenant_id)

    for event in body.events:
        diagnosis_id = event.call_id.strip()
        event_payload = event.model_dump()
        idempotency_key = _build_redis_idempotency_key(
            event=event_payload,
            call_id=diagnosis_id,
            tenant_id=tenant_id,
            header_key=idempotency_header,
        )
        if _check_redis_idempotency(idempotency_key):
            duplicates += 1
            record_diagnosis_job("already_exists")
            continue

        event_id, event_id_source = _resolve_idempotency_key(event=event_payload, call_id=diagnosis_id)
        payload = _payload_from_ingest_event(event)
        payload["event_id"] = event_id
        payload["idempotency_key_source"] = event_id_source
        payload = mask_payload(payload, custom_patterns=custom_pii_patterns)

        existing_call = _find_existing_call(
            db=db,
            tenant_id=tenant_id,
            event_id=event_id,
            call_id=diagnosis_id,
        )
        if existing_call is not None:
            duplicates += 1
            record_diagnosis_job("already_exists")
            try:
                upsert_trace_graph_for_call(db=db, tenant_id=tenant_id, call=existing_call)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(
                    "Failed to backfill trace graph for duplicate ingest",
                    extra={"tenant_id": tenant_id, "call_id": existing_call.id},
                )
            retry_result = _retry_enqueue_for_existing_call(db=db, tenant_id=tenant_id, call=existing_call)
            if retry_result == "queued":
                queued += 1
            elif retry_result == "failed":
                enqueue_failed += 1
            continue

        try:
            payload = enrich_payload_with_cost_buckets(tenant_id=tenant_id, payload=payload)
        except Exception as exc:
            logger.exception("Cost enrichment failed; storing degraded cost confidence")
            payload = _mark_cost_degraded(payload, exc)

        call = _build_call_record(
            tenant_id=tenant_id,
            call_id=diagnosis_id,
            event_id=event_id,
            payload=payload,
            custom_patterns=custom_pii_patterns,
        )
        identity = resolve_release_identity(
            db,
            project_id=tenant_id,
            payload=payload,
            provider=call.provider,
            model=call.model,
            agent_name=call.agent_name,
            is_production=call.is_production,
        )
        call.environment_id = identity.environment_id
        call.agent_id = identity.agent_id
        call.agent_release_id = identity.agent_release_id
        job = DiagnosisJob(
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            call_id=call.id,
            status="pending",
            agent_name=event.agent_name,
            prompt_fingerprint=event.prompt_fingerprint,
            payload_json="{}",
        )
        db.add(call)
        db.add(job)
        upsert_trace_graph_for_call(db=db, tenant_id=tenant_id, call=call, payload=payload)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            duplicates += 1
            record_diagnosis_job("already_exists")
            existing_after_race = _find_existing_call(
                db=db,
                tenant_id=tenant_id,
                event_id=event_id,
                call_id=diagnosis_id,
            )
            if existing_after_race is not None:
                try:
                    upsert_trace_graph_for_call(db=db, tenant_id=tenant_id, call=existing_after_race)
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception(
                        "Failed to backfill trace graph after ingest idempotency race",
                        extra={"tenant_id": tenant_id, "call_id": existing_after_race.id},
                    )
            retry_result = (
                _retry_enqueue_for_existing_call(
                    db=db,
                    tenant_id=tenant_id,
                    call=existing_after_race,
                )
                if existing_after_race is not None
                else "failed"
            )
            if retry_result == "queued":
                queued += 1
            elif retry_result == "failed":
                enqueue_failed += 1
            continue

        _persist_inline_outcome(db=db, tenant_id=tenant_id, call_id=call.id, payload=payload)
        accepted += 1

        try:
            _enqueue_diagnosis_job(job)
            job.status = "queued"
            db.add(job)
            db.commit()
            queued += 1
            record_diagnosis_job("queued")
            _set_redis_idempotency(idempotency_key)
        except Exception as exc:
            logger.exception("Failed to enqueue ingest diagnosis task")
            job.error_message = mask_error_message(exc)
            db.add(job)
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Failed to commit job error status")
            enqueue_failed += 1
            record_diagnosis_job("enqueue_failed")

        if increment_event_count(db, tenant_id):
            metered += 1
        else:
            metering_failed += 1
            if "event_counter_increment_failed" not in metering_warnings:
                metering_warnings.append("event_counter_increment_failed")

    return IngestBatchResponse(
        accepted=accepted,
        queued=queued,
        duplicates=duplicates,
        enqueue_failed=enqueue_failed,
        metered=metered,
        metering_failed=metering_failed,
        metering_warnings=metering_warnings,
    )
