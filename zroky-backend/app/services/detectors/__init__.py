"""
Detector plugin protocol and public re-exports.

Each detector module exposes a ``detect(payload, **kwargs)`` callable.
New detectors can be registered by satisfying the ``Detector`` Protocol.
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class Detector(Protocol):
    """Minimal interface every detector must satisfy."""

    def __call__(
        self, payload: Mapping[str, Any], **kwargs: Any
    ) -> dict[str, Any] | None:
        ...


# Re-export internal detector callables for convenience
from app.services.detectors.token_overflow import detect as detect_token_overflow  # noqa: E402
from app.services.detectors.rate_limit import detect as detect_rate_limit  # noqa: E402
from app.services.detectors.auth_failure import detect as detect_auth_failure  # noqa: E402
from app.services.detectors.provider_error import detect as detect_provider_error  # noqa: E402
from app.services.detectors.loop import detect as detect_loop  # noqa: E402
from app.services.detectors.cost_spike import detect as detect_cost_spike  # noqa: E402
from app.services.detectors.empty_output import detect as detect_empty_output  # noqa: E402
from app.services.detectors.output_truncated import detect as detect_output_truncated  # noqa: E402
from app.services.detectors.schema_violation import detect as detect_schema_violation  # noqa: E402
from app.services.detectors.latency_anomaly import detect as detect_latency_anomaly  # noqa: E402
from app.services.detectors.repeated_output import detect as detect_repeated_output  # noqa: E402
from app.services.detectors.output_length_drift import detect as detect_output_length_drift  # noqa: E402
from app.services.detectors.latency_drift import detect as detect_latency_drift  # noqa: E402
from app.services.detectors.error_rate_drift import detect as detect_error_rate_drift  # noqa: E402
from app.services.detectors.token_usage_drift import detect as detect_token_usage_drift  # noqa: E402
from app.services.detectors.hallucination_risk import detect as detect_hallucination_risk  # noqa: E402
from app.services.detectors.accuracy_regression import detect as detect_accuracy_regression  # noqa: E402
from app.services.detectors.blast_radius import build as build_blast_radius  # noqa: E402

__all__ = [
    "Detector",
    "detect_token_overflow",
    "detect_rate_limit",
    "detect_auth_failure",
    "detect_provider_error",
    "detect_loop",
    "detect_cost_spike",
    "detect_empty_output",
    "detect_output_truncated",
    "detect_schema_violation",
    "detect_latency_anomaly",
    "detect_repeated_output",
    "detect_output_length_drift",
    "detect_latency_drift",
    "detect_error_rate_drift",
    "detect_token_usage_drift",
    "detect_hallucination_risk",
    "detect_accuracy_regression",
    "build_blast_radius",
]
