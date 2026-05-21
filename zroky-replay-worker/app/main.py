# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""zroky-replay-worker — FastAPI process entry point.

Starts the background poll loop on startup and exposes:
  GET /health    → liveness probe
  GET /ready     → readiness (WORKER_TOKEN configured)
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


@app.on_event("startup")
async def _start_poll_loop() -> None:
    global _poll_task
    if not settings.WORKER_TOKEN:
        logger.warning("WORKER_TOKEN not set — poll loop disabled (dev mode)")
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
    configured = bool(settings.WORKER_TOKEN)
    return JSONResponse(
        {"ready": configured, "control_plane": settings.CONTROL_PLANE_URL},
        status_code=200 if configured else 503,
    )
