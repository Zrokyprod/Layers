from app.worker._internal.tasks_common import *

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


__all__ = [name for name in globals() if not name.startswith("__")]
