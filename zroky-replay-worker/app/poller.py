# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Zero-trust poll loop.

The worker PULLS jobs from the control plane — it never receives pushed
payloads.  This keeps the worker deployable in a customer VPC with no
inbound firewall rules beyond egress to api.zroky.com.

Protocol:
  1. POST /v1/replay/poll  { worker_token, capacity }
     → { jobs: [...] }
  2. For each job: verify signature, run, POST /v1/replay/result
"""
from __future__ import annotations

import asyncio
import logging
import socket
from uuid import uuid4
from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.models import PollResponse, ResultPayload
from app.runner import run_job

logger = logging.getLogger(__name__)
_DEFAULT_WORKER_ID = f"{socket.gethostname()}-{uuid4().hex[:8]}"


def _worker_id(settings) -> str:
    return (settings.WORKER_ID or _DEFAULT_WORKER_ID).strip()


async def poll_loop() -> None:
    settings = get_settings()
    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)

    async with httpx.AsyncClient(
        base_url=settings.CONTROL_PLANE_URL,
        headers={"Authorization": f"Bearer {settings.WORKER_TOKEN}"},
        timeout=30,
    ) as client:
        while True:
            try:
                await _poll_once(client, semaphore, settings)
            except Exception:
                logger.exception("Poll cycle failed; retrying after backoff")
            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)


async def _poll_once(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    settings,
) -> None:
    resp = await client.post(
        "/v1/replay/poll",
        json={
            "worker_token": settings.WORKER_TOKEN,
            "worker_id": _worker_id(settings),
            "capacity": settings.MAX_CONCURRENT_JOBS,
        },
    )
    if resp.status_code == 204:
        return
    resp.raise_for_status()

    data = PollResponse.model_validate(resp.json())
    if not data.jobs:
        return

    logger.info("Received %d replay job(s)", len(data.jobs))
    tasks = [
        asyncio.create_task(_run_and_report(job, client, semaphore, settings))
        for job in data.jobs
    ]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _run_and_report(job, client, semaphore, settings) -> None:
    async with semaphore:
        logger.info("Starting replay job %s (trace=%s)", job.replay_id, job.trace_id)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_job(
                job,
                signing_key=settings.ARTIFACT_SIGNING_KEY,
                signature_required=settings.ARTIFACT_SIGNATURE_REQUIRED,
            ),
        )
        await _report_result(client, result, settings)


async def _report_result(client, result, settings) -> None:
    payload = ResultPayload(worker_token=settings.WORKER_TOKEN, worker_id=_worker_id(settings), result=result)
    try:
        resp = await client.post(
            "/v1/replay/result",
            json=payload.model_dump(mode="json"),
        )
        resp.raise_for_status()
        logger.info(
            "Reported replay %s → %s (diff_metric=%s)",
            result.replay_id,
            result.status,
            result.diff_metric,
        )
    except Exception:
        logger.exception("Failed to report result for replay %s", result.replay_id)
