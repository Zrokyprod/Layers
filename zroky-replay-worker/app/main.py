# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""zroky-replay-worker — FastAPI process entry point.

Starts the background poll loop on startup and exposes:
  GET /health    → liveness probe
  GET /ready     → readiness (worker token and artifact trust configured)
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.poller import poll_loop

settings = get_settings()
logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Zroky Replay Worker",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

_poll_task: asyncio.Task | None = None


def _readiness() -> tuple[bool, dict[str, object]]:
    token_configured = bool(settings.WORKER_TOKEN)
    signing_key_configured = bool(settings.ARTIFACT_SIGNING_KEY)
    signing_ready = signing_key_configured or not settings.ARTIFACT_SIGNATURE_REQUIRED
    ready = token_configured and signing_ready
    return ready, {
        "ready": ready,
        "control_plane": settings.CONTROL_PLANE_URL,
        "worker_token_configured": token_configured,
        "artifact_signature_required": settings.ARTIFACT_SIGNATURE_REQUIRED,
        "artifact_signing_key_configured": signing_key_configured,
    }


@app.on_event("startup")
async def _start_poll_loop() -> None:
    global _poll_task
    ready, state = _readiness()
    if not ready:
        logger.warning("Replay worker not ready — poll loop disabled: %s", state)
        return
    _poll_task = asyncio.create_task(poll_loop())
    logger.info(
        "Replay worker started; polling %s every %ds",
        settings.CONTROL_PLANE_URL,
        settings.POLL_INTERVAL_SECONDS,
    )


@app.on_event("shutdown")
async def _stop_poll_loop() -> None:
    if _poll_task is not None:
        _poll_task.cancel()
        try:
            await _poll_task
        except asyncio.CancelledError:
            pass


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/ready")
def ready() -> JSONResponse:
    configured, state = _readiness()
    return JSONResponse(state, status_code=200 if configured else 503)
