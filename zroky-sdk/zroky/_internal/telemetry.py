"""
OpenTelemetry integration for the ZROKY SDK.

This module provides optional OpenTelemetry tracing integration.
Install with: pip install zroky[opentelemetry]
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

_logger = logging.getLogger(__name__)

# Try to import opentelemetry, but make it optional
try:
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind, Status, StatusCode
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    trace = None  # type: ignore[misc]

if TYPE_CHECKING:
    from zroky._internal.models import CallEvent


class OtelIntegration:
    """
    OpenTelemetry integration for ZROKY SDK.
    
    Automatically creates spans for AI provider calls and adds
    relevant attributes for observability.
    """

    def __init__(self, tracer_name: str = "zroky.sdk") -> None:
        self._tracer: Any = None
        if _OTEL_AVAILABLE:
            self._tracer = trace.get_tracer(tracer_name)
        else:
            _logger.debug("OpenTelemetry not available. Install with: pip install opentelemetry-api")

    def is_available(self) -> bool:
        """Check if OpenTelemetry is available and configured."""
        return _OTEL_AVAILABLE and self._tracer is not None

    def start_call_span(
        self,
        provider: str,
        model: str,
        call_id: str,
        *,
        parent_context: Any = None,
    ) -> Any:
        """
        Start a new span for an AI provider call.
        
        Returns the span context manager or a no-op context if OTel unavailable.
        """
        if not self.is_available():
            return _NoOpContextManager()

        attributes = {
            "zroky.provider": provider,
            "zroky.model": model,
            "zroky.call_id": call_id,
            "gen_ai.system": provider,
            "gen_ai.request.model": model,
        }

        return self._tracer.start_as_current_span(
            name=f"{provider}.{model}",
            kind=SpanKind.CLIENT,
            attributes=attributes,
        )

    def set_span_attributes_from_event(self, span: Any, event: "CallEvent") -> None:
        """Set span attributes from a CallEvent."""
        if not self.is_available() or span is None:
            return

        span.set_attribute("zroky.status", event.status)
        span.set_attribute("zroky.latency_ms", event.latency_ms)
        span.set_attribute("zroky.prompt_tokens", event.prompt_tokens)
        span.set_attribute("zroky.completion_tokens", event.completion_tokens)
        span.set_attribute("gen_ai.usage.input_tokens", event.prompt_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", event.completion_tokens)
        span.set_attribute("gen_ai.usage.total_tokens", 
                         event.prompt_tokens + event.completion_tokens)

        if event.error_code:
            span.set_attribute("zroky.error_code", event.error_code)
            span.set_status(Status(StatusCode.ERROR, event.error_code))
        else:
            span.set_status(Status(StatusCode.OK))

        if event.agent_name:
            span.set_attribute("zroky.agent_name", event.agent_name)

        if event.trace_id:
            span.set_attribute("zroky.trace_id", event.trace_id)

    def record_error(self, span: Any, error: Exception) -> None:
        """Record an exception on the span."""
        if not self.is_available() or span is None:
            return

        span.record_exception(error)
        span.set_status(Status(StatusCode.ERROR, str(error)))


class _NoOpContextManager:
    """No-op context manager for when OTel is not available."""

    def __enter__(self) -> "_NoOpContextManager":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


# Global instance
_otel_integration: OtelIntegration | None = None


def get_otel_integration() -> OtelIntegration:
    """Get the global OTel integration instance."""
    global _otel_integration
    if _otel_integration is None:
        _otel_integration = OtelIntegration()
    return _otel_integration


def set_otel_integration(integration: OtelIntegration) -> None:
    """Set a custom OTel integration instance."""
    global _otel_integration
    _otel_integration = integration
