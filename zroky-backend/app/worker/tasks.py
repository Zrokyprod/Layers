import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import and_, func, select
from sqlalchemy.orm import load_only, selectinload

from app.core.config import get_settings
from app.realtime.publisher import publish_diagnosis, publish_loop_alert, publish_auth_failure_alert, publish_rate_limit_alert, publish_cost_spike
from app.db.models import AuditLog, Call, DiagnosisFixWatch, DiagnosisJob, Project, ProjectDashboardConfig, ReplayRun
from app.db.session import SessionLocal, set_db_tenant_context
from app.observability.metrics import (
    record_diagnosis_job,
    record_diagnosis_rule_hits,
    record_retention_rows,
    record_retention_run,
)
from app.services.alerts import sync_alerts_from_jobs
from app.services.diagnosis_engine import (
    build_diagnosis_result,
    evaluate_fast_rules,
    evaluate_pattern_rules,
)
from app.services.fix_adoption import (
    calibrate_resolved_fix_confidence,
    ensure_fix_event_prerequisites,
    evaluate_fix_regressions,
    evaluate_pending_fix_resolutions,
    record_fix_event,
)
from app.services.fix_identity import extract_fix_id_from_result, safe_json_object as _fix_safe_json_object
from app.services.loop_pattern_cache import mark_loop_detected_fired, summarize_loop_from_cache
from app.services.loop_signals import (
    DEFAULT_LOOP_WINDOW_SIZE,
    normalize_loop_text,
    output_signal,
    output_similarity_score,
    summarize_tool_lifecycle,
)
from app.services.privacy import mask_error_message, mask_payload, mask_value
from app.services.retention import (
    DEFAULT_RETENTION_DAYS,
    normalize_retention_days,
    purge_project_retention_data,
)
from app.worker.celery_app import celery_app
from app.worker.idempotency import idempotency_guard
from app.services.email_sender import send_email, send_slack_message
from app.services.weekly_impact import (
    WeeklyImpactSummary,
    compute_weekly_impact,
    render_weekly_impact_html,
    render_weekly_impact_plain,
)
logger = logging.getLogger(__name__)

LOOP_REPEAT_THRESHOLD = 5
LOOP_REPEAT_WINDOW_SECONDS = 90
LOOP_TOOL_WINDOW_SECONDS = 120
LOOP_COOLDOWN_SECONDS = 600
LOOP_PROGRESS_MIN_EVENTS = 3
LOOP_EVIDENCE_SAMPLE_LIMIT = 5
LOOP_REPEAT_SCAN_LIMIT = 64
LOOP_PROGRESS_SCAN_LIMIT = 96
LOOP_COOLDOWN_SCAN_LIMIT = 128
LOOP_WINDOW_SIZE = DEFAULT_LOOP_WINDOW_SIZE
TERMINAL_DIAGNOSIS_STATUSES = {"done", "completed", "failed", "dead_lettered"}
SUCCESS_DIAGNOSIS_STATUSES = {"done", "completed"}
REQUEUEABLE_DIAGNOSIS_STATUSES = {"pending", "queued", "retrying", "enqueue_failed"}


def _calculate_retry_countdown(*, retry_count: int, base_seconds: int, max_seconds: int) -> int:
    bounded_retry = max(0, retry_count)
    bounded_base = max(1, base_seconds)
    bounded_max = max(bounded_base, max_seconds)
    return min(bounded_max, bounded_base * (2**bounded_retry))


def _current_retry_count(task: object) -> int:
    request = getattr(task, "request", None)
    return int(getattr(request, "retries", 0) or 0)


def _as_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return parsed if parsed > 0 else default


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _safe_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}

    if isinstance(parsed, dict):
        return mask_payload(parsed)
    return {}


def _payload_for_job(job: DiagnosisJob) -> dict[str, Any]:
    if job.call is not None and job.call.payload_json:
        payload = _safe_json_object(job.call.payload_json)
        if job.call.output_fingerprint and not payload.get("output_fingerprint"):
            payload["output_fingerprint"] = job.call.output_fingerprint
        if job.call.tool_lifecycle_summary_json and not payload.get("tool_lifecycle_summary"):
            payload["tool_lifecycle_summary"] = _safe_json_object_or_array(
                job.call.tool_lifecycle_summary_json,
            )
        if job.call.retry_metadata_json and not payload.get("retry_metadata"):
            payload["retry_metadata"] = _safe_json_object(job.call.retry_metadata_json)
        return payload
    return _safe_json_object(job.payload_json)


def _safe_json_object_or_array(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return mask_value(parsed) if isinstance(parsed, (dict, list)) else None


def _payload_for_call_or_legacy(
    *,
    call: Call | None,
    job: DiagnosisJob | None,
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if call is not None and call.payload_json:
        payload = _safe_json_object(call.payload_json)
        if call.output_fingerprint and not payload.get("output_fingerprint"):
            payload["output_fingerprint"] = call.output_fingerprint
        if call.tool_lifecycle_summary_json and not payload.get("tool_lifecycle_summary"):
            payload["tool_lifecycle_summary"] = _safe_json_object_or_array(
                call.tool_lifecycle_summary_json,
            )
        if call.retry_metadata_json and not payload.get("retry_metadata"):
            payload["retry_metadata"] = _safe_json_object(call.retry_metadata_json)
        return payload
    if isinstance(payload, Mapping):
        return mask_payload(payload)
    if job is not None:
        return _safe_json_object(job.payload_json)
    return {}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip().lower()
    if not text:
        return ""
    return " ".join(text.split())


def _payload_retry_attempt(payload: Mapping[str, Any]) -> bool:
    retry_section = payload.get("retry")
    retry_mapping = retry_section if isinstance(retry_section, Mapping) else {}

    if _coerce_bool(retry_mapping.get("is_sdk_retry"), default=False):
        return True
    if _coerce_positive_int(retry_mapping.get("sdk_attempts"), 0) > 0:
        return True
    if _coerce_positive_int(retry_mapping.get("backoff_attempts"), 0) > 0:
        return True
    if _coerce_positive_int(payload.get("sdk_retry_attempts"), 0) > 0:
        return True
    if _coerce_positive_int(payload.get("backoff_attempts"), 0) > 0:
        return True
    if _coerce_positive_int(payload.get("retry_attempt"), 0) > 0:
        return True

    return _coerce_bool(payload.get("is_sdk_retry"), default=False)


def _payload_failure_signature(
    payload: Mapping[str, Any],
    *,
    job_status: str,
    job_error_message: str | None,
) -> tuple[bool, str]:
    status_text = _normalize_text(payload.get("status"))
    payload_error_code = _normalize_text(payload.get("error_code"))
    payload_error_message = mask_error_message(_normalize_text(payload.get("error_message")))
    status_code = _coerce_positive_int(payload.get("status_code"), 0)

    failure_status_values = {"failed", "error", "errored", "timeout"}
    is_failure = (
        status_text in failure_status_values
        or bool(payload_error_code)
        or bool(payload_error_message)
        or status_code >= 400
        or _normalize_text(job_status) in {"dead_lettered", "enqueue_failed"}
        or bool(_normalize_text(job_error_message))
    )

    if not is_failure:
        return False, ""

    if payload_error_code:
        return True, f"code:{payload_error_code}"
    if payload_error_message:
        return True, f"message:{payload_error_message[:120]}"

    fallback_error = mask_error_message(_normalize_text(job_error_message))
    if fallback_error:
        return True, f"message:{fallback_error[:120]}"

    if status_code >= 400:
        return True, f"status_code:{status_code}"

    return True, f"status:{status_text or _normalize_text(job_status) or 'failure'}"


def _payload_useless_output(payload: Mapping[str, Any]) -> bool:
    status_text = _normalize_text(payload.get("status"))
    completion_tokens = _coerce_positive_int(payload.get("completion_tokens"), 0)
    prompt_tokens = _coerce_positive_int(payload.get("prompt_tokens"), 0)
    output_content = payload.get("output_content")

    if isinstance(output_content, str) and not output_content.strip() and status_text in {"completed", "success"}:
        return True

    if completion_tokens == 0 and prompt_tokens > 0 and status_text in {"completed", "success"}:
        return True

    return False


def _payload_output_signature(payload: Mapping[str, Any]) -> str:
    output_fingerprint = _as_text(payload.get("output_fingerprint"))
    if output_fingerprint:
        return output_fingerprint
    output_value = payload.get("normalized_output") or payload.get("output_content")
    signal = output_signal(output_value)
    return str(signal.get("output_fingerprint") or "")


def _payload_normalized_output(payload: Mapping[str, Any]) -> str:
    value = payload.get("normalized_output") or payload.get("output_content")
    return normalize_loop_text(value)


def _payload_tool_lifecycle(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = payload.get("tool_lifecycle_summary")
    if isinstance(summary, list):
        return [item for item in summary if isinstance(item, dict)]
    tool_calls = payload.get("tool_calls_made")
    if isinstance(tool_calls, list):
        return summarize_tool_lifecycle(tool_calls) or []
    return []


def _payload_retry_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    retry = payload.get("retry_metadata")
    if isinstance(retry, Mapping):
        return dict(retry)
    retry_section = payload.get("retry")
    if isinstance(retry_section, Mapping):
        return dict(retry_section)
    return {}


def _fetch_recent_signature_rows(
    session,
    *,
    tenant_id: str,
    agent_name: str,
    prompt_fingerprint: str,
    window_seconds: int,
    limit: int,
    now: datetime,
) -> list[DiagnosisJob]:
    # UTCDateTime column type normalizes tz across backends — pass through.
    query_now = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    window_start = query_now - timedelta(seconds=max(1, window_seconds))
    query = (
        select(DiagnosisJob)
        .options(
            load_only(
                DiagnosisJob.created_at,
                DiagnosisJob.payload_json,
                DiagnosisJob.result_json,
                DiagnosisJob.status,
                DiagnosisJob.error_message,
                DiagnosisJob.call_id,
            ),
            selectinload(DiagnosisJob.call).load_only(
                Call.payload_json,
                Call.output_fingerprint,
                Call.tool_lifecycle_summary_json,
                Call.retry_metadata_json,
            ),
        )
        .where(
            DiagnosisJob.tenant_id == tenant_id,
            DiagnosisJob.agent_name == agent_name,
            DiagnosisJob.prompt_fingerprint == prompt_fingerprint,
            DiagnosisJob.created_at >= window_start,
            DiagnosisJob.created_at <= query_now,
        )
        .order_by(DiagnosisJob.created_at.desc())
        .limit(max(1, limit))
    )
    return list(session.execute(query).scalars().all())


def _summarize_loop_progress(rows: list[DiagnosisJob]) -> dict[str, Any]:
    retry_excluded = 0
    eligible_rows: list[DiagnosisJob] = []
    failure_count = 0
    useless_output_count = 0
    error_counter: Counter[str] = Counter()
    output_counter: Counter[str] = Counter()
    tool_input_counter: Counter[str] = Counter()
    tool_failure_counter: Counter[str] = Counter()
    tool_success_no_change_counter: Counter[str] = Counter()
    retry_reason_counter: Counter[str] = Counter()
    tool_sequence: list[str] = []
    normalized_outputs: list[str] = []
    tool_state_changes = 0
    tool_no_state_changes = 0
    retry_count_total = 0

    window_rows = sorted(rows, key=lambda item: item.created_at)[-LOOP_WINDOW_SIZE:]
    for row in window_rows:
        payload = _payload_for_job(row)
        retry_metadata = _payload_retry_metadata(payload)
        retry_count = _coerce_positive_int(retry_metadata.get("retry_count"), 0)
        retry_reason = _normalize_text(retry_metadata.get("retry_reason"))
        if retry_count > 0:
            retry_count_total += retry_count
        if retry_reason:
            retry_reason_counter[retry_reason] += max(1, retry_count)

        if _payload_retry_attempt(payload):
            retry_excluded += 1

        eligible_rows.append(row)

        is_failure, failure_signature = _payload_failure_signature(
            payload,
            job_status=row.status,
            job_error_message=row.error_message,
        )
        if is_failure:
            failure_count += 1
            if failure_signature:
                error_counter[failure_signature] += 1

        if _payload_useless_output(payload):
            useless_output_count += 1

        output_signature = _payload_output_signature(payload)
        if output_signature:
            output_counter[output_signature] += 1
        normalized_output = _payload_normalized_output(payload)
        if normalized_output:
            normalized_outputs.append(normalized_output)

        for tool_event in _payload_tool_lifecycle(payload):
            tool_name = _normalize_text(tool_event.get("tool_name")) or "unknown"
            input_signature = _normalize_text(tool_event.get("tool_input_signature"))
            output_signature_tool = _normalize_text(tool_event.get("tool_output_signature"))
            tool_sequence.append(tool_name)
            if input_signature:
                tool_input_counter[f"{tool_name}:{input_signature}"] += 1
            tool_success = _coerce_bool(tool_event.get("tool_success"), default=False)
            if not tool_success:
                tool_failure_counter[tool_name] += 1
            elif input_signature and output_signature_tool:
                tool_success_no_change_counter[f"{tool_name}:{input_signature}:{output_signature_tool}"] += 1
                if _coerce_bool(tool_event.get("state_changed"), default=False):
                    tool_state_changes += 1
                else:
                    tool_no_state_changes += 1

    dominant_error, dominant_error_count = ("", 0)
    if error_counter:
        dominant_error, dominant_error_count = error_counter.most_common(1)[0]

    stagnant_output = False
    dominant_output_fingerprint: str | None = None
    dominant_output_count = 0
    if output_counter:
        dominant_output_fingerprint, dominant_output_count = output_counter.most_common(1)[0]
        stagnant_output = dominant_output_count >= LOOP_PROGRESS_MIN_EVENTS

    output_similarity = _max_recent_output_similarity(normalized_outputs)
    near_repeated_output = output_similarity >= 0.72 and len(normalized_outputs) >= 3

    dominant_tool_pattern, dominant_tool_count = ("", 0)
    tool_pattern_type = None
    for pattern_type, counter in (
        ("same_tool_input", tool_input_counter),
        ("tool_failure", tool_failure_counter),
        ("tool_success_no_state_change", tool_success_no_change_counter),
    ):
        if not counter:
            continue
        candidate, count = counter.most_common(1)[0]
        if count > dominant_tool_count:
            dominant_tool_pattern = candidate
            dominant_tool_count = count
            tool_pattern_type = pattern_type

    alternating_tool_cycle = _alternating_tool_cycle(tool_sequence)
    if alternating_tool_cycle and len(tool_sequence) >= 4 and dominant_tool_count < 4:
        dominant_tool_pattern = "->".join(alternating_tool_cycle)
        dominant_tool_count = len(tool_sequence)
        tool_pattern_type = "alternating_tool_cycle"

    dominant_retry_reason, dominant_retry_count = ("", 0)
    if retry_reason_counter:
        dominant_retry_reason, dominant_retry_count = retry_reason_counter.most_common(1)[0]

    repeated_failures = failure_count >= LOOP_PROGRESS_MIN_EVENTS
    repeated_useless_output = useless_output_count >= LOOP_PROGRESS_MIN_EVENTS or stagnant_output
    repeated_tool_cycle = dominant_tool_count >= LOOP_PROGRESS_MIN_EVENTS
    repeated_retry_pattern = retry_count_total >= 3 and dominant_retry_count >= 3
    tool_state_changed = tool_state_changes > 0 and tool_state_changes >= tool_no_state_changes
    loop_resolved = _loop_break_detected(
        normalized_outputs=normalized_outputs,
        output_similarity=output_similarity,
        tool_state_changed=tool_state_changed,
    )
    no_progress = (
        repeated_failures
        or repeated_useless_output
        or near_repeated_output
        or repeated_tool_cycle
        or repeated_retry_pattern
    ) and not loop_resolved

    sample_timestamps = [
        row.created_at.astimezone(timezone.utc).isoformat()
        if row.created_at.tzinfo is not None
        else row.created_at.replace(tzinfo=timezone.utc).isoformat()
        for row in sorted(eligible_rows, key=lambda item: item.created_at)
    ][-LOOP_EVIDENCE_SAMPLE_LIMIT:]

    reasons: list[str] = []
    if repeated_failures:
        reasons.append("repeated_failures")
    if repeated_useless_output:
        reasons.append("repeated_useless_output")
    if stagnant_output and "stagnant_output" not in reasons:
        reasons.append("stagnant_output")
    if near_repeated_output:
        reasons.append("near_repeated_output")
    if repeated_tool_cycle:
        reasons.append("tool_cycle_repeat")
    if repeated_retry_pattern:
        reasons.append("retry_pattern")

    return {
        "eligible_count": len(eligible_rows),
        "loop_window_size": LOOP_WINDOW_SIZE,
        "retry_excluded_count": retry_excluded,
        "no_progress": no_progress,
        "loop_resolved": loop_resolved,
        "no_progress_reasons": reasons,
        "sample_timestamps": sample_timestamps,
        "error_pattern": {
            "dominant_error": dominant_error or None,
            "dominant_error_count": dominant_error_count,
            "failure_count": failure_count,
            "useless_output_count": useless_output_count,
            "stagnant_output": stagnant_output,
        },
        "output_pattern": {
            "output_fingerprint": dominant_output_fingerprint,
            "repeat_count": dominant_output_count,
            "stagnant_output": stagnant_output,
            "output_similarity_score": output_similarity,
            "near_repeated_output": near_repeated_output,
        },
        "tool_cycle": {
            "dominant_pattern": dominant_tool_pattern or None,
            "pattern_type": tool_pattern_type,
            "repeat_count": dominant_tool_count,
            "tool_sequence": tool_sequence[-8:],
            "state_changed": tool_state_changed,
            "state_change_count": tool_state_changes,
            "no_state_change_count": tool_no_state_changes,
        },
        "retry_pattern": {
            "retry_count": retry_count_total,
            "dominant_retry_reason": dominant_retry_reason or None,
            "dominant_retry_reason_count": dominant_retry_count,
        },
    }


def _alternating_tool_cycle(tool_sequence: list[str]) -> list[str] | None:
    if len(tool_sequence) < 4:
        return None
    tail = tool_sequence[-6:]
    unique = list(dict.fromkeys(tail))
    if len(unique) != 2:
        return None
    for idx, name in enumerate(tail):
        if name != unique[idx % 2]:
            return None
    return unique


def _max_recent_output_similarity(normalized_outputs: list[str]) -> float:
    if len(normalized_outputs) < 2:
        return 0.0
    tail = normalized_outputs[-LOOP_WINDOW_SIZE:]
    best = 0.0
    for idx, left in enumerate(tail):
        for right in tail[idx + 1 :]:
            best = max(best, output_similarity_score(left, right))
    return round(best, 3)


def _loop_break_detected(
    *,
    normalized_outputs: list[str],
    output_similarity: float,
    tool_state_changed: bool,
) -> bool:
    if tool_state_changed:
        return True
    if len(normalized_outputs) < 3:
        return False
    previous = normalized_outputs[-2]
    latest = normalized_outputs[-1]
    latest_similarity = output_similarity_score(previous, latest)
    return output_similarity >= 0.72 and latest_similarity < 0.45


def _contains_loop_detected(result_json: str | None) -> bool:
    result = _safe_json_object(result_json)
    diagnoses = result.get("diagnoses")
    if not isinstance(diagnoses, list):
        return False

    for item in diagnoses:
        if not isinstance(item, Mapping):
            continue
        if _normalize_text(item.get("category")) == "loop_detected":
            return True
    return False


def _last_loop_fired_at(
    session,
    *,
    tenant_id: str,
    agent_name: str,
    prompt_fingerprint: str,
    now: datetime,
) -> datetime | None:
    rows = _fetch_recent_signature_rows(
        session,
        tenant_id=tenant_id,
        agent_name=agent_name,
        prompt_fingerprint=prompt_fingerprint,
        window_seconds=LOOP_COOLDOWN_SECONDS,
        limit=LOOP_COOLDOWN_SCAN_LIMIT,
        now=now,
    )

    for row in rows:
        if _normalize_text(row.status) not in SUCCESS_DIAGNOSIS_STATUSES:
            continue
        if _contains_loop_detected(row.result_json):
            return row.created_at
    return None


def _extract_loop_identity(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    loop_section = payload.get("loop")
    agent_name = _as_text(payload.get("agent_name"))
    prompt_fingerprint = _as_text(payload.get("prompt_fingerprint"))

    if isinstance(loop_section, Mapping):
        agent_name = agent_name or _as_text(loop_section.get("agent_name"))
        prompt_fingerprint = prompt_fingerprint or _as_text(loop_section.get("prompt_fingerprint"))

    return agent_name, prompt_fingerprint


def _bounded_recent_repeat_count(
    session,
    *,
    tenant_id: str,
    agent_name: str,
    prompt_fingerprint: str,
    window_seconds: int = LOOP_REPEAT_WINDOW_SECONDS,
    now: datetime | None = None,
) -> int:
    effective_now = now or datetime.now(timezone.utc)
    query_now = effective_now if effective_now.tzinfo is not None else effective_now.replace(tzinfo=timezone.utc)
    window_start = query_now - timedelta(seconds=max(1, window_seconds))

    count = session.execute(
        select(func.count(DiagnosisJob.id)).where(
            DiagnosisJob.tenant_id == tenant_id,
            DiagnosisJob.agent_name == agent_name,
            DiagnosisJob.prompt_fingerprint == prompt_fingerprint,
            DiagnosisJob.created_at >= window_start,
            DiagnosisJob.created_at <= query_now,
        )
    ).scalar_one()
    return int(count or 0)


def _enrich_payload_with_db_loop_context(session, *, tenant_id: str, payload: Mapping[str, Any]) -> dict:
    enriched_payload = dict(payload)
    loop_section_raw = enriched_payload.get("loop")
    loop_section = dict(loop_section_raw) if isinstance(loop_section_raw, Mapping) else {}

    agent_name, prompt_fingerprint = _extract_loop_identity(enriched_payload)
    if not agent_name or not prompt_fingerprint:
        if loop_section:
            enriched_payload["loop"] = loop_section
        return enriched_payload

    enriched_payload["agent_name"] = agent_name
    enriched_payload["prompt_fingerprint"] = prompt_fingerprint

    effective_now = datetime.now(timezone.utc)

    requested_window = _coerce_positive_int(loop_section.get("window_seconds"), LOOP_REPEAT_WINDOW_SECONDS)
    requested_tool_window = _coerce_positive_int(
        loop_section.get("tool_window_seconds"),
        LOOP_TOOL_WINDOW_SECONDS,
    )

    repeat_window_seconds = min(requested_window, LOOP_REPEAT_WINDOW_SECONDS)
    tool_window_seconds = min(requested_tool_window, LOOP_TOOL_WINDOW_SECONDS)
    progress_window_seconds = max(repeat_window_seconds, tool_window_seconds)

    payload_status = _as_text(enriched_payload.get("status")) or "unknown"
    payload_error_message = _as_text(enriched_payload.get("error_message"))
    is_retry_event = _payload_retry_attempt(enriched_payload)
    is_failure_event, failure_signature_event = _payload_failure_signature(
        enriched_payload,
        job_status=payload_status,
        job_error_message=payload_error_message,
    )
    useless_output_event = _payload_useless_output(enriched_payload)
    output_signature_event = _payload_output_signature(enriched_payload)

    cache_summary = summarize_loop_from_cache(
        tenant_id=tenant_id,
        agent_name=agent_name,
        prompt_fingerprint=prompt_fingerprint,
        now=effective_now,
        is_retry=is_retry_event,
        failure_signature=failure_signature_event if is_failure_event else "",
        useless_output=useless_output_event,
        output_signature=output_signature_event,
        repeat_window_seconds=repeat_window_seconds,
        progress_window_seconds=progress_window_seconds,
        progress_min_events=LOOP_PROGRESS_MIN_EVENTS,
        evidence_sample_limit=LOOP_EVIDENCE_SAMPLE_LIMIT,
        cooldown_seconds=LOOP_COOLDOWN_SECONDS,
    )

    if cache_summary is not None:
        repeat_count = int(cache_summary.get("repeat_count") or 0)
        retry_suppression_applied = bool(cache_summary.get("retry_excluded_count", 0) > 0)
        explicit_no_progress = _coerce_bool(loop_section.get("no_progress"), default=False)
        derived_no_progress = _coerce_bool(cache_summary.get("no_progress"), default=False)
        combined_no_progress = explicit_no_progress or derived_no_progress
        no_progress_reasons = list(cache_summary.get("no_progress_reasons") or [])
        if explicit_no_progress and "payload_no_progress" not in no_progress_reasons:
            no_progress_reasons.insert(0, "payload_no_progress")

        last_fired_at_raw = cache_summary.get("last_fired_at")
        last_fired_at = last_fired_at_raw if isinstance(last_fired_at_raw, datetime) else None
        sample_timestamps = list(cache_summary.get("sample_timestamps") or [])
        error_pattern = dict(cache_summary.get("error_pattern") or {})
        output_pattern = dict(cache_summary.get("output_pattern") or {})
        tool_cycle = dict(cache_summary.get("tool_cycle") or {})
        retry_pattern = dict(cache_summary.get("retry_pattern") or {})
        loop_window_size = _coerce_positive_int(
            cache_summary.get("loop_window_size"),
            LOOP_WINDOW_SIZE,
        )
        loop_resolved = _coerce_bool(cache_summary.get("loop_resolved"), default=False)
        repeat_count_derived_from_db = False

        # Cold-cache fallback: preserve behavior for existing DB history until cache warms.
        if repeat_count < LOOP_REPEAT_THRESHOLD or last_fired_at is None:
            repeat_rows = _fetch_recent_signature_rows(
                session,
                tenant_id=tenant_id,
                agent_name=agent_name,
                prompt_fingerprint=prompt_fingerprint,
                window_seconds=repeat_window_seconds,
                limit=LOOP_REPEAT_SCAN_LIMIT,
                now=effective_now,
            )
            repeat_summary = _summarize_loop_progress(repeat_rows)

            if progress_window_seconds == repeat_window_seconds:
                progress_summary = repeat_summary
            else:
                progress_rows = _fetch_recent_signature_rows(
                    session,
                    tenant_id=tenant_id,
                    agent_name=agent_name,
                    prompt_fingerprint=prompt_fingerprint,
                    window_seconds=progress_window_seconds,
                    limit=LOOP_PROGRESS_SCAN_LIMIT,
                    now=effective_now,
                )
                progress_summary = _summarize_loop_progress(progress_rows)

            db_repeat_count = int(repeat_summary["eligible_count"])
            if db_repeat_count > repeat_count:
                repeat_count = db_repeat_count
                repeat_count_derived_from_db = True

            retry_suppression_applied = retry_suppression_applied or bool(
                progress_summary["retry_excluded_count"] > 0
            )
            derived_no_progress = derived_no_progress or bool(progress_summary["no_progress"])
            db_reasons = list(progress_summary.get("no_progress_reasons") or [])
            for reason in db_reasons:
                if reason not in no_progress_reasons:
                    no_progress_reasons.append(reason)
            loop_window_size = _coerce_positive_int(
                progress_summary.get("loop_window_size"),
                loop_window_size,
            )
            loop_resolved = loop_resolved or _coerce_bool(
                progress_summary.get("loop_resolved"),
                default=False,
            )

            if not sample_timestamps:
                sample_timestamps = list(repeat_summary.get("sample_timestamps") or [])

            db_error_pattern = dict(progress_summary.get("error_pattern") or {})
            db_failure_count = _coerce_positive_int(db_error_pattern.get("failure_count"), 0)
            cache_failure_count = _coerce_positive_int(error_pattern.get("failure_count"), 0)
            if db_failure_count > cache_failure_count:
                error_pattern = db_error_pattern
            for key, value in (
                ("output_pattern", output_pattern),
                ("tool_cycle", tool_cycle),
                ("retry_pattern", retry_pattern),
            ):
                db_value = dict(progress_summary.get(key) or {})
                if db_value.get("repeat_count", db_value.get("retry_count", 0)) > value.get(
                    "repeat_count",
                    value.get("retry_count", 0),
                ):
                    if key == "output_pattern":
                        output_pattern = db_value
                    elif key == "tool_cycle":
                        tool_cycle = db_value
                    else:
                        retry_pattern = db_value

            if last_fired_at is None:
                last_fired_at = _last_loop_fired_at(
                    session,
                    tenant_id=tenant_id,
                    agent_name=agent_name,
                    prompt_fingerprint=prompt_fingerprint,
                    now=effective_now,
                )

        combined_no_progress = explicit_no_progress or derived_no_progress
    else:
        repeat_rows = _fetch_recent_signature_rows(
            session,
            tenant_id=tenant_id,
            agent_name=agent_name,
            prompt_fingerprint=prompt_fingerprint,
            window_seconds=repeat_window_seconds,
            limit=LOOP_REPEAT_SCAN_LIMIT,
            now=effective_now,
        )
        repeat_summary = _summarize_loop_progress(repeat_rows)

        if progress_window_seconds == repeat_window_seconds:
            progress_summary = repeat_summary
        else:
            progress_rows = _fetch_recent_signature_rows(
                session,
                tenant_id=tenant_id,
                agent_name=agent_name,
                prompt_fingerprint=prompt_fingerprint,
                window_seconds=progress_window_seconds,
                limit=LOOP_PROGRESS_SCAN_LIMIT,
                now=effective_now,
            )
            progress_summary = _summarize_loop_progress(progress_rows)

        repeat_count = int(repeat_summary["eligible_count"])
        retry_suppression_applied = bool(progress_summary["retry_excluded_count"] > 0)
        explicit_no_progress = _coerce_bool(loop_section.get("no_progress"), default=False)
        derived_no_progress = bool(progress_summary["no_progress"])
        combined_no_progress = explicit_no_progress or derived_no_progress
        no_progress_reasons = list(progress_summary.get("no_progress_reasons") or [])
        if explicit_no_progress and "payload_no_progress" not in no_progress_reasons:
            no_progress_reasons.insert(0, "payload_no_progress")

        last_fired_at = _last_loop_fired_at(
            session,
            tenant_id=tenant_id,
            agent_name=agent_name,
            prompt_fingerprint=prompt_fingerprint,
            now=effective_now,
        )
        sample_timestamps = list(repeat_summary.get("sample_timestamps") or [])
        error_pattern = dict(progress_summary.get("error_pattern") or {})
        output_pattern = dict(progress_summary.get("output_pattern") or {})
        tool_cycle = dict(progress_summary.get("tool_cycle") or {})
        retry_pattern = dict(progress_summary.get("retry_pattern") or {})
        loop_window_size = _coerce_positive_int(
            progress_summary.get("loop_window_size"),
            LOOP_WINDOW_SIZE,
        )
        loop_resolved = _coerce_bool(progress_summary.get("loop_resolved"), default=False)
        repeat_count_derived_from_db = True

    loop_section["repeat_count"] = repeat_count
    loop_section["window_seconds"] = repeat_window_seconds
    loop_section["tool_window_seconds"] = tool_window_seconds
    loop_section["loop_window_size"] = loop_window_size
    loop_section["loop_resolved"] = loop_resolved
    loop_section["repeat_count_derived_from_db"] = repeat_count_derived_from_db
    loop_section["retry_suppression_applied"] = retry_suppression_applied
    loop_section["sample_timestamps"] = sample_timestamps
    loop_section["error_pattern"] = error_pattern
    loop_section["output_pattern"] = output_pattern
    loop_section["tool_cycle"] = tool_cycle
    loop_section["retry_pattern"] = retry_pattern
    loop_section["no_progress_reasons"] = no_progress_reasons
    if last_fired_at is not None:
        normalized_last_fired = (
            last_fired_at.astimezone(timezone.utc)
            if last_fired_at.tzinfo is not None
            else last_fired_at.replace(tzinfo=timezone.utc)
        )
        loop_section["last_fired_at"] = normalized_last_fired.isoformat()

    # Require repeated failures/useless outputs for loop no-progress gating.
    loop_section["no_progress"] = combined_no_progress

    enriched_payload["loop"] = loop_section
    return enriched_payload


@celery_app.task(name="app.worker.tasks.run_fast_diagnosis", queue="diagnosis_fast")
def run_fast_diagnosis(payload: dict) -> list[dict]:
    return mask_value(evaluate_fast_rules(mask_payload(payload)))


@celery_app.task(name="app.worker.tasks.run_pattern_diagnosis", queue="diagnosis_pattern")
def run_pattern_diagnosis(payload: dict) -> dict:
    diagnoses, informational = evaluate_pattern_rules(mask_payload(payload))
    return {
        "diagnoses": mask_value(diagnoses),
        "informational": mask_value(informational),
    }


@celery_app.task(name="app.worker.tasks.process_diagnosis", bind=True, max_retries=3)
def process_diagnosis(self, tenant_id: str, diagnosis_id: str, payload: dict | None = None) -> dict:
    task_key = f"{tenant_id}:{diagnosis_id}"
    with idempotency_guard(task_key) as acquired:
        if not acquired:
            record_diagnosis_job("duplicate_ignored")
            return {
                "status": "duplicate_ignored",
                "tenant_id": tenant_id,
                "diagnosis_id": diagnosis_id,
            }

        session = SessionLocal()
        try:
            set_db_tenant_context(session, tenant_id)
            job = session.execute(
                select(DiagnosisJob).where(
                    DiagnosisJob.tenant_id == tenant_id,
                    DiagnosisJob.diagnosis_id == diagnosis_id,
                )
            ).scalar_one_or_none()
            call = None
            if job is not None and job.call_id:
                call = session.get(Call, job.call_id)
            if call is None:
                call = session.execute(
                    select(Call).where(
                        Call.project_id == tenant_id,
                        Call.id == diagnosis_id,
                    )
                ).scalar_one_or_none()

            if job is not None and _normalize_text(job.status) in TERMINAL_DIAGNOSIS_STATUSES:
                record_diagnosis_job("duplicate_ignored")
                existing_result = _safe_json_object(job.result_json)
                if existing_result:
                    existing_result.setdefault("status", "already_done")
                    return existing_result
                return {
                    "status": "already_done",
                    "tenant_id": tenant_id,
                    "diagnosis_id": diagnosis_id,
                }

            diagnosis_payload = _payload_for_call_or_legacy(
                call=call,
                job=job,
                payload=payload,
            )

            payload_with_db_context = mask_payload(_enrich_payload_with_db_loop_context(
                session,
                tenant_id=tenant_id,
                payload=diagnosis_payload,
            ))

            if job is not None:
                job.status = "processing"
                job.agent_name = _as_text(payload_with_db_context.get("agent_name"))
                job.prompt_fingerprint = _as_text(payload_with_db_context.get("prompt_fingerprint"))
                session.commit()

            # Keep orchestration inside one task while exposing dedicated fast/pattern
            # tasks so production workers can route them independently by queue.
            fast_diagnoses = evaluate_fast_rules(payload_with_db_context)
            pattern_diagnoses, informational = evaluate_pattern_rules(payload_with_db_context)

            result = mask_value(build_diagnosis_result(
                payload=payload_with_db_context,
                fast_diagnoses=fast_diagnoses,
                pattern_diagnoses=pattern_diagnoses,
                informational=informational,
            ))
            result["status"] = "processed"
            result["tenant_id"] = tenant_id
            result["diagnosis_id"] = diagnosis_id

            diagnosis_categories = [
                str(item.get("category", "UNKNOWN"))
                for item in result.get("diagnoses", [])
                if isinstance(item, dict)
            ]

            if any(category == "LOOP_DETECTED" for category in diagnosis_categories):
                loop_mapping = (
                    payload_with_db_context.get("loop")
                    if isinstance(payload_with_db_context.get("loop"), Mapping)
                    else {}
                )
                loop_agent_name = _as_text(payload_with_db_context.get("agent_name")) or _as_text(
                    loop_mapping.get("agent_name")
                )
                loop_prompt_fingerprint = _as_text(payload_with_db_context.get("prompt_fingerprint")) or _as_text(
                    loop_mapping.get("prompt_fingerprint")
                )

                if loop_agent_name and loop_prompt_fingerprint:
                    mark_loop_detected_fired(
                        tenant_id=tenant_id,
                        agent_name=loop_agent_name,
                        prompt_fingerprint=loop_prompt_fingerprint,
                        fired_at=datetime.now(timezone.utc),
                        cooldown_seconds=LOOP_COOLDOWN_SECONDS,
                    )

            record_diagnosis_job("completed")
            record_diagnosis_rule_hits(diagnosis_categories)

            logger.info(
                "diagnosis_task_completed",
                extra={
                    "event": "diagnosis_task",
                    "tenant_id": tenant_id,
                    "diagnosis_id": diagnosis_id,
                    "categories": diagnosis_categories,
                    "diagnosis_count": len(diagnosis_categories),
                },
            )

            if job is not None:
                job.status = "done" if job.call_id else "completed"
                job.result_json = json.dumps(mask_value(result), separators=(",", ":"))
                job.error_message = None
                sync_alerts_from_jobs(session, tenant_id, [job])
                session.commit()
                # Group each detected failure code into the issues triage table
                # AND, in parallel, into the new anomalies table (Module 3 Phase B
                # of the issues→anomalies rename — plan §3.1, §6.1). The two
                # writes share the same source-of-truth iteration; demoted codes
                # per plan §6.1 (AUTH_FAILURE, TOKEN_OVERFLOW, RATE_LIMIT,
                # PROVIDER_ERROR) are skipped on the anomalies side via the
                # `map_failure_code_to_detector` helper but still recorded in
                # the legacy issues table for backwards compat.
                try:
                    from app.services.issues import upsert_issue
                    from app.services.anomalies import (
                        map_failure_code_to_detector,
                        upsert_anomaly,
                    )
                    _call_cost = float(getattr(call, "cost_total", None) or 0.0) if call else 0.0
                    _occurred_at = getattr(job, "created_at", None) or datetime.now(timezone.utc)
                    _prompt_fp = _as_text(payload_with_db_context.get("prompt_fingerprint"))
                    _agent_name = _as_text(payload_with_db_context.get("agent_name"))
                    _seen_codes: set[str] = set()
                    for _diag_item in result.get("diagnoses", []):
                        if not isinstance(_diag_item, dict):
                            continue
                        _code = str(_diag_item.get("category", "")).strip().upper()
                        if not _code or _code in ("UNKNOWN", "") or _code in _seen_codes:
                            continue
                        _seen_codes.add(_code)
                        _evidence = {
                            "confidence": _diag_item.get("confidence"),
                            "summary": _diag_item.get("summary") or _diag_item.get("title"),
                        }
                        upsert_issue(
                            session,
                            project_id=tenant_id,
                            failure_code=_code,
                            prompt_fingerprint=_prompt_fp,
                            agent_name=_agent_name,
                            call_id=str(job.call_id or ""),
                            diagnosis_id=diagnosis_id,
                            occurred_at=_occurred_at,
                            call_cost_usd=_call_cost,
                            evidence=_evidence,
                        )
                        _detector = map_failure_code_to_detector(_code)
                        if _detector is not None:
                            try:
                                upsert_anomaly(
                                    session,
                                    project_id=tenant_id,
                                    detector=_detector,
                                    prompt_fingerprint=_prompt_fp,
                                    agent_name=_agent_name,
                                    call_id=str(job.call_id or "") or None,
                                    occurred_at=_occurred_at,
                                    evidence=_evidence,
                                )
                            except Exception:
                                logger.warning(
                                    "anomaly_upsert_failed",
                                    extra={"code": _code, "detector": _detector},
                                    exc_info=True,
                                )
                except Exception:
                    logger.warning("issue_upsert_failed", exc_info=True)
                # Write shown event so the fix appears in adoption funnel analytics.
                try:
                    _result_payload = _fix_safe_json_object(job.result_json)
                    _fix_id = extract_fix_id_from_result(_result_payload, diagnosis_id=diagnosis_id)
                    _now = datetime.now(timezone.utc)
                    ensure_fix_event_prerequisites(
                        session,
                        project_id=tenant_id,
                        diagnosis_id=diagnosis_id,
                        fix_id=_fix_id,
                        event_type="shown",
                        anchor_time=_now,
                        source="system",
                        inferred_from="diagnosis_completed",
                        metadata={"feed": "diagnosis_task"},
                    )
                    record_fix_event(
                        session,
                        project_id=tenant_id,
                        diagnosis_id=diagnosis_id,
                        fix_id=_fix_id,
                        event_type="shown",
                        metadata={
                            "categories": diagnosis_categories,
                            "source_endpoint": "diagnosis_task",
                        },
                        idempotency_key=f"system:diagnosis-shown:{tenant_id}:{diagnosis_id}",
                        source="system",
                        timestamp=_now,
                    )
                except Exception:
                    logger.debug("fix_shown_event_write_failed", exc_info=True)
                # Best-effort realtime broadcast — never blocks the worker.
                try:
                    publish_diagnosis(
                        tenant_id=tenant_id,
                        diagnosis={
                            "diagnosis_id": diagnosis_id,
                            "call_id": job.call_id,
                            "status": job.status,
                            "categories": diagnosis_categories,
                            "agent_name": job.agent_name,
                        },
                    )
                    if "LOOP_DETECTED" in diagnosis_categories:
                        publish_loop_alert(
                            tenant_id=tenant_id,
                            alert={
                                "diagnosis_id": diagnosis_id,
                                "agent_name": job.agent_name,
                                "prompt_fingerprint": job.prompt_fingerprint,
                            },
                        )
                    if "AUTH_FAILURE" in diagnosis_categories:
                        publish_auth_failure_alert(
                            tenant_id=tenant_id,
                            alert={
                                "diagnosis_id": diagnosis_id,
                                "agent_name": job.agent_name,
                            },
                        )
                    if "RATE_LIMIT" in diagnosis_categories:
                        publish_rate_limit_alert(
                            tenant_id=tenant_id,
                            alert={
                                "diagnosis_id": diagnosis_id,
                                "agent_name": job.agent_name,
                            },
                        )
                    if "COST_SPIKE" in diagnosis_categories:
                        publish_cost_spike(
                            tenant_id=tenant_id,
                            spike={
                                "diagnosis_id": diagnosis_id,
                                "agent_name": job.agent_name,
                            },
                        )
                except Exception:  # noqa: BLE001
                    logger.debug("realtime publish failed", exc_info=True)
                try:
                    evaluate_pending_fix_resolutions(session, project_id=tenant_id)
                    evaluate_fix_regressions(session, project_id=tenant_id)
                    calibrate_resolved_fix_confidence(session, project_id=tenant_id)
                except Exception:
                    logger.exception(
                        "fix_resolution_evaluation_failed",
                        extra={
                            "event": "fix_resolution_evaluation",
                            "tenant_id": tenant_id,
                            "diagnosis_id": diagnosis_id,
                        },
                    )

                try:
                    from app.services.judge_shadow import should_run_shadow_judge
                    for _code in diagnosis_categories:
                        if should_run_shadow_judge(db=session, tenant_id=tenant_id, failure_code=_code):
                            _call_prompt = None
                            _call_response = None
                            if job.call is not None:
                                _raw = _safe_json_object(job.call.payload_json)
                                _call_prompt = _as_text(_raw.get("prompt"))
                                _call_response = _as_text(_raw.get("response"))
                            run_shadow_judge_task.apply_async(
                                kwargs={
                                    "tenant_id": tenant_id,
                                    "call_id": str(job.call_id or ""),
                                    "failure_code": _code,
                                    "call_prompt": _call_prompt,
                                    "call_response": _call_response,
                                    "diagnosis_summary": str(diagnosis_id),
                                },
                                queue="diagnosis_pattern",
                                countdown=5,
                            )
                            break
                except Exception:
                    logger.debug("shadow_judge_dispatch_failed", exc_info=True)

            return result
        except Exception as exc:
            session.rollback()

            settings = get_settings()
            max_retries = max(0, settings.DIAGNOSIS_TASK_MAX_RETRIES)
            retry_count = _current_retry_count(self)
            error_message = mask_error_message(exc)

            job = session.execute(
                select(DiagnosisJob).where(
                    DiagnosisJob.tenant_id == tenant_id,
                    DiagnosisJob.diagnosis_id == diagnosis_id,
                )
            ).scalar_one_or_none()

            if retry_count < max_retries:
                countdown = _calculate_retry_countdown(
                    retry_count=retry_count,
                    base_seconds=settings.DIAGNOSIS_TASK_RETRY_BASE_SECONDS,
                    max_seconds=settings.DIAGNOSIS_TASK_RETRY_MAX_SECONDS,
                )

                if job is not None:
                    job.status = "retrying"
                    job.error_message = error_message
                    session.add(job)
                    session.commit()

                record_diagnosis_job("retry_scheduled")
                logger.warning(
                    "diagnosis_task_retry_scheduled",
                    extra={
                        "event": "diagnosis_task",
                        "tenant_id": tenant_id,
                        "diagnosis_id": diagnosis_id,
                        "retry_count": retry_count,
                        "max_retries": max_retries,
                        "countdown_seconds": countdown,
                    },
                )
                raise self.retry(exc=exc, countdown=countdown, max_retries=max_retries)

            dead_letter_payload = {
                "status": "dead_lettered",
                "tenant_id": tenant_id,
                "diagnosis_id": diagnosis_id,
                "error_message": error_message,
                "retry_count": retry_count,
                "max_retries": max_retries,
                "dead_lettered_at": datetime.now(timezone.utc).isoformat(),
            }

            if job is not None:
                job.status = "failed" if job.call_id else "dead_lettered"
                job.error_message = error_message
                job.result_json = json.dumps(dead_letter_payload, separators=(",", ":"))
                session.add(job)
                session.commit()

            record_diagnosis_job("dead_lettered")
            logger.exception(
                "diagnosis_task_dead_lettered",
                extra={
                    "event": "diagnosis_task",
                    "tenant_id": tenant_id,
                    "diagnosis_id": diagnosis_id,
                    "retry_count": retry_count,
                    "max_retries": max_retries,
                },
            )
            return dead_letter_payload
        finally:
            session.close()


@celery_app.task(name="app.worker.tasks.requeue_pending_diagnosis_jobs", queue="diagnosis_fast")
def requeue_pending_diagnosis_jobs(
    tenant_id: str,
    *,
    older_than_seconds: int = 60,
    limit: int = 100,
) -> dict[str, Any]:
    session = SessionLocal()
    enqueued = 0
    failed = 0
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(1, older_than_seconds))
    bounded_limit = min(max(1, limit), 1000)

    try:
        set_db_tenant_context(session, tenant_id)
        jobs = list(
            session.execute(
                select(DiagnosisJob)
                .where(
                    DiagnosisJob.tenant_id == tenant_id,
                    DiagnosisJob.status.in_(REQUEUEABLE_DIAGNOSIS_STATUSES),
                    DiagnosisJob.updated_at <= cutoff,
                )
                .order_by(DiagnosisJob.updated_at.asc())
                .limit(bounded_limit)
            )
            .scalars()
            .all()
        )

        for job in jobs:
            try:
                process_diagnosis.delay(
                    tenant_id,
                    job.diagnosis_id,
                    None if job.call_id else _safe_json_object(job.payload_json),
                )
                job.error_message = None
                session.add(job)
                enqueued += 1
                record_diagnosis_job("queued")
            except Exception as exc:
                job.error_message = mask_error_message(exc)
                session.add(job)
                failed += 1
                record_diagnosis_job("enqueue_failed")

        session.commit()
        return {
            "status": "ok",
            "tenant_id": tenant_id,
            "scanned": len(jobs),
            "enqueued": enqueued,
            "failed": failed,
        }
    except Exception:
        session.rollback()
        logger.exception(
            "pending_diagnosis_requeue_failed",
            extra={"event": "diagnosis_requeue", "tenant_id": tenant_id},
        )
        raise
    finally:
        session.close()


@celery_app.task(name="app.worker.tasks.purge_project_retention", queue="diagnosis_fast")
def purge_project_retention(
    tenant_id: str,
    *,
    retention_days: int | None = None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    effective_dry_run = settings.RETENTION_PURGE_DRY_RUN if dry_run is None else bool(dry_run)
    session = SessionLocal()
    try:
        set_db_tenant_context(session, tenant_id)
        configured_days = retention_days
        if configured_days is None:
            config = session.execute(
                select(ProjectDashboardConfig).where(ProjectDashboardConfig.tenant_id == tenant_id)
            ).scalar_one_or_none()
            configured_days = config.retention_days if config is not None else DEFAULT_RETENTION_DAYS

        summary = purge_project_retention_data(
            session=session,
            tenant_id=tenant_id,
            retention_days=normalize_retention_days(configured_days),
            batch_size=settings.RETENTION_PURGE_BATCH_SIZE,
            dry_run=effective_dry_run,
        )

        for table_name, row_count in summary["deleted_by_table"].items():
            record_retention_rows(table_name, row_count, dry_run=effective_dry_run)

        logger.info(
            "retention_project_purge_completed",
            extra={
                "event": "retention_enforcement",
                "tenant_id": tenant_id,
                "retention_days": summary["retention_days"],
                "dry_run": effective_dry_run,
                "total_deleted": summary["total_deleted"],
            },
        )
        return summary
    except Exception:
        session.rollback()
        logger.exception(
            "retention_project_purge_failed",
            extra={"event": "retention_enforcement", "tenant_id": tenant_id},
        )
        raise
    finally:
        session.close()


@celery_app.task(name="app.worker.tasks.run_retention_enforcement", queue="diagnosis_fast")
def run_retention_enforcement(
    *,
    dry_run: bool | None = None,
    tenant_limit: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.RETENTION_ENFORCEMENT_ENABLED:
        record_retention_run("disabled")
        return {
            "status": "disabled",
            "retention_enforcement_enabled": False,
            "processed_tenants": 0,
            "failed_tenants": 0,
            "total_deleted": 0,
            "results": [],
            "errors": [],
        }

    effective_dry_run = settings.RETENTION_PURGE_DRY_RUN if dry_run is None else bool(dry_run)
    bounded_limit = max(1, int(tenant_limit)) if tenant_limit is not None else None
    session = SessionLocal()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    try:
        tenant_query = select(Project.id).where(Project.is_active.is_(True)).order_by(Project.id.asc())
        if bounded_limit is not None:
            tenant_query = tenant_query.limit(bounded_limit)
        tenant_ids = list(session.execute(tenant_query).scalars().all())

        for tenant_id in tenant_ids:
            try:
                set_db_tenant_context(session, tenant_id)
                config = session.execute(
                    select(ProjectDashboardConfig).where(ProjectDashboardConfig.tenant_id == tenant_id)
                ).scalar_one_or_none()
                retention_days = normalize_retention_days(
                    config.retention_days if config is not None else DEFAULT_RETENTION_DAYS
                )
                summary = purge_project_retention_data(
                    session=session,
                    tenant_id=tenant_id,
                    retention_days=retention_days,
                    batch_size=settings.RETENTION_PURGE_BATCH_SIZE,
                    dry_run=effective_dry_run,
                )
                for table_name, row_count in summary["deleted_by_table"].items():
                    record_retention_rows(table_name, row_count, dry_run=effective_dry_run)
                results.append(summary)
            except Exception as exc:
                session.rollback()
                errors.append(
                    {
                        "tenant_id": tenant_id,
                        "error": mask_error_message(exc),
                    }
                )
                logger.exception(
                    "retention_tenant_run_failed",
                    extra={"event": "retention_enforcement", "tenant_id": tenant_id},
                )

        total_deleted = sum(int(item.get("total_deleted", 0) or 0) for item in results)
        status = "ok"
        if errors:
            status = "partial_failure" if results else "failed"

        record_retention_run(status)
        summary_payload = {
            "status": status,
            "retention_enforcement_enabled": True,
            "dry_run": effective_dry_run,
            "processed_tenants": len(results),
            "failed_tenants": len(errors),
            "total_deleted": total_deleted,
            "results": results,
            "errors": errors,
        }
        logger.info(
            "retention_enforcement_run_completed",
            extra={
                "event": "retention_enforcement",
                "status": status,
                "processed_tenants": len(results),
                "failed_tenants": len(errors),
                "total_deleted": total_deleted,
                "dry_run": effective_dry_run,
            },
        )
        return summary_payload
    finally:
        session.close()


@celery_app.task(name="app.worker.tasks.send_weekly_impact_emails", queue="diagnosis_fast")
def send_weekly_impact_emails() -> dict:
    """Celery beat task: send weekly developer impact emails to all active projects."""
    settings = get_settings()
    if not settings.WEEKLY_IMPACT_EMAIL_ENABLED:
        logger.info("send_weekly_impact_emails: feature disabled — skipping")
        return {"skipped": True}

    session = SessionLocal()
    sent = 0
    errors = 0
    try:
        projects: list[Project] = list(
            session.execute(
                select(Project).where(Project.is_active.is_(True))
            ).scalars().all()
        )

        for project in projects:
            try:
                summary: WeeklyImpactSummary = compute_weekly_impact(session, project.id)

                if not summary.recipient_emails:
                    logger.debug(
                        "send_weekly_impact_emails: no admin emails for project %s — skipping",
                        project.id,
                    )
                    continue

                subject = f"ZROKY saved you ${summary.prevented_waste_usd:.2f} this week"
                html_body = render_weekly_impact_html(summary)
                plain_body = render_weekly_impact_plain(summary)

                ok = send_email(
                    summary.recipient_emails,
                    subject,
                    html_body,
                    plain_body=plain_body,
                )
                if ok:
                    sent += 1
                    logger.info(
                        "send_weekly_impact_emails: sent for project %s to %d recipients",
                        project.id,
                        len(summary.recipient_emails),
                    )
                else:
                    logger.warning(
                        "send_weekly_impact_emails: send_email returned False for project %s",
                        project.id,
                    )
            except Exception as project_exc:  # noqa: BLE001
                errors += 1
                logger.error(
                    "send_weekly_impact_emails: failed for project %s: %s",
                    project.id,
                    project_exc,
                )

        return {"projects_processed": len(projects), "emails_sent": sent, "errors": errors}
    finally:
        session.close()


@celery_app.task(name="app.worker.tasks.notify_fix_watch_recurrences", queue="diagnosis_fast")
def notify_fix_watch_recurrences() -> dict:
    """Celery beat task: scan active fix watches, send email/Slack for new recurrences."""
    session = SessionLocal()
    notified = 0
    errors = 0

    try:
        now = datetime.now(timezone.utc)
        # Only watches that are still active (not yet expired)
        watches: list[DiagnosisFixWatch] = list(
            session.execute(
                select(DiagnosisFixWatch).where(DiagnosisFixWatch.watch_expires_at > now)
            ).scalars().all()
        )

        for watch in watches:
            try:
                set_db_tenant_context(session, watch.tenant_id)
                target_cats = json.loads(watch.target_categories_json or "[]")
                if not target_cats:
                    continue

                recurrence_jobs = []
                _candidate_jobs = list(
                    session.execute(
                        select(DiagnosisJob).where(
                            and_(
                                DiagnosisJob.tenant_id == watch.tenant_id,
                                DiagnosisJob.status.in_(SUCCESS_DIAGNOSIS_STATUSES),
                                DiagnosisJob.created_at > watch.resolved_at,
                            )
                        ).order_by(DiagnosisJob.created_at.desc()).limit(500)
                    ).scalars().all()
                )
                for _job in _candidate_jobs:
                    try:
                        _result = json.loads(_job.result_json or "{}")
                        _diagnoses = _result.get("diagnoses") if isinstance(_result, dict) else []
                        if not isinstance(_diagnoses, list):
                            continue
                        _job_cats = {
                            d.get("category") for d in _diagnoses
                            if isinstance(d, dict) and isinstance(d.get("category"), str)
                        }
                        if _job_cats & set(target_cats):
                            recurrence_jobs.append(_job)
                    except (json.JSONDecodeError, TypeError, AttributeError):
                        continue
                if not recurrence_jobs:
                    continue

                # Check if we already sent a notification today for this watch
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                already_notified = session.execute(
                    select(AuditLog).where(
                        and_(
                            AuditLog.tenant_id == watch.tenant_id,
                            AuditLog.diagnosis_id == watch.diagnosis_id,
                            AuditLog.action == "fix_watch_recurrence_notified",
                            AuditLog.created_at >= today_start,
                        )
                    ).limit(1)
                ).scalars().first()
                if already_notified:
                    continue

                project = session.get(Project, watch.tenant_id)
                project_name = project.name if project else watch.tenant_id

                slack_msg = (
                    f":rotating_light: *Fix regression* in project {project_name}\n"
                    f"Diagnosis {watch.diagnosis_id} ({', '.join(target_cats)}) has recurred "
                    f"{len(recurrence_jobs)} time(s) since the fix. Review the dashboard."
                )
                send_slack_message(slack_msg)

                # Record notification in audit log to avoid re-notifying today
                audit = AuditLog(
                    tenant_id=watch.tenant_id,
                    diagnosis_id=watch.diagnosis_id,
                    action="fix_watch_recurrence_notified",
                    actor_subject="system",
                    metadata_json=json.dumps({"recurrence_count": len(recurrence_jobs)}),
                )
                session.add(audit)
                session.commit()
                notified += 1
            except Exception as exc:  # noqa: BLE001
                errors += 1
                logger.error("notify_fix_watch_recurrences: error for watch %s: %s", watch.id, exc)

        return {"watches_scanned": len(watches), "notifications_sent": notified, "errors": errors}
    finally:
        session.close()


@celery_app.task(name="app.worker.tasks.sync_clickhouse", queue="diagnosis_fast", ignore_result=True)
def sync_clickhouse() -> dict:
    """Beat task: pull new Call rows from Postgres → insert into ClickHouse."""
    from app.services.clickhouse_sync import sync_calls_to_clickhouse
    session = SessionLocal()
    try:
        return sync_calls_to_clickhouse(session)
    finally:
        session.close()


@celery_app.task(
    name="app.worker.tasks.run_shadow_judge_task",
    queue="diagnosis_pattern",
    max_retries=0,
    ignore_result=True,
)
def run_shadow_judge_task(
    *,
    tenant_id: str,
    call_id: str,
    failure_code: str,
    call_prompt: str | None = None,
    call_response: str | None = None,
    diagnosis_summary: str | None = None,
) -> dict:
    """Background shadow judge — fire-and-forget, never retried, never blocks production."""
    from app.services.judge_shadow import run_shadow_judge
    verdict = run_shadow_judge(
        tenant_id=tenant_id,
        call_id=call_id,
        failure_code=failure_code,
        call_prompt=call_prompt,
        call_response=call_response,
        diagnosis_summary=diagnosis_summary,
    )
    logger.info(
        "shadow_judge_completed tenant=%s call=%s code=%s verdict=%s conf=%.2f",
        tenant_id,
        call_id,
        failure_code,
        verdict.get("verdict"),
        verdict.get("confidence", 0.0),
    )
    return verdict


@celery_app.task(
    name="app.worker.tasks.process_replay_run",
    queue="diagnosis_pattern",
    bind=True,
    max_retries=2,
)
def process_replay_run(
    self,
    tenant_id: str,
    run_id: str,
    *,
    record_calibration: bool = False,
) -> dict:
    """Execute a pending ReplayRun (Module 8; plan §6.4).

    Grades every GoldenTrace in the parent set against the configured
    judge_engine evaluator and writes one ReplayRunTrace row per trace.

    Idempotent on the (tenant_id, run_id) pair via the standard
    idempotency_guard; once a run is non-pending the executor itself
    short-circuits, so retries are safe.

    Resolves the right evaluator based on the org's plan + entitlements
    so Pro gets single-judge (Haiku-4) and Team+ gets ensemble per locked
    decision #4.
    """
    task_key = f"replay:{tenant_id}:{run_id}"
    with idempotency_guard(task_key) as acquired:
        if not acquired:
            return {
                "status": "duplicate_ignored",
                "tenant_id": tenant_id,
                "run_id": run_id,
            }

        session = SessionLocal()
        try:
            set_db_tenant_context(session, tenant_id)

            # Resolve the right evaluator for this org. Resolver lookups
            # are cached (60s TTL) so this is a cheap call. Failure to
            # resolve (e.g. cache layer down) falls through to the
            # plan-code default path in get_evaluator.
            from app.services import judge_engine
            from app.services.entitlements_resolver import (
                get_plan_code,
                resolve_all,
            )
            from app.services.replay_executor import (
                ReplayBudgetTracker,
                default_resolver,
                execute_replay_run,
                make_live_llm_resolver,
            )
            from app.services.replay_runs import (
                REPLAY_MODE_REAL_LLM,
                parse_summary,
            )

            try:
                ents = resolve_all(session, tenant_id)
                plan = get_plan_code(session, tenant_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "process_replay_run.entitlements_lookup_failed tenant=%s",
                    tenant_id,
                    exc_info=True,
                )
                ents = None
                plan = None
            evaluator = judge_engine.get_evaluator(
                plan_code=plan, entitlements_dict=ents
            )

            # ── Option B: resolve replay mode + overrides from summary ────
            run = session.execute(
                select(ReplayRun).where(
                    ReplayRun.project_id == tenant_id,
                    ReplayRun.id == run_id,
                )
            ).scalar_one_or_none()
            if run is None:
                logger.warning(
                    "process_replay_run.run_not_found tenant=%s run=%s",
                    tenant_id, run_id,
                )
                return {
                    "status": "not_found",
                    "tenant_id": tenant_id,
                    "run_id": run_id,
                }

            summary = parse_summary(run.summary_json)
            replay_mode = summary.get("replay_mode", "stub")
            candidate_prompt_override = summary.get("candidate_prompt_override")
            candidate_model_override = summary.get("candidate_model_override")

            # Plan gate: real-LLM replay requires Team+ or Enterprise.
            # Pro and below fall back to stub with a warning log.
            use_live_resolver = False
            if replay_mode == REPLAY_MODE_REAL_LLM:
                from app.services.entitlements_resolver import has

                real_llm_entitled = has(
                    session, tenant_id, "pilot.real_llm_replay_enabled"
                )
                if not real_llm_entitled:
                    logger.warning(
                        "process_replay_run.plan_gate_blocked tenant=%s run=%s "
                        "plan=%s — falling back to stub resolver",
                        tenant_id, run_id, plan,
                    )
                    use_live_resolver = False
                else:
                    use_live_resolver = True

            # Budget tracker only matters when we're doing live calls.
            budget_tracker = None
            if use_live_resolver:
                from app.core.config import get_settings

                budget_usd = float(
                    get_settings().REPLAY_REAL_LLM_BUDGET_USD
                )
                budget_tracker = ReplayBudgetTracker(budget_usd=budget_usd)

            actual_output_resolver = (
                make_live_llm_resolver(
                    candidate_prompt_override=candidate_prompt_override,
                    candidate_model_override=candidate_model_override,
                    budget_tracker=budget_tracker,
                )
                if use_live_resolver
                else default_resolver
            )

            run = execute_replay_run(
                session,
                project_id=tenant_id,
                run_id=run_id,
                evaluator=evaluator,
                record_calibration=record_calibration,
                actual_output_resolver=actual_output_resolver,
                budget_tracker=budget_tracker,
            )
            if run is None:
                logger.warning(
                    "process_replay_run.run_not_found tenant=%s run=%s",
                    tenant_id, run_id,
                )
                return {
                    "status": "not_found",
                    "tenant_id": tenant_id,
                    "run_id": run_id,
                }

            # ── Auto-fix PR generation (most advanced — Enterprise) ──
            # Trigger only when a real-LLM replay with overrides fails.
            if replay_mode == REPLAY_MODE_REAL_LLM and run.status in ("fail", "error"):
                from app.services.replay_pr_dispatch import (
                    dispatch_replay_fix_pr,
                )

                try:
                    outcome = dispatch_replay_fix_pr(
                        session, replay_run=run
                    )
                    logger.info(
                        "process_replay_run.autofix_outcome tenant=%s run=%s "
                        "decision=%s pr_url=%s",
                        tenant_id,
                        run_id,
                        outcome.decision,
                        (outcome.action.pr_url or "")
                        if outcome.action
                        else None,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "process_replay_run.autofix_failed tenant=%s run=%s",
                        tenant_id, run_id,
                    )

            return {
                "status": run.status,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "summary": json.loads(run.summary_json) if run.summary_json else {},
            }
        except Exception as exc:
            session.rollback()
            retry_count = _current_retry_count(self)
            if retry_count < 2:
                logger.warning(
                    "process_replay_run.retry tenant=%s run=%s attempt=%d",
                    tenant_id, run_id, retry_count + 1,
                )
                raise self.retry(exc=exc, countdown=30)
            logger.exception(
                "process_replay_run.failed tenant=%s run=%s",
                tenant_id, run_id,
            )
            # Best-effort: mark the run as error so the dashboard stops
            # polling a pending row indefinitely.
            try:
                from app.services.replay_executor import _finalize_error  # type: ignore[attr-defined]

                run = session.execute(
                    select(ReplayRun).where(
                        ReplayRun.project_id == tenant_id,
                        ReplayRun.id == run_id,
                    )
                ).scalar_one_or_none()
                if run is not None and run.status in ("pending", "running"):
                    _finalize_error(
                        session, run, reason=f"worker_error:{type(exc).__name__}"
                    )
            except Exception:  # noqa: BLE001
                logger.debug("process_replay_run.finalize_error_failed", exc_info=True)
            return {
                "status": "error",
                "tenant_id": tenant_id,
                "run_id": run_id,
                "error_message": mask_error_message(exc),
            }
        finally:
            session.close()


# ════════════════════════════════════════════════════════════════════════════
# Module 12 — Subscription lifecycle automation (plan §11.4)
# ════════════════════════════════════════════════════════════════════════════
#
# Two beat-driven sweeps that close the gap between Stripe's event
# stream and section 11.4's locked transition rules:
#
#   * expire_trials                — application-managed (no-card) trials
#   * expire_past_due_grace        — 7-day grace cap on past_due
#
# Both tasks are thin wrappers over `services.subscription_lifecycle`.
# The actual transition logic, audit-log writes, and resolver-cache
# invalidation live in the service module so unit tests can drive the
# same code paths without Celery.
#
# Cadence: hourly. The trial-expiry worst case (one row that became
# eligible at 00:01) sees its downgrade by 01:07 — well under the
# customer-perception bound of "starts working within an hour".
#
# Idempotency: the eligibility filters in the service guarantee
# re-entry safety. Concurrent sweeps would each pick the same rows
# and the second would find the rows already transitioned. We do
# NOT add a distributed lock — the cost is one wasted SELECT per
# duplicate run, which is cheap.


@celery_app.task(
    name="app.worker.tasks.expire_trials", queue="diagnosis_fast"
)
def expire_trials(limit: int | None = None) -> dict:
    """Beat task: downgrade `trialing` subscriptions whose `trial_end`
    has passed AND that have no Stripe subscription. See
    `services.subscription_lifecycle.sweep_expired_trials` for the
    eligibility contract.

    Returns a summary dict so beat logs surface counts.
    """
    from app.services.subscription_lifecycle import sweep_expired_trials

    settings = get_settings()
    if not settings.BILLING_LIFECYCLE_SWEEP_ENABLED:
        logger.info("expire_trials: BILLING_LIFECYCLE_SWEEP_ENABLED=false — skipping")
        return {"skipped": True, "reason": "BILLING_LIFECYCLE_SWEEP_ENABLED=false"}

    effective_limit = (
        int(limit)
        if limit is not None and limit > 0
        else int(settings.BILLING_LIFECYCLE_SWEEP_LIMIT)
    )

    session = SessionLocal()
    try:
        result = sweep_expired_trials(session, limit=effective_limit)
        logger.info(
            "expire_trials.completed",
            extra={
                "event": "subscription_lifecycle",
                "task": "expire_trials",
                "examined": result.examined,
                "transitioned": result.transitioned,
                "failed": result.failed,
            },
        )
        # Strip per-row transitions from the dict to keep the Celery
        # result envelope small. Operators read counts from logs.
        out = result.to_dict()
        out.pop("transitions", None)
        return out
    finally:
        session.close()


@celery_app.task(
    name="app.worker.tasks.expire_past_due_grace", queue="diagnosis_fast"
)
def expire_past_due_grace(
    grace_days: int | None = None,
    limit: int | None = None,
) -> dict:
    """Beat task: hard-downgrade `past_due` subscriptions whose
    `current_period_end + grace_days` has passed. See
    `services.subscription_lifecycle.sweep_expired_past_due_grace`
    for the eligibility contract.

    grace_days defaults to BILLING_PAST_DUE_GRACE_DAYS (locked at 7
    per plan §11.4 binding); the kwarg exists so an operator can run
    a one-off sweep with a longer window during a Stripe outage.
    """
    from app.services.subscription_lifecycle import sweep_expired_past_due_grace

    settings = get_settings()
    if not settings.BILLING_LIFECYCLE_SWEEP_ENABLED:
        logger.info(
            "expire_past_due_grace: BILLING_LIFECYCLE_SWEEP_ENABLED=false — skipping"
        )
        return {"skipped": True, "reason": "BILLING_LIFECYCLE_SWEEP_ENABLED=false"}

    effective_grace = (
        int(grace_days)
        if grace_days is not None and grace_days >= 0
        else int(settings.BILLING_PAST_DUE_GRACE_DAYS)
    )
    effective_limit = (
        int(limit)
        if limit is not None and limit > 0
        else int(settings.BILLING_LIFECYCLE_SWEEP_LIMIT)
    )

    session = SessionLocal()
    try:
        result = sweep_expired_past_due_grace(
            session, grace_days=effective_grace, limit=effective_limit,
        )
        logger.info(
            "expire_past_due_grace.completed",
            extra={
                "event": "subscription_lifecycle",
                "task": "expire_past_due_grace",
                "grace_days": effective_grace,
                "examined": result.examined,
                "transitioned": result.transitioned,
                "failed": result.failed,
            },
        )
        out = result.to_dict()
        out.pop("transitions", None)
        return out
    finally:
        session.close()


@celery_app.task(name="app.worker.tasks.run_judge_calibration_all_projects")
def run_judge_calibration_all_projects() -> dict:
    """Beat task: run judge calibration for every active project with
    labeled golden traces.

    Idempotent per (project_id, judge_model, run_date) — the runner
    short-circuits if a complete row already exists.
    """
    from datetime import date as _date

    from sqlalchemy import select

    from app.db.models import Project
    from app.services.judge_calibration_runner import run_calibration

    settings = get_settings()
    if not settings.JUDGE_CALIBRATION_ENABLED:
        logger.info("judge_calibration_all_projects: JUDGE_CALIBRATION_ENABLED=false — skipping")
        return {"skipped": True, "reason": "JUDGE_CALIBRATION_ENABLED=false"}

    today = _date.today()
    session = SessionLocal()
    results = []
    try:
        projects = session.execute(select(Project).where(Project.active.is_(True))).scalars().all()
        for project in projects:
            set_db_tenant_context(project.id)
            try:
                run = run_calibration(
                    db=session,
                    project_id=project.id,
                    judge_model=settings.JUDGE_SINGLE_MODEL,
                )
                results.append(
                    {
                        "project_id": project.id,
                        "run_id": run.id,
                        "status": run.status,
                        "accuracy": run.accuracy,
                        "sample_count": run.sample_count,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "judge_calibration.project_failed",
                    extra={
                        "project_id": project.id,
                        "error": str(exc),
                    },
                )
                results.append(
                    {
                        "project_id": project.id,
                        "status": "error",
                        "error": str(exc),
                    }
                )
    finally:
        session.close()

    logger.info(
        "judge_calibration_all_projects.completed",
        extra={
            "event": "judge_calibration_all_projects",
            "task": "run_judge_calibration_all_projects",
            "date": str(today),
            "projects": len(results),
            "completed": sum(1 for r in results if r.get("status") == "complete"),
        },
    )
    return {"date": str(today), "results": results}


@celery_app.task(name="app.worker.tasks.run_provider_drift_watch")
def run_provider_drift_watch() -> dict:
    """Beat task: dispatch probe suite for every active model, then run
    the aggregator for today's date.

    Two-phase so probes and alerts are never in an inconsistent state:
      1. Runner: one (model, date) at a time, budget-capped.
      2. Aggregator: compute drift metrics, upsert alerts.

    Returns:
        {"runs": list of RunOutcome dicts, "aggregator": AggregatorOutcome dict}
    """
    from datetime import date as _date

    from app.services.provider_drift.aggregator import run_aggregator
    from app.services.provider_drift.models import ModelSpec
    from app.services.provider_drift.prompt_suite import load_active_prompts
    from app.services.provider_drift.runner import execute_run, load_active_models as _load_active_models

    settings = get_settings()
    if not settings.PROVIDER_DRIFT_WATCH_ENABLED:
        logger.info("run_provider_drift_watch: PROVIDER_DRIFT_WATCH_ENABLED=false — skipping")
        return {"skipped": True, "reason": "PROVIDER_DRIFT_WATCH_ENABLED=false"}

    today = _date.today()
    session = SessionLocal()
    run_results = []
    try:
        models = _load_active_models(session)
        prompts = load_active_prompts(session)
        for model_row in models:
            model_spec = ModelSpec(
                id=model_row.id,
                provider=model_row.provider,
                model_id=model_row.model_id,
                display_name=model_row.display_name,
                family=model_row.family,
                active=model_row.active,
            )
            outcome = execute_run(
                db=session,
                model_spec=model_spec,
                run_date=today,
                prompts=prompts,
                provider_client=None,
                embedder=None,
                budget_usd=settings.PROVIDER_DRIFT_WATCH_BUDGET_USD,
            )
            run_results.append({
                "run_id": outcome.run_id,
                "model_id": outcome.model_id,
                "status": outcome.status,
                "prompts_total": outcome.prompts_total,
                "prompts_ok": outcome.prompts_ok,
                "cost_usd": outcome.cost_usd,
            })

        agg = run_aggregator(db=session, current_date=today)

        logger.info(
            "provider_drift_watch.completed",
            extra={
                "event": "provider_drift_watch",
                "task": "run_provider_drift_watch",
                "date": str(today),
                "runs": len(run_results),
                "metrics_evaluated": agg.metrics_evaluated,
                "alerts_published": agg.alerts_published,
                "candidates": agg.candidates_recorded,
                "skipped": agg.skipped_for_coverage,
            },
        )

        return {
            "date": str(today),
            "runs": run_results,
            "aggregator": {
                "metrics_evaluated": agg.metrics_evaluated,
                "alerts_published": agg.alerts_published,
                "candidates_recorded": agg.candidates_recorded,
                "skipped_for_coverage": agg.skipped_for_coverage,
            },
        }
    finally:
        session.close()
