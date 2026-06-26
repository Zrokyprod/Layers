# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Customer-hosted protected action runner.

The runner is intentionally local-first: Zroky's API owns policy, approval,
dispatch, timeline, and receipts; the customer-hosted process resolves protected
credential references locally and executes the action without returning secrets
to the agent or control plane.
"""
from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

from zroky._internal.config import load_config

_REQUEST_TIMEOUT_S = 30.0
_FINAL_STATUSES = {"succeeded", "failed", "ambiguous", "cancelled"}
RUNNER_CAPABILITY_VERSION = "zroky-python-runner/0.1.0"
DEFAULT_EXECUTABLE_ADAPTERS = ("generic_rest", "stripe_refund")
_SECRET_KEY_MARKERS = (
    "authorization",
    "bearer",
    "bearer_token",
    "api_key",
    "apikey",
    "key_secret",
    "password",
    "secret",
    "token",
)
_SECRET_VALUE_MARKERS = (
    "bearer ",
    "sk_live_",
    "sk_test_",
    "xoxb-",
    "xoxp-",
    "ghp_",
    "gho_",
    "github_pat_",
    "-----begin private key-----",
)


class ZrokyRunnerError(RuntimeError):
    """Raised when a protected action runner cannot safely execute a job."""


@dataclass(frozen=True)
class RunnerExecutionContext:
    attempt: dict[str, Any]
    plan: dict[str, Any]
    credential_ref: str
    credential: dict[str, Any]
    idempotency_key: str | None


RunnerAdapter = Callable[[RunnerExecutionContext, httpx.Client], dict[str, Any]]


def default_runner_metadata(runner_instance_id: str | None = None) -> dict[str, Any]:
    """Build non-secret metadata for runner claim and heartbeat payloads."""
    metadata: dict[str, Any] = {
        "runner_instance_id": runner_instance_id or os.environ.get("ZROKY_RUNNER_INSTANCE_ID"),
        "host": (
            os.environ.get("COMPUTERNAME")
            or os.environ.get("HOSTNAME")
            or socket.gethostname()
        ),
        "pid": os.getpid(),
        "sdk": "zroky-python",
        "capability_version": RUNNER_CAPABILITY_VERSION,
        "executable_adapters": list(DEFAULT_EXECUTABLE_ADAPTERS),
    }
    return {key: value for key, value in metadata.items() if value not in (None, "")}


def credential_env_name(credential_ref: str) -> str:
    """Map a protected credential reference to a deterministic env var name."""
    cleaned = credential_ref.strip()
    for prefix in (
        "customer-runner-secret://",
        "zroky-secret://",
        "vault://",
        "aws-secretsmanager://",
        "gcp-secretmanager://",
        "azure-keyvault://",
    ):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    token = re.sub(r"[^A-Za-z0-9]+", "_", cleaned).strip("_").upper()
    if not token:
        raise ZrokyRunnerError("credential_ref cannot be mapped to an env var.")
    return f"ZROKY_RUNNER_SECRET_{token}"


class EnvCredentialResolver:
    """Resolve protected credential refs from local runner environment variables."""

    def resolve(self, credential_ref: str) -> dict[str, Any]:
        env_name = credential_env_name(credential_ref)
        raw = os.environ.get(env_name)
        if raw is None or not raw.strip():
            raise ZrokyRunnerError(
                f"Missing local runner credential env var {env_name} for {credential_ref}."
            )
        raw = raw.strip()
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ZrokyRunnerError(f"{env_name} contains invalid JSON.") from exc
            if not isinstance(parsed, dict):
                raise ZrokyRunnerError(f"{env_name} must contain a JSON object.")
            return dict(parsed)
        return {"token": raw}


def _api_headers(api_key: str, project: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "x-api-key": api_key,
        "x-project-id": project,
    }


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            key_text = str(key).strip().lower()
            if any(marker in key_text for marker in _SECRET_KEY_MARKERS):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = _redact(nested)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        lowered = value.strip().lower()
        if any(marker in lowered for marker in _SECRET_VALUE_MARKERS):
            return "[REDACTED]"
        if len(value) > 2000:
            return value[:2000] + "...[truncated]"
    return value


def _json_response_preview(response: httpx.Response) -> Any:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:1000]
    return _redact(payload)


def _credential_header(credential: Mapping[str, Any]) -> dict[str, str]:
    bearer = credential.get("bearer_token") or credential.get("token")
    if bearer:
        return {"Authorization": f"Bearer {str(bearer).strip()}"}
    header_name = credential.get("header_name")
    api_key = credential.get("api_key")
    if header_name and api_key:
        return {str(header_name): str(api_key)}
    return {}


def _base_url(credential: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    target = plan.get("target") if isinstance(plan.get("target"), Mapping) else {}
    value = credential.get("base_url") or target.get("base_url")  # type: ignore[union-attr]
    if not value:
        raise ZrokyRunnerError("Runner credential or target must provide base_url.")
    return str(value).rstrip("/") + "/"


def _path_from_plan(plan: Mapping[str, Any]) -> str:
    target = plan.get("target")
    if not isinstance(target, Mapping):
        raise ZrokyRunnerError("execution plan target must be an object.")
    path = target.get("path") or target.get("resource_path") or target.get("resource_ref")
    if not path:
        raise ZrokyRunnerError("generic_rest target requires path, resource_path, or resource_ref.")
    return str(path).lstrip("/")


def _arguments(plan: Mapping[str, Any]) -> dict[str, Any]:
    arguments = plan.get("arguments")
    if arguments is None:
        return {}
    if not isinstance(arguments, Mapping):
        raise ZrokyRunnerError("execution plan arguments must be an object.")
    return dict(arguments)


def generic_rest_adapter(ctx: RunnerExecutionContext, client: httpx.Client) -> dict[str, Any]:
    operation = str(ctx.plan.get("operation") or "").strip()
    method = {
        "rest.post": "POST",
        "rest.patch": "PATCH",
        "rest.put": "PUT",
        "workflow.execute": "POST",
    }.get(operation)
    if method is None:
        raise ZrokyRunnerError(f"generic_rest does not support operation {operation!r}.")

    url = urljoin(_base_url(ctx.credential, ctx.plan), _path_from_plan(ctx.plan))
    arguments = _arguments(ctx.plan)
    body = arguments.get("body") if isinstance(arguments.get("body"), Mapping) else arguments
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    headers.update(_credential_header(ctx.credential))

    response = client.request(method, url, headers=headers, json=body)
    result: dict[str, Any] = {
        "adapter": "generic_rest",
        "operation": operation,
        "provider_ref": _provider_ref(ctx.plan),
        "http_status": response.status_code,
        "status": "succeeded" if 200 <= response.status_code < 300 else "failed",
        "response": _json_response_preview(response),
    }
    if response.status_code >= 300:
        raise ZrokyRunnerError(
            f"generic_rest execution failed with HTTP {response.status_code}: {response.text[:300]}"
        )
    return result


def stripe_refund_adapter(ctx: RunnerExecutionContext, client: httpx.Client) -> dict[str, Any]:
    token = ctx.credential.get("secret_key") or ctx.credential.get("token")
    if not token:
        raise ZrokyRunnerError("stripe_refund credential requires secret_key or token.")
    operation = str(ctx.plan.get("operation") or "").strip()
    target = ctx.plan.get("target") if isinstance(ctx.plan.get("target"), Mapping) else {}
    arguments = _arguments(ctx.plan)
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": ctx.idempotency_key or str(ctx.attempt.get("attempt_id") or ""),
    }

    if operation == "refund.create":
        form: dict[str, str] = {}
        for field in ("charge", "payment_intent"):
            value = target.get(field) or arguments.get(field)  # type: ignore[union-attr]
            if value:
                form[field] = str(value)
                break
        if not form:
            raise ZrokyRunnerError("stripe_refund refund.create requires charge or payment_intent.")
        if arguments.get("amount_minor") is not None:
            form["amount"] = str(arguments["amount_minor"])
        if arguments.get("reason") is not None:
            form["reason"] = str(arguments["reason"])
        if target.get("refund_id") is not None:  # type: ignore[union-attr]
            form["metadata[zroky_refund_id]"] = str(target["refund_id"])  # type: ignore[index]
        response = client.post("https://api.stripe.com/v1/refunds", headers=headers, data=form)
    elif operation == "refund.cancel":
        refund_id = target.get("refund_id")  # type: ignore[union-attr]
        if not refund_id:
            raise ZrokyRunnerError("stripe_refund refund.cancel requires target.refund_id.")
        response = client.post(
            f"https://api.stripe.com/v1/refunds/{refund_id}/cancel",
            headers=headers,
        )
    else:
        raise ZrokyRunnerError(f"stripe_refund does not support operation {operation!r}.")

    payload = _json_response_preview(response)
    if response.status_code >= 300:
        raise ZrokyRunnerError(
            "stripe_refund execution failed with HTTP "
            f"{response.status_code}: {response.text[:300]}"
        )
    provider_ref = payload.get("id") if isinstance(payload, dict) else None
    return {
        "adapter": "stripe_refund",
        "operation": operation,
        "provider_ref": provider_ref or _provider_ref(ctx.plan),
        "http_status": response.status_code,
        "status": "succeeded",
        "response": payload,
    }


def _provider_ref(plan: Mapping[str, Any]) -> str | None:
    target = plan.get("target")
    if not isinstance(target, Mapping):
        return None
    for key in ("provider_ref", "refund_id", "ticket_id", "message_id", "resource_ref"):
        value = target.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _sleep_until_stop(
    delay_seconds: float,
    stop_event: threading.Event | None,
    sleep: Callable[[float], None],
) -> None:
    remaining = max(0.0, float(delay_seconds))
    while remaining > 0:
        if stop_event is not None and stop_event.is_set():
            return
        chunk = min(remaining, 0.5)
        sleep(chunk)
        remaining -= chunk


def _unsupported_adapter(name: str) -> RunnerAdapter:
    def _adapter(_ctx: RunnerExecutionContext, _client: httpx.Client) -> dict[str, Any]:
        raise ZrokyRunnerError(
            f"{name} requires a customer adapter callback in this SDK version."
        )

    return _adapter


DEFAULT_RUNNER_ADAPTERS: dict[str, RunnerAdapter] = {
    "generic_rest": generic_rest_adapter,
    "stripe_refund": stripe_refund_adapter,
    "razorpay_refund": _unsupported_adapter("razorpay_refund"),
    "zendesk_ticket": _unsupported_adapter("zendesk_ticket"),
    "customer_message": _unsupported_adapter("customer_message"),
}


class ProtectedActionRunner:
    """Claim, execute, and finish protected action attempts for one runner id."""

    def __init__(
        self,
        *,
        runner_id: str,
        api_key: str | None = None,
        project: str | None = None,
        api_base: str | None = None,
        credential_resolver: EnvCredentialResolver | None = None,
        adapters: Mapping[str, RunnerAdapter] | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = _REQUEST_TIMEOUT_S,
    ) -> None:
        config = load_config(api_key=api_key, project=project, ingest_url=api_base)
        if not config.api_key or not config.project:
            raise ZrokyRunnerError("ProtectedActionRunner requires api_key and project.")
        self.runner_id = runner_id
        self.api_key = config.api_key
        self.project = config.project
        self.api_base = config.ingest_url.rstrip("/")
        self.credential_resolver = credential_resolver or EnvCredentialResolver()
        self.adapters = {**DEFAULT_RUNNER_ADAPTERS, **dict(adapters or {})}
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    def claim_once(
        self,
        *,
        runner_metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        url = f"{self.api_base}/v1/action-runners/{self.runner_id}/execution-attempts/claim"
        payload = {"runner_metadata": dict(runner_metadata or {})}
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.post(
                url,
                headers=_api_headers(self.api_key, self.project),
                json=payload,
            )
        if response.status_code == 404:
            return None
        if response.status_code >= 300:
            raise ZrokyRunnerError(
                f"Runner claim failed with HTTP {response.status_code}: {response.text[:300]}"
            )
        data = response.json()
        if not isinstance(data, dict):
            raise ZrokyRunnerError("Runner claim returned invalid response shape.")
        return data

    def heartbeat(
        self,
        *,
        status: str = "online",
        heartbeat_payload: Mapping[str, Any] | None = None,
        supported_operation_kinds: list[str] | tuple[str, ...] | None = None,
        capability_version: str | None = RUNNER_CAPABILITY_VERSION,
    ) -> dict[str, Any]:
        url = f"{self.api_base}/v1/action-runners/{self.runner_id}/heartbeat"
        payload: dict[str, Any] = {
            "status": status,
            "heartbeat_payload": _redact(dict(heartbeat_payload or {})),
        }
        if supported_operation_kinds is not None:
            payload["supported_operation_kinds"] = list(supported_operation_kinds)
        if capability_version is not None:
            payload["capability_version"] = capability_version
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.post(
                url,
                headers=_api_headers(self.api_key, self.project),
                json=payload,
            )
        if response.status_code >= 300:
            raise ZrokyRunnerError(
                f"Runner heartbeat failed with HTTP {response.status_code}: {response.text[:300]}"
            )
        data = response.json()
        if not isinstance(data, dict):
            raise ZrokyRunnerError("Runner heartbeat returned invalid response shape.")
        return data

    def run_once(self, *, runner_metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        attempt = self.claim_once(runner_metadata=runner_metadata)
        if attempt is None:
            return {"claimed": False, "status": "idle"}

        try:
            result_summary = self._execute_attempt(attempt)
            final_status = str(result_summary.pop("final_status", "succeeded"))
            if final_status not in _FINAL_STATUSES:
                final_status = "succeeded"
            finished = self.finish_attempt(
                attempt=attempt,
                final_status=final_status,
                result_summary=result_summary,
            )
            return {"claimed": True, "status": final_status, "attempt": finished}
        except Exception as exc:  # noqa: BLE001
            failed = self.finish_attempt(
                attempt=attempt,
                final_status="failed",
                result_summary={"runner_error": exc.__class__.__name__},
                error_message=str(exc),
            )
            return {"claimed": True, "status": "failed", "attempt": failed, "error": str(exc)}

    def run_daemon(
        self,
        *,
        runner_metadata: Mapping[str, Any] | None = None,
        supported_operation_kinds: list[str] | tuple[str, ...] | None = None,
        capability_version: str | None = RUNNER_CAPABILITY_VERSION,
        poll_interval_seconds: float = 2.0,
        idle_backoff_max_seconds: float = 30.0,
        heartbeat_interval_seconds: float = 30.0,
        max_iterations: int | None = None,
        stop_event: threading.Event | None = None,
        send_offline_heartbeat: bool = True,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> dict[str, Any]:
        """Run the protected-action runner as a long-lived daemon.

        The daemon keeps execution fail-closed: action execution failures are
        reported to the control plane as failed attempts, while transient claim
        or heartbeat errors only slow the polling loop.
        """
        if poll_interval_seconds <= 0:
            raise ZrokyRunnerError("poll_interval_seconds must be greater than zero.")
        if idle_backoff_max_seconds < poll_interval_seconds:
            raise ZrokyRunnerError("idle_backoff_max_seconds must be >= poll_interval_seconds.")
        if heartbeat_interval_seconds <= 0:
            raise ZrokyRunnerError("heartbeat_interval_seconds must be greater than zero.")
        if max_iterations is not None and max_iterations <= 0:
            raise ZrokyRunnerError("max_iterations must be greater than zero when provided.")

        base_metadata = dict(runner_metadata or default_runner_metadata())
        stats: dict[str, Any] = {
            "status": "running",
            "iterations": 0,
            "claimed": 0,
            "idle": 0,
            "succeeded": 0,
            "failed": 0,
            "ambiguous": 0,
            "cancelled": 0,
            "claim_errors": 0,
            "heartbeat_errors": 0,
            "heartbeats": 0,
            "last_result": None,
        }
        next_heartbeat_at = 0.0
        idle_delay = poll_interval_seconds

        try:
            while stop_event is None or not stop_event.is_set():
                now = clock()
                if now >= next_heartbeat_at:
                    heartbeat_payload = {
                        **base_metadata,
                        "daemon": True,
                        "stats": {
                            key: value
                            for key, value in stats.items()
                            if key not in {"last_result", "status"}
                        },
                    }
                    try:
                        self.heartbeat(
                            status="online",
                            heartbeat_payload=heartbeat_payload,
                            supported_operation_kinds=supported_operation_kinds,
                            capability_version=capability_version,
                        )
                        stats["heartbeats"] += 1
                    except Exception as exc:  # noqa: BLE001
                        stats["heartbeat_errors"] += 1
                        stats["last_heartbeat_error"] = str(exc)
                    next_heartbeat_at = now + heartbeat_interval_seconds

                stats["iterations"] += 1
                try:
                    result = self.run_once(runner_metadata=base_metadata)
                except Exception as exc:  # noqa: BLE001
                    stats["claim_errors"] += 1
                    stats["last_error"] = str(exc)
                    sleep_for = idle_delay
                    idle_delay = min(idle_backoff_max_seconds, idle_delay * 2)
                else:
                    stats["last_result"] = result
                    result_status = str(result.get("status") or "unknown")
                    if result.get("claimed") is True:
                        stats["claimed"] += 1
                        if result_status in {"succeeded", "failed", "ambiguous", "cancelled"}:
                            stats[result_status] += 1
                        idle_delay = poll_interval_seconds
                        sleep_for = 0.0
                    else:
                        stats["idle"] += 1
                        sleep_for = idle_delay
                        idle_delay = min(idle_backoff_max_seconds, idle_delay * 2)

                if max_iterations is not None and stats["iterations"] >= max_iterations:
                    break
                _sleep_until_stop(sleep_for, stop_event, sleep)
        finally:
            stats["status"] = "stopped"
            if send_offline_heartbeat:
                try:
                    self.heartbeat(
                        status="offline",
                        heartbeat_payload={**base_metadata, "daemon": True, "final_stats": stats},
                        supported_operation_kinds=supported_operation_kinds,
                        capability_version=capability_version,
                    )
                    stats["heartbeats"] += 1
                except Exception as exc:  # noqa: BLE001
                    stats["heartbeat_errors"] += 1
                    stats["offline_heartbeat_error"] = str(exc)
        return stats

    def finish_attempt(
        self,
        *,
        attempt: Mapping[str, Any],
        final_status: str,
        result_summary: Mapping[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        action_id = str(attempt.get("action_id") or "")
        attempt_id = str(attempt.get("attempt_id") or "")
        if not action_id or not attempt_id:
            raise ZrokyRunnerError("attempt response missing action_id or attempt_id.")
        payload = {
            "final_status": final_status,
            "result_summary": _redact(dict(result_summary or {})),
            "error_message": error_message,
        }
        url = (
            f"{self.api_base}/v1/action-intents/{action_id}"
            f"/execution-attempts/{attempt_id}/finish"
        )
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.post(
                url,
                headers=_api_headers(self.api_key, self.project),
                json={key: value for key, value in payload.items() if value is not None},
            )
        if response.status_code >= 300:
            raise ZrokyRunnerError(
                f"Runner finish failed with HTTP {response.status_code}: {response.text[:300]}"
            )
        data = response.json()
        if not isinstance(data, dict):
            raise ZrokyRunnerError("Runner finish returned invalid response shape.")
        return data

    def _execute_attempt(self, attempt: Mapping[str, Any]) -> dict[str, Any]:
        wrapper = attempt.get("execution_plan")
        if not isinstance(wrapper, Mapping):
            raise ZrokyRunnerError("attempt missing execution_plan.")
        plan = wrapper.get("execution_plan")
        if not isinstance(plan, Mapping):
            raise ZrokyRunnerError("attempt missing runner execution_plan.")
        credential_ref = str(
            wrapper.get("credential_ref") or attempt.get("credential_ref") or ""
        ).strip()
        if not credential_ref:
            raise ZrokyRunnerError("attempt missing credential_ref.")
        adapter_name = str(plan.get("adapter") or "").strip()
        if not adapter_name:
            raise ZrokyRunnerError("attempt execution_plan missing adapter.")
        adapter = self.adapters.get(adapter_name)
        if adapter is None:
            raise ZrokyRunnerError(f"Unsupported runner adapter: {adapter_name}.")
        credential = self.credential_resolver.resolve(credential_ref)
        context = RunnerExecutionContext(
            attempt=dict(attempt),
            plan=dict(plan),
            credential_ref=credential_ref,
            credential=credential,
            idempotency_key=str(attempt.get("idempotency_key") or "") or None,
        )
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            result = adapter(context, client)
        if not isinstance(result, dict):
            raise ZrokyRunnerError(f"Runner adapter {adapter_name} returned invalid result.")
        return _redact(result)
