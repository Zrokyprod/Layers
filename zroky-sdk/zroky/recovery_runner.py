# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Customer-hosted recovery runner."""
from __future__ import annotations

import hashlib
import os
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from zroky._internal.config import load_config
from zroky._runner import (
    DEFAULT_RUNNER_ADAPTERS,
    EnvCredentialResolver,
    RunnerAdapter,
    RunnerExecutionContext,
    ZrokyRunnerError,
    _api_headers,
    _redact,
)

_REQUEST_TIMEOUT_S = 30.0


def recovery_step_idempotency_key(plan_digest: str, step_key: str) -> str:
    return hashlib.sha256(f"{plan_digest}:{step_key}".encode()).hexdigest()


def _step_key(step: Mapping[str, Any], index: int) -> str:
    value = step.get("step_key") or step.get("key") or step.get("effect_key")
    return str(value).strip() if value else f"step_{index + 1}"


def _step_plan(step: Mapping[str, Any]) -> dict[str, Any]:
    nested = step.get("execution_plan")
    plan = dict(nested) if isinstance(nested, Mapping) else dict(step)
    operation = str(plan.get("operation") or "").strip()
    if not plan.get("adapter"):
        plan["adapter"] = "stripe_refund" if operation.startswith("refund.") else "generic_rest"
    return plan


def _plan_steps(recovery_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    plan = recovery_plan.get("plan")
    if isinstance(plan, Mapping) and isinstance(plan.get("steps"), list):
        return [dict(item) for item in plan["steps"] if isinstance(item, Mapping)]
    if isinstance(plan, Mapping):
        return [dict(plan)]
    if isinstance(recovery_plan.get("steps"), list):
        return [dict(item) for item in recovery_plan["steps"] if isinstance(item, Mapping)]
    return []


class RecoveryRunner:
    def __init__(
        self,
        *,
        executor_ref: str,
        api_key: str | None = None,
        project: str | None = None,
        api_base: str | None = None,
        credential_resolver: EnvCredentialResolver | None = None,
        adapters: Mapping[str, RunnerAdapter] | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = _REQUEST_TIMEOUT_S,
        lease_seconds: int = 300,
    ) -> None:
        config = load_config(api_key=api_key, project=project, ingest_url=api_base)
        if not config.api_key or not config.project:
            raise ZrokyRunnerError("RecoveryRunner requires api_key and project.")
        self.executor_ref = executor_ref
        self.api_key = config.api_key
        self.project = config.project
        self.api_base = config.ingest_url.rstrip("/")
        self.credential_resolver = credential_resolver or EnvCredentialResolver()
        self.adapters = {**DEFAULT_RUNNER_ADAPTERS, **dict(adapters or {})}
        self.transport = transport
        self.timeout_seconds = timeout_seconds
        self.lease_seconds = lease_seconds

    def claim_once(self) -> dict[str, Any] | None:
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.post(
                f"{self.api_base}/v1/recovery/dispatch/claim",
                headers=_api_headers(self.api_key, self.project),
                json={"executor_ref": self.executor_ref, "lease_seconds": self.lease_seconds},
            )
        if response.status_code == 404:
            return None
        if response.status_code >= 300:
            raise ZrokyRunnerError(
                f"Recovery claim failed with HTTP {response.status_code}: {response.text[:300]}"
            )
        data = response.json()
        if not isinstance(data, dict):
            raise ZrokyRunnerError("Recovery claim returned invalid response shape.")
        return data

    def heartbeat(self, dispatch: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "outbox_job_id": dispatch["outbox_job_id"],
            "fencing_token": dispatch["fencing_token"],
            "lease_seconds": self.lease_seconds,
        }
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.post(
                f"{self.api_base}/v1/recovery/dispatch/heartbeat",
                headers=_api_headers(self.api_key, self.project),
                json=payload,
            )
        if response.status_code >= 300:
            raise ZrokyRunnerError(
                f"Recovery heartbeat failed with HTTP {response.status_code}: {response.text[:300]}"
            )
        data = response.json()
        return data if isinstance(data, dict) else {}

    def complete(
        self,
        dispatch: Mapping[str, Any],
        *,
        overall: str,
        step_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.post(
                f"{self.api_base}/v1/recovery/dispatch/complete",
                headers=_api_headers(self.api_key, self.project),
                json={
                    "outbox_job_id": dispatch["outbox_job_id"],
                    "fencing_token": dispatch["fencing_token"],
                    "overall": overall,
                    "step_results": _redact(step_results),
                },
            )
        if response.status_code >= 300:
            raise ZrokyRunnerError(
                f"Recovery complete failed with HTTP {response.status_code}: {response.text[:300]}"
            )
        data = response.json()
        return data if isinstance(data, dict) else {}

    def run_once(self, *, send_heartbeats: bool = True) -> dict[str, Any]:
        dispatch = self.claim_once()
        if dispatch is None:
            return {"claimed": False, "status": "idle"}
        stop_event = threading.Event()
        heartbeat_thread = None
        if send_heartbeats:
            heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                args=(dispatch, stop_event),
                daemon=True,
            )
            heartbeat_thread.start()
        try:
            overall, step_results = self._execute_dispatch(dispatch)
            completed = self.complete(dispatch, overall=overall, step_results=step_results)
            return {"claimed": True, "status": overall, "dispatch": completed}
        finally:
            stop_event.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=1.0)

    def run_daemon(
        self,
        *,
        poll_interval_seconds: float = 30.0,
        max_iterations: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> dict[str, Any]:
        stats = {
            "iterations": 0,
            "claimed": 0,
            "idle": 0,
            "failed": 0,
            "succeeded": 0,
            "ambiguous": 0,
        }
        while max_iterations is None or stats["iterations"] < max_iterations:
            stats["iterations"] += 1
            result = self.run_once()
            status = str(result.get("status") or "unknown")
            if result.get("claimed"):
                stats["claimed"] += 1
                if status in {"succeeded", "failed", "ambiguous"}:
                    stats[status] += 1
            else:
                stats["idle"] += 1
                sleep(poll_interval_seconds)
        return stats

    def _heartbeat_loop(self, dispatch: Mapping[str, Any], stop_event: threading.Event) -> None:
        interval = max(1.0, float(self.lease_seconds) / 3.0)
        while not stop_event.wait(interval):
            self.heartbeat(dispatch)

    def _execute_dispatch(self, dispatch: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        recovery_plan = dispatch.get("recovery_plan")
        if not isinstance(recovery_plan, Mapping):
            raise ZrokyRunnerError("Recovery dispatch missing recovery_plan.")
        signed_payload = dispatch.get("signed_payload")
        plan_digest = str(
            signed_payload.get("plan_digest")
            if isinstance(signed_payload, Mapping)
            else ""
        )
        if not plan_digest:
            raise ZrokyRunnerError("Recovery dispatch missing plan_digest.")
        steps = _plan_steps(recovery_plan)
        step_results: list[dict[str, Any]] = []
        for index, step in enumerate(steps):
            key = _step_key(step, index)
            try:
                detail = self._execute_step(dispatch, step, key, plan_digest)
            except httpx.TimeoutException as exc:
                step_results.append(
                    {"step_key": key, "status": "failed", "detail": {"error": str(exc)}}
                )
                return "ambiguous", step_results
            except Exception as exc:  # noqa: BLE001
                step_results.append(
                    {"step_key": key, "status": "failed", "detail": {"error": str(exc)}}
                )
                return "failed", step_results
            step_results.append({"step_key": key, "status": "succeeded", "detail": detail})
        return "succeeded", step_results

    def _execute_step(
        self,
        dispatch: Mapping[str, Any],
        step: Mapping[str, Any],
        step_key: str,
        plan_digest: str,
    ) -> dict[str, Any]:
        plan = _step_plan(step)
        adapter_name = str(plan.get("adapter") or "").strip()
        adapter = self.adapters.get(adapter_name)
        if adapter is None:
            raise ZrokyRunnerError(f"Unsupported recovery adapter: {adapter_name}.")
        credential_ref = str(plan.get("credential_ref") or step.get("credential_ref") or "").strip()
        if not credential_ref:
            raise ZrokyRunnerError(f"Recovery step {step_key} missing credential_ref.")
        credential = self.credential_resolver.resolve(credential_ref)
        context = RunnerExecutionContext(
            attempt={"outbox_job_id": dispatch.get("outbox_job_id"), "step_key": step_key},
            plan=plan,
            credential_ref=credential_ref,
            credential=credential,
            idempotency_key=recovery_step_idempotency_key(plan_digest, step_key),
        )
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            result = adapter(context, client)
        if not isinstance(result, dict):
            raise ZrokyRunnerError(f"Recovery adapter {adapter_name} returned invalid result.")
        return _redact(result)


def main() -> None:
    executor_ref = os.environ.get("ZROKY_EXECUTOR_REF", "").strip()
    if not executor_ref:
        raise SystemExit("ZROKY_EXECUTOR_REF is required.")
    poll_seconds = float(os.environ.get("ZROKY_POLL_SECONDS", "30"))
    runner = RecoveryRunner(executor_ref=executor_ref)
    runner.run_daemon(poll_interval_seconds=poll_seconds)


if __name__ == "__main__":
    main()
