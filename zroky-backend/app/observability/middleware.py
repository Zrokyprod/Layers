from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from app.core.config import get_settings
from app.observability.context import (
    reset_request_context,
    set_request_context,
)
from app.observability.metrics import record_http_request

logger = logging.getLogger(__name__)
REQUEST_ID_HEADER = "X-Request-Id"
CORRELATION_ID_HEADER = "X-Correlation-Id"


def install_observability_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_observability_middleware(request: Request, call_next):
        settings = get_settings()
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())

        # Correlation ID: use provided header, or fall back to request_id for new traces
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or request_id

        tenant_id = (
            request.headers.get(settings.TENANT_HEADER_NAME)
            or request.headers.get(settings.LEGACY_TENANT_HEADER_NAME)
            or "-"
        )

        context_tokens = set_request_context(
            request_id=request_id,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )
        started_at = perf_counter()
        response: Response | None = None
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            try:
                elapsed_seconds = perf_counter() - started_at
                route = request.scope.get("route")
                path_label = route.path if route and getattr(route, "path", None) else request.url.path

                record_http_request(
                    method=request.method,
                    path=path_label,
                    status_code=status_code,
                    duration_seconds=elapsed_seconds,
                )

                # Include correlation_id in all request logs for distributed tracing
                logger.info(
                    "http_request_completed",
                    extra={
                        "event": "http_request",
                        "request_id": request_id,
                        "correlation_id": correlation_id,
                        "tenant_id": tenant_id,
                        "method": request.method,
                        "path": path_label,
                        "status_code": status_code,
                        "duration_ms": round(elapsed_seconds * 1000, 2),
                    },
                )

                if response is not None:
                    response.headers.setdefault(REQUEST_ID_HEADER, request_id)
                    response.headers.setdefault(CORRELATION_ID_HEADER, correlation_id)
            finally:
                reset_request_context(context_tokens)
