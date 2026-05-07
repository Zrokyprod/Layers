"""HTTP client utilities with correlation-id propagation for distributed tracing."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx

from app.observability.context import get_correlation_id

logger = logging.getLogger(__name__)
CORRELATION_ID_HEADER = "X-Correlation-Id"


def _inject_correlation_id(headers: dict[str, str] | None) -> dict[str, str]:
    """Inject correlation_id into outgoing request headers for distributed tracing."""
    correlation_id = get_correlation_id()
    if correlation_id and correlation_id != "-":
        headers = headers or {}
        headers.setdefault(CORRELATION_ID_HEADER, correlation_id)
    return headers or {}


@asynccontextmanager
async def async_http_client(**kwargs: Any):
    """Async HTTP client context manager with correlation-id propagation.

    Usage:
        async with async_http_client() as client:
            resp = await client.get("https://api.example.com/health")
    """
    headers = _inject_correlation_id(kwargs.pop("headers", None))
    async with httpx.AsyncClient(headers=headers, **kwargs) as client:
        yield client


def sync_http_client(**kwargs: Any) -> httpx.Client:
    """Sync HTTP client factory with correlation-id propagation.

    Usage:
        with sync_http_client() as client:
            resp = client.get("https://api.example.com/health")
    """
    headers = _inject_correlation_id(kwargs.pop("headers", None))
    return httpx.Client(headers=headers, **kwargs)
