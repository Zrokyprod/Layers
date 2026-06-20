"""
Detector plugin registry.

Loads detector callables via ``importlib.metadata`` entry points
(group ``zroky.detectors``).  When the package is not installed
(e.g., bare source checkout without ``pip install -e .``), falls
back to the built-in detectors registered in ``_BUILTIN_DETECTORS``.

Usage
-----
    from app.services.detectors._registry import load_detectors
    detectors = load_detectors()          # {name: callable}
    result = detectors["token_overflow"](payload)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

# ── built-in fallback registry ────────────────────────────────────────────────
# Mirrors the entry-points declared in pyproject.toml.
# Kept in sync manually; the authoritative source is pyproject.toml.

def _builtin_detectors() -> dict[str, Callable]:
    from app.services.detectors.token_overflow import detect as detect_token_overflow
    from app.services.detectors.rate_limit import detect as detect_rate_limit
    from app.services.detectors.auth_failure import detect as detect_auth_failure
    from app.services.detectors.provider_error import detect as detect_provider_error
    from app.services.detectors.loop import detect_entry as detect_loop_entry
    from app.services.detectors.cost_spike import detect_entry as detect_cost_spike_entry
    from app.services.detectors.empty_output import detect as detect_empty_output
    from app.services.detectors.output_truncated import detect as detect_output_truncated
    from app.services.detectors.schema_violation import detect as detect_schema_violation
    from app.services.detectors.tool_failures import (
        detect_tool_argument_mismatch,
        detect_tool_call_failure,
        detect_tool_selection_failure,
    )
    from app.services.detectors.unsafe_action import detect as detect_unsafe_action
    from app.services.detectors.outcome_mismatch import detect as detect_outcome_mismatch
    from app.services.detectors.task_outcome_failure import detect as detect_task_outcome_failure
    from app.services.detectors.latency_anomaly import detect as detect_latency_anomaly
    from app.services.detectors.repeated_output import detect_entry as detect_repeated_output_entry
    from app.services.detectors.output_length_drift import detect_entry as detect_output_length_drift_entry
    from app.services.detectors.latency_drift import detect_entry as detect_latency_drift_entry
    from app.services.detectors.error_rate_drift import detect_entry as detect_error_rate_drift_entry
    from app.services.detectors.token_usage_drift import detect_entry as detect_token_usage_drift_entry
    from app.services.detectors.hallucination_risk import detect_entry as detect_hallucination_risk_entry
    from app.services.detectors.rag_grounding_failure import detect as detect_rag_grounding_failure
    from app.services.detectors.accuracy_regression import detect_entry as detect_accuracy_regression_entry
    return {
        "token_overflow": detect_token_overflow,
        "rate_limit": detect_rate_limit,
        "auth_failure": detect_auth_failure,
        "provider_error": detect_provider_error,
        "loop_detected": detect_loop_entry,
        "cost_spike": detect_cost_spike_entry,
        "empty_output": detect_empty_output,
        "output_truncated": detect_output_truncated,
        "schema_violation": detect_schema_violation,
        "tool_selection_failure": detect_tool_selection_failure,
        "tool_call_failure": detect_tool_call_failure,
        "tool_argument_mismatch": detect_tool_argument_mismatch,
        "unsafe_action": detect_unsafe_action,
        "outcome_mismatch": detect_outcome_mismatch,
        "task_outcome_failure": detect_task_outcome_failure,
        "latency_anomaly": detect_latency_anomaly,
        "repeated_output": detect_repeated_output_entry,
        "output_length_drift": detect_output_length_drift_entry,
        "latency_drift": detect_latency_drift_entry,
        "error_rate_drift": detect_error_rate_drift_entry,
        "token_usage_drift": detect_token_usage_drift_entry,
        "hallucination_risk": detect_hallucination_risk_entry,
        "rag_grounding_failure": detect_rag_grounding_failure,
        "accuracy_regression": detect_accuracy_regression_entry,
    }


def load_detectors() -> dict[str, Callable[..., dict[str, Any] | None]]:
    """Return registered detector callables keyed by entry-point name.

    Prefers ``importlib.metadata`` entry points; falls back to
    ``_builtin_detectors()`` when no entry points are registered
    (uninstalled source checkout).
    """
    try:
        from importlib.metadata import entry_points
        eps = entry_points(group="zroky.detectors")
        loaded: dict[str, Callable] = {}
        for ep in eps:
            try:
                loaded[ep.name] = ep.load()
            except Exception as exc:
                logger.warning("Failed to load detector entry point %r: %s", ep.name, exc)
        if loaded:
            logger.debug("Loaded %d detector(s) from entry points: %s", len(loaded), list(loaded))
            return loaded
    except Exception as exc:
        logger.debug("importlib.metadata unavailable (%s); using built-in detectors", exc)

    logger.debug("No entry-point detectors registered; using built-in fallback registry")
    return _builtin_detectors()
