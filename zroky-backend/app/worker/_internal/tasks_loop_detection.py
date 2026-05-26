from app.worker._internal.tasks_common import *
from app.worker._internal.tasks_utils import *

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
    # UTCDateTime column type normalizes tz across backends â€” pass through.
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


__all__ = [name for name in globals() if not name.startswith("__")]
