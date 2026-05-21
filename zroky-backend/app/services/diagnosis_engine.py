"""
diagnosis_engine — thin orchestrator.

All detector logic lives in app.services.detectors.*
This module owns the public API surface and the fan-out / result-assembly logic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.detectors import (
    build_blast_radius,
    detect_accuracy_regression,
    detect_auth_failure,
    detect_cost_spike,
    detect_empty_output,
    detect_error_rate_drift,
    detect_hallucination_risk,
    detect_latency_anomaly,
    detect_latency_drift,
    detect_loop,
    detect_output_length_drift,
    detect_output_truncated,
    detect_provider_error,
    detect_rate_limit,
    detect_repeated_output,
    detect_schema_violation,
    detect_token_overflow,
    detect_token_usage_drift,
)
from app.services.detectors.token_overflow import (
    TOKEN_OVERFLOW_ESTIMATE_THRESHOLD_RATIO,
)

RULE_CONFIDENCE: dict[str, float] = {
    "TOKEN_OVERFLOW": 0.98,
    "RATE_LIMIT": 0.95,
    "AUTH_FAILURE": 0.99,
    "PROVIDER_ERROR": 0.82,
    "LOOP_DETECTED": 0.92,
    "COST_SPIKE": 0.90,
    "EMPTY_OUTPUT": 0.99,
    "OUTPUT_TRUNCATED": 0.98,
    "SCHEMA_VIOLATION": 0.95,
    "LATENCY_ANOMALY": 0.90,
    "REPEATED_OUTPUT": 0.92,
    "OUTPUT_LENGTH_DRIFT": 0.88,
    "LATENCY_DRIFT": 0.88,
    "ERROR_RATE_DRIFT": 0.92,
    "TOKEN_USAGE_DRIFT": 0.88,
    "HALLUCINATION_RISK": 0.90,
    "ACCURACY_REGRESSION": 0.90,
}

FAST_RULE_CATEGORIES = (
    "TOKEN_OVERFLOW",
    "RATE_LIMIT",
    "AUTH_FAILURE",
    "PROVIDER_ERROR",
    "EMPTY_OUTPUT",
    "OUTPUT_TRUNCATED",
    "SCHEMA_VIOLATION",
    "LATENCY_ANOMALY",
)
PATTERN_RULE_CATEGORIES = (
    "LOOP_DETECTED",
    "COST_SPIKE",
    "REPEATED_OUTPUT",
    "OUTPUT_LENGTH_DRIFT",
    "LATENCY_DRIFT",
    "ERROR_RATE_DRIFT",
    "TOKEN_USAGE_DRIFT",
    "HALLUCINATION_RISK",
    "ACCURACY_REGRESSION",
)


def evaluate_fast_rules(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    diagnoses: list[dict[str, Any]] = []

    # ── Error-class fast rules ────────────────────────────────────────────
    # These describe the call FAILING at the transport / token / auth layer.
    token_overflow = detect_token_overflow(payload)
    if token_overflow is not None:
        diagnoses.append(token_overflow)

    rate_limit = detect_rate_limit(payload)
    if rate_limit is not None:
        diagnoses.append(rate_limit)

    auth_failure = detect_auth_failure(payload)
    if auth_failure is not None:
        diagnoses.append(auth_failure)

    # provider_error is the *fallback* for any failed call that did not
    # match a more-specific error rule above. Preserved semantic from v1.
    if not diagnoses:
        provider_error = detect_provider_error(payload)
        if provider_error is not None:
            diagnoses.append(provider_error)

    # ── Output-quality fast rules ─────────────────────────────────────────
    # These describe issues with the *successful* response payload — they
    # run independently of the error fallback above so a call can carry
    # both an error diagnosis and (separately) an output-quality finding.
    empty_output = detect_empty_output(payload)
    if empty_output is not None:
        diagnoses.append(empty_output)

    output_truncated = detect_output_truncated(payload)
    if output_truncated is not None:
        diagnoses.append(output_truncated)

    schema_violation = detect_schema_violation(payload)
    if schema_violation is not None:
        diagnoses.append(schema_violation)

    # ── Performance fast rule ─────────────────────────────────────────────
    latency_anomaly = detect_latency_anomaly(payload)
    if latency_anomaly is not None:
        diagnoses.append(latency_anomaly)

    return diagnoses


def evaluate_pattern_rules(
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    current_time = now or datetime.now(timezone.utc)

    diagnoses: list[dict[str, Any]] = []
    informational: list[dict[str, Any]] = []

    loop_detected = detect_loop(payload, current_time)
    if loop_detected is not None:
        diagnoses.append(loop_detected)

    cost_spike, cost_info = detect_cost_spike(payload)
    if cost_spike is not None:
        diagnoses.append(cost_spike)
    if cost_info is not None:
        informational.append(cost_info)

    # REPEATED_OUTPUT is suppressed when LOOP_DETECTED already fired —
    # the two signals overlap and reporting both is noisy. Loop detection
    # is the higher-fidelity signal because it considers `no_progress`
    # and tool-cycle evidence in addition to output repetition.
    if loop_detected is None:
        repeated_output = detect_repeated_output(payload)
        if repeated_output is not None:
            diagnoses.append(repeated_output)

    # ── Layer 2 statistical-baseline drift detectors ──────────────────────
    # Each requires baseline values to be injected upstream by the analytics
    # pipeline (history_calls, history_days, baseline_*). When baselines
    # are absent or warmup is unmet, these silently no-op.
    output_length_drift = detect_output_length_drift(payload)
    if output_length_drift is not None:
        diagnoses.append(output_length_drift)

    latency_drift = detect_latency_drift(payload)
    if latency_drift is not None:
        diagnoses.append(latency_drift)

    error_rate_drift = detect_error_rate_drift(payload)
    if error_rate_drift is not None:
        diagnoses.append(error_rate_drift)

    token_usage_drift = detect_token_usage_drift(payload)
    if token_usage_drift is not None:
        diagnoses.append(token_usage_drift)

    # ── Layer 3 judge-engine bridge ───────────────────────────────────────
    # When the upstream pipeline ran a judge call (replay run / shadow judge
    # / inline grader) and attached the verdict + dimensions to the payload,
    # these two detectors translate judge output into anomaly categories.
    # Both silent no-op when no judge data is present.
    hallucination_risk = detect_hallucination_risk(payload)
    if hallucination_risk is not None:
        diagnoses.append(hallucination_risk)

    accuracy_regression = detect_accuracy_regression(payload)
    if accuracy_regression is not None:
        diagnoses.append(accuracy_regression)

    return diagnoses, informational


def build_diagnosis_result(
    *,
    payload: Mapping[str, Any],
    fast_diagnoses: list[dict[str, Any]],
    pattern_diagnoses: list[dict[str, Any]],
    informational: list[dict[str, Any]],
) -> dict[str, Any]:
    combined = [*fast_diagnoses, *pattern_diagnoses]
    result: dict[str, Any] = {
        "diagnosis_contract_version": "v1",
        "diagnoses": combined,
        "diagnosis_count": len(combined),
        "speed_classes": {
            "fast": list(FAST_RULE_CATEGORIES),
            "pattern": list(PATTERN_RULE_CATEGORIES),
            "targets": {
                "fast_p95_seconds": 5,
                "pattern_p95_seconds": 30,
            },
        },
    }

    if informational:
        result["informational"] = informational

    blast_radius = build_blast_radius(payload)
    if blast_radius is not None:
        result["blast_radius"] = blast_radius

    return result


def evaluate_diagnosis_payload(
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    fast_diagnoses = evaluate_fast_rules(payload)
    pattern_diagnoses, informational = evaluate_pattern_rules(payload, now=now)
    return build_diagnosis_result(
        payload=payload,
        fast_diagnoses=fast_diagnoses,
        pattern_diagnoses=pattern_diagnoses,
        informational=informational,
    )
