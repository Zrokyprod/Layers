import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.db.models import Call, DiagnosisJob, ProjectAlert, ProjectDashboardConfig
from app.db.session import get_db_session
from app.observability.metrics import record_diagnosis_job
from app.schemas.ingest import IngestBatchRequest, IngestBatchResponse
from app.services.currency import BASE_CURRENCY, TOKEN_UNIT, resolve_ingest_exchange_rate
from app.services.cost_buckets import enrich_payload_with_cost_buckets
from app.services.ingest_protection import IngestRateLimitDecision, evaluate_ingest_rate_limit
from app.services.loop_signals import output_signal, summarize_tool_lifecycle, normalize_retry_metadata
from app.core.limiter import limiter
from app.services.privacy import mask_error_message, mask_metadata, mask_payload
from app.services.redis_client import get_redis_client
from app.worker.tasks import process_diagnosis

# Try to import redis for idempotency cache; fall back gracefully if unavailable
try:
    import redis
except ImportError:
    redis = None  # type: ignore[misc]

router = APIRouter(prefix="/v1")
logger = logging.getLogger(__name__)

SUCCESS_STATUSES = {"completed", "complete", "success", "succeeded", "ok", "done"}
TIMEOUT_STATUSES = {"timeout", "timed_out", "deadline_exceeded"}
ERROR_STATUSES = {
    "failed",
    "failure",
    "error",
    "errored",
    "dead_lettered",
    "enqueue_failed",
    "cancelled",
    "canceled",
    "aborted",
    "incomplete",
    "partial",
    "partial_response",
    "partial_success",
}
TIMEOUT_ERROR_MARKERS = {
    "timeout",
    "timed_out",
    "deadline",
    "deadline_exceeded",
    "read_timeout",
    "request_timeout",
    "gateway_timeout",
    "context_deadline_exceeded",
}
NON_TERMINAL_JOB_STATUSES = {"pending", "queued", "retrying", "enqueue_failed"}

_TEST_PROVIDER_MARKERS = frozenset(("mock", "test", "fake", "dummy", "stub"))
_NON_PRODUCTION_ENVIRONMENTS = frozenset(("test", "testing", "dev", "development"))


def _is_production_event(payload: dict) -> bool:
    """Return False for any payload flagged as synthetic, test, or non-production."""
    if payload.get("is_synthetic"):
        return False
    if payload.get("is_production") is False:
        return False
    env = str(payload.get("environment") or "").lower().strip()
    if env in _NON_PRODUCTION_ENVIRONMENTS:
        return False
    provider = str(payload.get("provider") or "").lower()
    return not any(marker in provider for marker in _TEST_PROVIDER_MARKERS)


def _build_payload_from_event(event: dict) -> dict:
    prompt_tokens = int(event.get("prompt_tokens", 0) or 0)
    completion_tokens = int(event.get("completion_tokens", 0) or 0)
    reasoning_tokens = int(event.get("reasoning_tokens", 0) or 0)
    cache_creation_tokens = int(event.get("cache_creation_tokens", 0) or 0)
    cache_read_tokens = int(event.get("cache_read_tokens", 0) or 0)

    total_tokens = prompt_tokens + completion_tokens + reasoning_tokens

    payload = {
        "source": "sdk_ingest",
        "call_id": event.get("call_id"),
        "event_id": event.get("event_id"),
        "request_id": event.get("request_id"),
        "provider": event.get("provider"),
        "model": event.get("model"),
        "call_type": event.get("call_type"),
        "status": event.get("status"),
        "latency_ms": event.get("latency_ms"),
        "prompt_tokens": prompt_tokens,
        "estimated_prompt_tokens": event.get("estimated_prompt_tokens"),
        "model_context_limit": event.get("model_context_limit"),
        "model_context_limit_source": event.get("model_context_limit_source"),
        "model_context_limit_source_detail": event.get(
            "model_context_limit_source_detail"
        ),
        "model_context_limit_confidence": event.get("model_context_limit_confidence"),
        "model_context_limit_catalog_version": event.get(
            "model_context_limit_catalog_version"
        ),
        "model_context_limit_catalog_updated_at": event.get(
            "model_context_limit_catalog_updated_at"
        ),
        "model_context_limit_catalog_stale": event.get(
            "model_context_limit_catalog_stale"
        ),
        "model_context_limit_catalog_stale_after_days": event.get(
            "model_context_limit_catalog_stale_after_days"
        ),
        "token_estimator_version": event.get("token_estimator_version"),
        "token_rules_version": event.get("token_rules_version"),
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "cache_read_tokens": cache_read_tokens,
        "estimated_cost_usd": event.get("estimated_cost_usd"),
        "actual_cost_usd": event.get("actual_cost_usd"),
        "budget_remaining_usd": event.get("budget_remaining_usd"),
        "budget_action_taken": event.get("budget_action_taken"),
        "loop_action_taken": event.get("loop_action_taken"),
        "loop_call_count": int(event.get("loop_call_count", 0) or 0),
        "loop_cumulative_cost_usd": event.get("loop_cumulative_cost_usd"),
        "exchange_rate_usd_to_inr": event.get("exchange_rate_usd_to_inr"),
        "exchange_rate_timestamp": event.get("exchange_rate_timestamp"),
        "exchange_rate_source": event.get("exchange_rate_source"),
        "total_tokens": total_tokens,
        "normalized_output": event.get("normalized_output"),
        "output_content": event.get("output_content"),
        "output_fingerprint": event.get("output_fingerprint"),
        "tool_definitions": event.get("tool_definitions"),
        "tool_calls_made": event.get("tool_calls_made"),
        "tool_lifecycle_summary": event.get("tool_lifecycle_summary"),
        "retry_metadata": event.get("retry_metadata"),
        "cache_hit": bool(event.get("cache_hit")),
        "timeout_triggered": bool(event.get("timeout_triggered")),
        "resolved_model": event.get("resolved_model"),
        "fallback_chain": event.get("fallback_chain")
        if isinstance(event.get("fallback_chain"), list)
        else None,
        "fallback_attempts": int(event.get("fallback_attempts", 0) or 0),
        "circuit_open_models": event.get("circuit_open_models")
        if isinstance(event.get("circuit_open_models"), list)
        else None,
        "trace_id": event.get("trace_id"),
        "parent_call_id": event.get("parent_call_id"),
        "agent_name": event.get("agent_name"),
        "prompt_fingerprint": event.get("prompt_fingerprint"),
        "user_id": event.get("user_id"),
        "is_synthetic": bool(event.get("is_synthetic")),
        "is_production": event.get("is_production"),
        "environment": event.get("environment"),
        "metadata": event.get("metadata") if isinstance(event.get("metadata"), dict) else None,
        "error_code": event.get("error_code"),
        "error_message": event.get("error_message"),
        "failure_reason": event.get("failure_reason")
        if isinstance(event.get("failure_reason"), dict)
        else None,
        "created_at": event.get("created_at"),
    }
    return payload


def _ensure_loop_signal_payload(payload: dict) -> dict:
    enriched = dict(payload)
    output_value = enriched.get("normalized_output") or enriched.get("output_content")
    if not enriched.get("output_fingerprint") and output_value:
        signal = output_signal(output_value)
        enriched["normalized_output"] = signal["normalized_output"]
        enriched["output_fingerprint"] = signal["output_fingerprint"]

    if not enriched.get("tool_lifecycle_summary"):
        tool_calls = enriched.get("tool_calls_made")
        if isinstance(tool_calls, list):
            enriched["tool_lifecycle_summary"] = summarize_tool_lifecycle(tool_calls)

    retry_metadata = normalize_retry_metadata(enriched.get("retry_metadata") or enriched.get("retry"))
    if retry_metadata is not None:
        enriched["retry_metadata"] = retry_metadata
    return enriched


def _project_pii_patterns(db: Session, tenant_id: str) -> list[str]:
    config = db.execute(
        select(ProjectDashboardConfig).where(ProjectDashboardConfig.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if config is None:
        return []
    try:
        parsed = json.loads(config.pii_custom_patterns_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]


def _normalize_call_status(
    *,
    status_value: str | None,
    error_code: str | None,
    error_message: str | None = None,
) -> str:
    status_text = (status_value or "").strip().lower()
    error_text = (error_code or "").strip().lower()
    message_text = (error_message or "").strip().lower()
    combined_error_text = f"{error_text} {message_text}".replace("-", "_")

    if status_text in TIMEOUT_STATUSES or any(marker in combined_error_text for marker in TIMEOUT_ERROR_MARKERS):
        return "timeout"
    if error_text or message_text or status_text in ERROR_STATUSES:
        return "error"
    if status_text in SUCCESS_STATUSES:
        return "success"
    return "unknown"


def _as_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _as_float_or_none(value: object) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _as_float(value: object) -> float:
    parsed = _as_float_or_none(value)
    return parsed if parsed is not None else 0.0


def _first_present(*values: object) -> object | None:
    for value in values:
        if value is not None:
            return value
    return None


def _as_bounded_text(value: object, *, max_length: int) -> str | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
    except Exception:
        return None
    return text[:max_length] if text else None


def _parse_created_at(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return datetime.fromtimestamp(float(candidate), tz=timezone.utc)
        except ValueError:
            pass
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    return None


def _build_call_metadata(payload: dict, *, custom_patterns: list[str] | None = None) -> dict:
    metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
    metadata.update(
        {
            "call_type": payload.get("call_type"),
            "trace_id": payload.get("trace_id"),
            "parent_call_id": payload.get("parent_call_id"),
            "agent_name": payload.get("agent_name"),
            "prompt_fingerprint": payload.get("prompt_fingerprint"),
            "user_id": payload.get("user_id"),
            "idempotency_key_source": payload.get("idempotency_key_source"),
            "is_synthetic": bool(payload.get("is_synthetic")),
            "is_production": payload.get("is_production"),
            "environment": payload.get("environment"),
        }
    )
    return mask_metadata(metadata, custom_patterns=custom_patterns)


def _pricing_timestamp(payload: dict) -> datetime | None:
    return _parse_created_at(payload.get("pricing_last_updated_at"))


def _pricing_source(payload: dict) -> str | None:
    cost = payload.get("cost") if isinstance(payload.get("cost"), dict) else {}
    per_call = cost.get("per_call_breakdown") if isinstance(cost.get("per_call_breakdown"), dict) else {}
    for value in (
        payload.get("pricing_source"),
        cost.get("pricing_source"),
        per_call.get("pricing_source"),
    ):
        if isinstance(value, str) and value.strip():
            normalized = value.strip()
            if normalized in {"official_provider", "cached_rate_card", "fallback_default"}:
                return normalized
    return None


def _confidence_reason(payload: dict) -> str | None:
    cost = payload.get("cost") if isinstance(payload.get("cost"), dict) else {}
    per_call = cost.get("per_call_breakdown") if isinstance(cost.get("per_call_breakdown"), dict) else {}
    for value in (
        payload.get("confidence_reason"),
        cost.get("confidence_reason"),
        per_call.get("confidence_reason"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()[:120]
    return None


def _resolve_idempotency_key(*, event: dict, call_id: str) -> tuple[str, str]:
    # Strict priority: SDK event_id > provider/client request_id > legacy call_id.
    for source in ("event_id", "request_id"):
        raw_value = event.get(source)
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if value:
            return value[:128], source

    fallback = call_id.strip() or "unknown"
    return fallback[:128], "call_id"


def _build_call_record(
    *,
    tenant_id: str,
    call_id: str,
    event_id: str,
    payload: dict,
    custom_patterns: list[str] | None = None,
) -> Call:
    payload = _ensure_loop_signal_payload(mask_payload(payload, custom_patterns=custom_patterns))
    status_value = str(payload.get("status") or "")
    error_code = payload.get("error_code")
    prompt_tokens = _as_int(payload.get("prompt_tokens"))
    completion_tokens = _as_int(payload.get("completion_tokens"))
    reasoning_tokens = _as_int(payload.get("reasoning_tokens"))
    total_tokens = _as_int(payload.get("total_tokens")) or (
        prompt_tokens + completion_tokens + reasoning_tokens
    )
    created_at = _parse_created_at(payload.get("created_at"))
    captured_at = created_at or datetime.now(timezone.utc)
    exchange_rate = resolve_ingest_exchange_rate(payload, captured_at=captured_at)

    call = Call(
        id=call_id,
        project_id=tenant_id,
        event_id=event_id,
        agent_name=_as_bounded_text(payload.get("agent_name"), max_length=255),
        user_id=_as_bounded_text(payload.get("user_id"), max_length=255),
        call_type=_as_bounded_text(payload.get("call_type"), max_length=32),
        provider=str(payload.get("provider") or "unknown").lower(),
        model=str(payload.get("model") or "unknown").lower(),
        status=_normalize_call_status(
            status_value=status_value,
            error_code=str(error_code) if error_code is not None else None,
            error_message=str(payload.get("error_message")) if payload.get("error_message") is not None else None,
        ),
        error_code=str(error_code) if error_code is not None else None,
        latency_ms=_as_float_or_none(payload.get("latency_ms")),
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
        cost_total=_as_float(
            _first_present(
                payload.get("total_cost_usd"),
                payload.get("actual_cost_usd"),
                payload.get("cost_usd"),
            )
        ),
        reasoning_cost_total=_as_float(payload.get("reasoning_cost_usd")),
        cache_savings_total=_as_float(payload.get("cache_savings_usd")),
        pricing_version=str(payload.get("pricing_version"))[:64] if payload.get("pricing_version") else None,
        pricing_source=_pricing_source(payload),
        pricing_last_updated_at=_pricing_timestamp(payload),
        cost_currency=BASE_CURRENCY,
        token_unit=TOKEN_UNIT,
        exchange_rate_usd_to_inr=exchange_rate["exchange_rate_usd_to_inr"],
        exchange_rate_timestamp=exchange_rate["exchange_rate_timestamp"],
        exchange_rate_source=exchange_rate["exchange_rate_source"],
        cost_confidence=str(payload.get("cost_confidence") or "degraded")[:32],
        confidence_reason=_confidence_reason(payload),
        output_fingerprint=str(payload.get("output_fingerprint"))[:64] if payload.get("output_fingerprint") else None,
        is_production=_is_production_event(payload),
        tool_lifecycle_summary_json=json.dumps(payload.get("tool_lifecycle_summary"), separators=(",", ":"))
        if payload.get("tool_lifecycle_summary") is not None
        else None,
        retry_metadata_json=json.dumps(payload.get("retry_metadata"), separators=(",", ":"))
        if payload.get("retry_metadata") is not None
        else None,
        payload_json=json.dumps(payload, separators=(",", ":")),
        metadata_json=json.dumps(
            _build_call_metadata(payload, custom_patterns=custom_patterns),
            separators=(",", ":"),
        ),
    )
    if created_at is not None:
        call.created_at = created_at
    return call


def _apply_enriched_payload_to_call(
    call: Call,
    payload: dict,
    *,
    custom_patterns: list[str] | None = None,
) -> None:
    payload = _ensure_loop_signal_payload(mask_payload(payload, custom_patterns=custom_patterns))
    prompt_tokens = _as_int(payload.get("prompt_tokens"))
    completion_tokens = _as_int(payload.get("completion_tokens"))
    reasoning_tokens = _as_int(payload.get("reasoning_tokens"))
    total_tokens = _as_int(payload.get("total_tokens")) or (
        prompt_tokens + completion_tokens + reasoning_tokens
    )
    captured_at = _parse_created_at(payload.get("created_at")) or call.created_at or datetime.now(timezone.utc)
    exchange_rate = resolve_ingest_exchange_rate(payload, captured_at=captured_at)

    call.status = _normalize_call_status(
        status_value=str(payload.get("status") or ""),
        error_code=str(payload.get("error_code")) if payload.get("error_code") is not None else None,
        error_message=str(payload.get("error_message")) if payload.get("error_message") is not None else None,
    )
    call.agent_name = _as_bounded_text(payload.get("agent_name"), max_length=255)
    call.user_id = _as_bounded_text(payload.get("user_id"), max_length=255)
    call.call_type = _as_bounded_text(payload.get("call_type"), max_length=32)
    call.error_code = str(payload.get("error_code")) if payload.get("error_code") is not None else None
    call.latency_ms = _as_float_or_none(payload.get("latency_ms"))
    call.input_tokens = prompt_tokens
    call.output_tokens = completion_tokens
    call.reasoning_tokens = reasoning_tokens
    call.total_tokens = total_tokens
    call.cost_total = _as_float(
        _first_present(
            payload.get("total_cost_usd"),
            payload.get("actual_cost_usd"),
            payload.get("cost_usd"),
        )
    )
    call.reasoning_cost_total = _as_float(payload.get("reasoning_cost_usd"))
    call.cache_savings_total = _as_float(payload.get("cache_savings_usd"))
    call.pricing_version = str(payload.get("pricing_version"))[:64] if payload.get("pricing_version") else None
    call.pricing_source = _pricing_source(payload)
    call.pricing_last_updated_at = _pricing_timestamp(payload)
    call.cost_currency = BASE_CURRENCY
    call.token_unit = TOKEN_UNIT
    call.exchange_rate_usd_to_inr = exchange_rate["exchange_rate_usd_to_inr"]
    call.exchange_rate_timestamp = exchange_rate["exchange_rate_timestamp"]
    call.exchange_rate_source = exchange_rate["exchange_rate_source"]
    call.cost_confidence = str(payload.get("cost_confidence") or "degraded")[:32]
    call.confidence_reason = _confidence_reason(payload)
    call.output_fingerprint = str(payload.get("output_fingerprint"))[:64] if payload.get("output_fingerprint") else None
    call.is_production = _is_production_event(payload)
    call.tool_lifecycle_summary_json = (
        json.dumps(payload.get("tool_lifecycle_summary"), separators=(",", ":"))
        if payload.get("tool_lifecycle_summary") is not None
        else None
    )
    call.retry_metadata_json = (
        json.dumps(payload.get("retry_metadata"), separators=(",", ":"))
        if payload.get("retry_metadata") is not None
        else None
    )
    call.payload_json = json.dumps(payload, separators=(",", ":"))
    call.metadata_json = json.dumps(
        _build_call_metadata(payload, custom_patterns=custom_patterns),
        separators=(",", ":"),
    )


def _mark_cost_degraded(payload: dict, exc: Exception) -> dict:
    degraded = dict(payload)
    fallback_cost = _first_present(
        degraded.get("total_cost_usd"),
        degraded.get("actual_cost_usd"),
        degraded.get("cost_usd"),
    )
    degraded["cost_usd"] = _as_float(fallback_cost)
    degraded["total_cost_usd"] = _as_float(fallback_cost)
    degraded["reasoning_cost_usd"] = _as_float(degraded.get("reasoning_cost_usd"))
    degraded["cache_savings_usd"] = _as_float(degraded.get("cache_savings_usd"))
    degraded["pricing_version"] = str(degraded.get("pricing_version") or "unavailable")
    degraded["pricing_source"] = "fallback_default"
    degraded["pricing_last_updated_at"] = None
    degraded["pricing_age_days"] = None
    degraded["cost_confidence"] = "degraded"
    degraded["confidence_reason"] = "cost_enrichment_failed"
    degraded["cost_currency"] = BASE_CURRENCY
    degraded["token_unit"] = TOKEN_UNIT
    degraded["cost"] = {
        "event_cost_usd": degraded["total_cost_usd"],
        "current_15m_spend_usd": 0.0,
        "baseline_15m_spend_usd": 0.0,
        "history_days": 0.0,
        "history_calls": 0,
        "baseline_window_days": 0,
        "spend_bucket_minutes": 15,
        "model_spend_coefficient": 1.0,
        "pricing_version": degraded["pricing_version"],
        "pricing_source": "fallback_default",
        "pricing_last_updated_at": None,
        "pricing_age_days": None,
        "cost_confidence": "degraded",
        "confidence_reason": "cost_enrichment_failed",
        "error_message": mask_error_message(exc),
        "per_call_breakdown": {
            "provider": degraded.get("provider") or "unknown",
            "model": degraded.get("model") or "unknown",
            "status": degraded.get("status") or "unknown",
            "total_cost_usd": degraded["total_cost_usd"],
            "currency": BASE_CURRENCY,
            "token_unit": TOKEN_UNIT,
            "pricing_source": "fallback_default",
            "cost_confidence": "degraded",
            "confidence_reason": "cost_enrichment_failed",
        },
    }
    return degraded


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
    event_key, _ = _resolve_idempotency_key(event=event, call_id=call_id)
    header_key = (request.headers.get("X-Idempotency-Key") or "").strip()
    if header_key:
        return f"{tenant_id}:{header_key[:128]}:{event_key}"
    return f"{tenant_id}:{event_key}"


def _check_redis_idempotency(key: str) -> bool:
    """Return True when *key* is present in the Redis idempotency cache.

    Failure to reach Redis is treated as a cache miss (allow through) so
    the database remains the authoritative idempotency guard.
    """
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
    rc = get_redis_client()
    if rc is None:
        return
    try:
        rc.set(f"{_REDIS_IDEM_PREFIX}{key}", "1", ex=_REDIS_IDEM_TTL)
    except Exception:
        logger.debug("Redis idempotency set failed; continuing", exc_info=True)


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
        alert.status = "OPEN"
        alert.resolved_at = None
        alert.updated_at = now
        alert.title = title
        alert.evidence_json = json.dumps(evidence, separators=(",", ":"))
        db.add(alert)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to commit backpressure alert")
        raise


@router.post("/ingest", response_model=IngestBatchResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("100/minute")
def ingest_events(
    request: Request,
    body: IngestBatchRequest,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> IngestBatchResponse:
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

    accepted = 0
    queued = 0
    duplicates = 0
    enqueue_failed = 0
    custom_pii_patterns = _project_pii_patterns(db, tenant_id)

    for event in body.events:
        diagnosis_id = event.call_id.strip()
        event_payload = event.model_dump()
        idempotency_key = _extract_redis_idempotency_key(
            request=request,
            event=event_payload,
            call_id=diagnosis_id,
            tenant_id=tenant_id,
        )
        if _check_redis_idempotency(idempotency_key):
            duplicates += 1
            record_diagnosis_job("already_exists")
            continue

        event_id, event_id_source = _resolve_idempotency_key(event=event_payload, call_id=diagnosis_id)
        payload = _build_payload_from_event(event_payload)
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
            retry_result = _retry_enqueue_for_existing_call(db=db, tenant_id=tenant_id, call=existing_call)
            if retry_result == "queued":
                queued += 1
            elif retry_result == "failed":
                enqueue_failed += 1
            continue

        # Enrich cost data before creating the record for atomic insert
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

    return IngestBatchResponse(
        accepted=accepted,
        queued=queued,
        duplicates=duplicates,
        enqueue_failed=enqueue_failed,
    )
