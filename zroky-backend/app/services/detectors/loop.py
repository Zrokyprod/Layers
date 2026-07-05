"""LOOP_DETECTED pattern-rule detector."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

from app.services.loop_signals import DEFAULT_LOOP_WINDOW_SIZE
from app.services.detectors._payload import (
    _as_bool,
    _as_float,
    _as_int,
    _as_str,
    _error_snippet,
    _parse_datetime,
    _pick,
)


def detect(payload: Mapping[str, Any], now: datetime) -> dict[str, Any] | None:
    return _detect_loop(payload, now)


def detect_entry(payload: Mapping[str, Any], **kwargs: Any) -> dict[str, Any] | None:
    """Protocol-compatible shim for importlib.metadata entry-point registration.
    Accepts optional ``now`` kwarg; defaults to current UTC time."""
    from datetime import timezone
    now = kwargs.get("now") or datetime.now(timezone.utc)
    return _detect_loop(payload, now)


def _detect_loop(payload: Mapping[str, Any], now: datetime) -> dict[str, Any] | None:
    agent_name = _as_str(
        _pick(payload, ("agent_name",), ("loop", "agent_name")), fallback="unknown",
    )
    signature = _as_str(
        _pick(payload, ("prompt_fingerprint",), ("loop", "prompt_fingerprint")),
        fallback="unknown",
    )
    repeat_count = _as_int(_pick(payload, ("loop", "repeat_count"), ("repeat_count",)))
    repeat_window_seconds = _as_int(
        _pick(payload, ("loop", "window_seconds"), ("repeat_window_seconds",)), fallback=90,
    )
    tool_chain_cycles = _as_int(
        _pick(payload, ("loop", "tool_chain_repeat_cycles"), ("tool_chain_repeat_cycles",)),
    )
    tool_window_seconds = _as_int(
        _pick(payload, ("loop", "tool_window_seconds"), ("tool_window_seconds",)), fallback=120,
    )
    no_progress = _as_bool(_pick(payload, ("loop", "no_progress"), ("no_progress",)), fallback=False)
    loop_window_size = _as_int(
        _pick(payload, ("loop", "loop_window_size"), ("loop_window_size",)),
        fallback=DEFAULT_LOOP_WINDOW_SIZE,
    )
    loop_resolved = _as_bool(
        _pick(payload, ("loop", "loop_resolved"), ("loop_resolved",)), fallback=False,
    )
    if loop_resolved:
        return None

    guard_reason = _loop_false_positive_guard(payload, now)
    if guard_reason is not None:
        return None

    no_progress_reasons_raw = _pick(payload, ("loop", "no_progress_reasons"))
    no_progress_reasons = (
        [_as_str(r) for r in no_progress_reasons_raw if _as_str(r)]
        if isinstance(no_progress_reasons_raw, list) else []
    )

    sample_timestamps_raw = _pick(payload, ("loop", "sample_timestamps"))
    sample_timestamps = (
        [_as_str(v) for v in sample_timestamps_raw if _as_str(v)]
        if isinstance(sample_timestamps_raw, list) else []
    )

    error_pattern_raw = _pick(payload, ("loop", "error_pattern"))
    error_pattern = error_pattern_raw if isinstance(error_pattern_raw, Mapping) else {}
    output_pattern_raw = _pick(payload, ("loop", "output_pattern"))
    output_pattern = output_pattern_raw if isinstance(output_pattern_raw, Mapping) else {}
    tool_cycle_raw = _pick(payload, ("loop", "tool_cycle"))
    tool_cycle = tool_cycle_raw if isinstance(tool_cycle_raw, Mapping) else {}
    retry_pattern_raw = _pick(payload, ("loop", "retry_pattern"))
    retry_pattern = retry_pattern_raw if isinstance(retry_pattern_raw, Mapping) else {}
    retry_metadata_raw = _pick(payload, ("retry_metadata",), ("retry",))
    retry_metadata = retry_metadata_raw if isinstance(retry_metadata_raw, Mapping) else {}

    output_repeat_count = _as_int(
        output_pattern.get("repeat_count") or _pick(payload, ("output_repeat_count",)),
    )
    output_fingerprint = _as_str(
        output_pattern.get("output_fingerprint") or _pick(payload, ("output_fingerprint",)),
    )
    output_similarity = _as_float(output_pattern.get("output_similarity_score"))
    near_repeated_output = _as_bool(
        output_pattern.get("near_repeated_output"), fallback=output_similarity >= 0.72,
    )
    tool_cycle_repeat_count = _as_int(tool_cycle.get("repeat_count") or tool_chain_cycles)
    tool_state_changed = _as_bool(tool_cycle.get("state_changed"), fallback=False)
    retry_count = _as_int(
        retry_pattern.get("retry_count")
        or retry_metadata.get("retry_count")
        or _pick(payload, ("retry_count",)),
    )
    repeated_retry_reason_count = _as_int(retry_pattern.get("dominant_retry_reason_count"))
    max_steps_reached = _as_bool(
        retry_metadata.get("max_steps_reached") or _pick(payload, ("max_steps_reached",)),
        fallback=False,
    )
    retry_suppression_applied = _as_bool(
        _pick(payload, ("loop", "retry_suppression_applied")), fallback=False,
    )

    exact_output_repeat = bool(
        output_fingerprint and output_repeat_count >= 3 and repeat_count >= 3,
    )
    similar_output_repeat = bool(
        near_repeated_output and output_similarity >= 0.72 and repeat_count >= 3,
    )
    output_signal_key = (
        "output_fingerprint" if exact_output_repeat
        else "output_similarity" if similar_output_repeat
        else None
    )
    tool_cycle_detected = (
        tool_cycle_repeat_count >= 3 and tool_window_seconds > 0 and not tool_state_changed
    )

    simple_prompt_repeat = (
        repeat_count >= 3
        and repeat_window_seconds > 0
        and repeat_window_seconds <= 300
    )
    simple_tool_cycle = (
        tool_cycle_repeat_count >= 3
        and tool_window_seconds > 0
        and tool_window_seconds <= 300
        and not tool_state_changed
    )

    score_result = _loop_score(
        prompt_repeat=simple_prompt_repeat,
        output_signal=output_signal_key,
        tool_cycle_repeat=tool_cycle_detected or simple_tool_cycle,
        retry_pattern=retry_count >= 3 and (repeated_retry_reason_count >= 3 or max_steps_reached),
        no_progress=no_progress,
    )
    loop_score = score_result["score"]
    detected_by = score_result["detected_by"]
    score_breakdown = score_result["breakdown"]
    if loop_score < 0.65 or not detected_by:
        return None

    confidence_level = _loop_confidence_level(loop_score)
    dominant_pattern = _loop_dominant_pattern(
        detected_by=detected_by,
        output_fingerprint=output_fingerprint,
        tool_cycle=tool_cycle,
        retry_pattern=retry_pattern,
        repeat_count=repeat_count,
    )
    return {
        "category": "LOOP_DETECTED",
        "speed_class": "pattern",
        "confidence": loop_score,
        "confidence_level": confidence_level,
        "detected_by": detected_by[0],
        "root_cause": (
            "Multi-signal loop detected"
            f" for agent {agent_name} with signature {signature}"
            f" (score={loop_score:.2f}, signals={','.join(detected_by)})."
        ),
        "fix": {
            "primary": "Add a no-progress guard using input, output, tool, and retry signatures.",
            "code": (
                "if loop_score(input_sig, output_sig, tool_sig, retry_sig) >= 0.65:\n"
                "    break_loop_and_emit_guardrail()"
            ),
            "alternative": "Add max-step limits and require state-change proof before repeating tools.",
        },
        "evidence": {
            "detected_by": detected_by,
            "loop_score": loop_score,
            "loop_score_breakdown": score_breakdown,
            "confidence": loop_score,
            "confidence_level": confidence_level,
            "dominant_pattern": dominant_pattern,
            "loop_window_size": loop_window_size,
            "loop_resolved": False,
            "agent_name": agent_name,
            "prompt_fingerprint": signature,
            "repeat_count": repeat_count,
            "repeat_window_seconds": repeat_window_seconds,
            "output_fingerprint": output_fingerprint or None,
            "output_repeat_count": output_repeat_count,
            "output_similarity_score": output_similarity,
            "near_repeated_output": near_repeated_output,
            "tool_chain_repeat_cycles": tool_cycle_repeat_count,
            "tool_window_seconds": tool_window_seconds,
            "tool_name": _tool_name_from_pattern(tool_cycle),
            "retry_count": retry_count,
            "retry_reason": _as_str(
                retry_pattern.get("dominant_retry_reason") or retry_metadata.get("retry_reason"),
            ) or None,
            "max_steps_reached": max_steps_reached,
            "no_progress": no_progress,
            "no_progress_reasons": no_progress_reasons,
            "retry_suppression_applied": retry_suppression_applied,
            "sample_timestamps": sample_timestamps,
            "output_pattern": {
                "output_fingerprint": output_fingerprint or None,
                "repeat_count": output_repeat_count,
                "stagnant_output": _as_bool(output_pattern.get("stagnant_output"), fallback=False),
                "output_similarity_score": output_similarity,
                "near_repeated_output": near_repeated_output,
            },
            "tool_cycle": {
                "dominant_pattern": _as_str(tool_cycle.get("dominant_pattern")) or None,
                "pattern_type": _as_str(tool_cycle.get("pattern_type")) or None,
                "repeat_count": tool_cycle_repeat_count,
                "tool_sequence": (
                    tool_cycle.get("tool_sequence")
                    if isinstance(tool_cycle.get("tool_sequence"), list) else []
                ),
                "state_changed": tool_state_changed,
                "state_change_count": _as_int(tool_cycle.get("state_change_count")),
                "no_state_change_count": _as_int(tool_cycle.get("no_state_change_count")),
            },
            "retry_pattern": {
                "retry_count": retry_count,
                "dominant_retry_reason": _as_str(retry_pattern.get("dominant_retry_reason")) or None,
                "dominant_retry_reason_count": repeated_retry_reason_count,
            },
            "error_pattern": {
                "dominant_error": _error_snippet(
                    _as_str(error_pattern.get("dominant_error"), fallback=""),
                ),
                "dominant_error_count": _as_int(error_pattern.get("dominant_error_count")),
                "failure_count": _as_int(error_pattern.get("failure_count")),
                "useless_output_count": _as_int(error_pattern.get("useless_output_count")),
                "stagnant_output": _as_bool(error_pattern.get("stagnant_output"), fallback=False),
            },
            "cooldown_seconds": 600,
            "threshold_agent_repeat_count": 5,
            "threshold_agent_window_seconds": 90,
            "threshold_tool_chain_cycles": 3,
            "threshold_tool_window_seconds": 120,
            "threshold_output_similarity_score": 0.72,
        },
    }


def _loop_false_positive_guard(payload: Mapping[str, Any], now: datetime) -> str | None:
    if _as_bool(
        _pick(payload, ("loop", "user_driven_repetition"), ("user_driven_repetition",)),
        fallback=False,
    ):
        return "user_driven_repetition"
    if _as_bool(
        _pick(payload, ("loop", "legitimate_repeated_output"), ("legitimate_repeated_output",)),
        fallback=False,
    ):
        return "legitimate_repeated_output"
    if _as_bool(
        _pick(payload, ("loop", "idempotent_retry"), ("idempotent_retry",)), fallback=False,
    ):
        return "idempotent_retry"

    known_sdk_retry = _as_bool(
        _pick(payload, ("retry", "is_sdk_retry"), ("is_sdk_retry",)), fallback=False,
    )
    if known_sdk_retry:
        return "known_sdk_retry"

    last_fired_raw = _pick(payload, ("loop", "last_fired_at"), ("last_loop_detected_at",))
    last_fired_at = _parse_datetime(last_fired_raw)
    if last_fired_at and now - last_fired_at < timedelta(minutes=10):
        return "cooldown_active"
    return None


def _loop_score(
    *,
    prompt_repeat: bool,
    output_signal: str | None,
    tool_cycle_repeat: bool,
    retry_pattern: bool,
    no_progress: bool,
) -> dict[str, Any]:
    weights = {
        "prompt_repeat": 0.70,
        "output_fingerprint": 0.35,
        "tool_cycle": 0.75,
        "retry_pattern": 0.15,
    }
    detected_by: list[str] = []
    breakdown = {
        "prompt_repeat": 0.0,
        "output": 0.0,
        "tool_cycle": 0.0,
        "retry_pattern": 0.0,
        "no_progress_bonus": 0.0,
    }
    score = 0.0
    if prompt_repeat:
        breakdown["prompt_repeat"] = weights["prompt_repeat"]
        score += breakdown["prompt_repeat"]
        detected_by.append("prompt_repeat")
    if output_signal:
        breakdown["output"] = weights["output_fingerprint"]
        score += breakdown["output"]
        detected_by.append(output_signal)
    if tool_cycle_repeat:
        breakdown["tool_cycle"] = weights["tool_cycle"]
        score += breakdown["tool_cycle"]
        detected_by.append("tool_cycle")
    if retry_pattern:
        breakdown["retry_pattern"] = weights["retry_pattern"]
        score += breakdown["retry_pattern"]
        detected_by.append("retry_pattern")
    if no_progress and len(detected_by) >= 2:
        breakdown["no_progress_bonus"] = 0.10
        score += breakdown["no_progress_bonus"]
    return {
        "score": round(min(score, 0.97), 2),
        "detected_by": detected_by,
        "breakdown": {key: round(value, 2) for key, value in breakdown.items()},
    }


def _loop_confidence_level(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


def _loop_dominant_pattern(
    *,
    detected_by: list[str],
    output_fingerprint: str,
    tool_cycle: Mapping[str, Any],
    retry_pattern: Mapping[str, Any],
    repeat_count: int,
) -> str:
    if "tool_cycle" in detected_by:
        pattern = _as_str(tool_cycle.get("dominant_pattern"))
        return pattern or "repeated tool cycle"
    if "output_fingerprint" in detected_by:
        return f"repeated output_fingerprint:{output_fingerprint[:12]}"
    if "output_similarity" in detected_by:
        return "near-repeated output content"
    if "retry_pattern" in detected_by:
        reason = _as_str(retry_pattern.get("dominant_retry_reason"), fallback="same outcome")
        return f"retry loop:{reason}"
    return f"prompt_repeat:{repeat_count}"


def _tool_name_from_pattern(tool_cycle: Mapping[str, Any]) -> str | None:
    pattern = _as_str(tool_cycle.get("dominant_pattern"))
    if not pattern:
        sequence = tool_cycle.get("tool_sequence")
        if isinstance(sequence, list) and sequence:
            return _as_str(sequence[-1]) or None
        return None
    return pattern.split(":", 1)[0].split("->", 1)[0] or None
