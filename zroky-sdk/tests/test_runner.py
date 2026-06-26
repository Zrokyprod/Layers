# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

from __future__ import annotations

import json
import threading

import httpx
import pytest

from zroky._runner import ProtectedActionRunner, credential_env_name


def _attempt(
    plan: dict,
    *,
    credential_ref: str = "customer-runner-secret://support/generic",
) -> dict:
    return {
        "attempt_id": "attempt_123",
        "action_id": "action_123",
        "runner_id": "runner_123",
        "status": "running",
        "idempotency_key": "exec_123",
        "credential_ref": credential_ref,
        "execution_plan": {
            "credential_ref": credential_ref,
            "execution_plan": plan,
        },
    }


def _is_claim_request(request: httpx.Request) -> bool:
    return (
        request.url.host == "api.zroky.test"
        and request.url.path.endswith("/execution-attempts/claim")
    )


def test_credential_env_name_is_stable() -> None:
    assert (
        credential_env_name("customer-runner-secret://support/stripe-refund-prod")
        == "ZROKY_RUNNER_SECRET_SUPPORT_STRIPE_REFUND_PROD"
    )


def test_runner_claims_executes_generic_rest_and_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    credential_ref = "customer-runner-secret://support/generic"
    monkeypatch.setenv(
        credential_env_name(credential_ref),
        json.dumps({"base_url": "https://customer.example", "bearer_token": "super-secret"}),
    )
    finish_payloads: list[dict] = []
    provider_requests: list[httpx.Request] = []

    plan = {
        "adapter": "generic_rest",
        "operation": "rest.post",
        "target": {"resource_ref": "/orders/ord_123/approve"},
        "arguments": {"status": "approved"},
    }

    def _handler(request: httpx.Request) -> httpx.Response:
        if _is_claim_request(request):
            return httpx.Response(200, json=_attempt(plan, credential_ref=credential_ref))
        if request.url.host == "customer.example":
            provider_requests.append(request)
            assert request.headers["authorization"] == "Bearer super-secret"
            return httpx.Response(200, json={"id": "ord_123", "status": "approved"})
        if request.url.host == "api.zroky.test" and request.url.path.endswith("/finish"):
            payload = json.loads(request.content.decode("utf-8"))
            finish_payloads.append(payload)
            assert "super-secret" not in json.dumps(payload)
            return httpx.Response(
                200,
                json={
                    "attempt_id": "attempt_123",
                    "action_id": "action_123",
                    "status": payload["final_status"],
                    "result_summary": payload["result_summary"],
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    runner = ProtectedActionRunner(
        runner_id="runner_123",
        api_key="zk_test",
        project="proj_123",
        api_base="https://api.zroky.test",
        transport=httpx.MockTransport(_handler),
    )

    result = runner.run_once(runner_metadata={"runner_instance_id": "runner-test"})

    assert result["status"] == "succeeded"
    assert provider_requests[0].method == "POST"
    assert finish_payloads[0]["final_status"] == "succeeded"
    assert finish_payloads[0]["result_summary"]["adapter"] == "generic_rest"
    assert finish_payloads[0]["result_summary"]["provider_ref"] == "/orders/ord_123/approve"


def test_runner_returns_idle_when_no_claimable_job() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/execution-attempts/claim")
        return httpx.Response(404, json={"detail": "No claimable execution attempt found."})

    runner = ProtectedActionRunner(
        runner_id="runner_123",
        api_key="zk_test",
        project="proj_123",
        api_base="https://api.zroky.test",
        transport=httpx.MockTransport(_handler),
    )

    assert runner.run_once() == {"claimed": False, "status": "idle"}


def test_runner_sends_heartbeat_with_redacted_payload() -> None:
    heartbeat_payloads: list[dict] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/heartbeat")
        payload = json.loads(request.content.decode("utf-8"))
        heartbeat_payloads.append(payload)
        return httpx.Response(
            200,
            json={
                "runner_id": "runner_123",
                "status": payload["status"],
                "heartbeat_payload": payload["heartbeat_payload"],
            },
        )

    runner = ProtectedActionRunner(
        runner_id="runner_123",
        api_key="zk_test",
        project="proj_123",
        api_base="https://api.zroky.test",
        transport=httpx.MockTransport(_handler),
    )

    response = runner.heartbeat(
        heartbeat_payload={"api_key": "secret-token", "runner_instance_id": "local_1"},
        supported_operation_kinds=["TRANSFER"],
    )

    assert response["status"] == "online"
    assert heartbeat_payloads[0]["supported_operation_kinds"] == ["TRANSFER"]
    assert heartbeat_payloads[0]["heartbeat_payload"]["api_key"] == "[REDACTED]"


def test_runner_daemon_heartbeats_backs_off_and_stops() -> None:
    requests: list[str] = []
    clock_value = {"now": 0.0}

    def _sleep(seconds: float) -> None:
        clock_value["now"] += seconds

    def _clock() -> float:
        return clock_value["now"]

    def _handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("/heartbeat"):
            payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "runner_id": "runner_123",
                    "status": payload["status"],
                    "heartbeat_payload": payload["heartbeat_payload"],
                },
            )
        if request.url.path.endswith("/execution-attempts/claim"):
            return httpx.Response(404, json={"detail": "No claimable execution attempt found."})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    runner = ProtectedActionRunner(
        runner_id="runner_123",
        api_key="zk_test",
        project="proj_123",
        api_base="https://api.zroky.test",
        transport=httpx.MockTransport(_handler),
    )

    stats = runner.run_daemon(
        runner_metadata={"runner_instance_id": "local_1"},
        supported_operation_kinds=["TRANSFER"],
        poll_interval_seconds=1,
        idle_backoff_max_seconds=4,
        heartbeat_interval_seconds=1,
        max_iterations=3,
        stop_event=threading.Event(),
        sleep=_sleep,
        clock=_clock,
    )

    assert stats["status"] == "stopped"
    assert stats["iterations"] == 3
    assert stats["idle"] == 3
    assert stats["heartbeats"] >= 2
    assert sum(1 for path in requests if path.endswith("/execution-attempts/claim")) == 3


def test_runner_reports_failed_when_adapter_is_not_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential_ref = "customer-runner-secret://payments/razorpay"
    monkeypatch.setenv(credential_env_name(credential_ref), json.dumps({"token": "secret-token"}))
    finish_payloads: list[dict] = []
    plan = {
        "adapter": "razorpay_refund",
        "operation": "refund.create",
        "target": {"refund_id": "rf_123"},
        "arguments": {"amount_minor": 50000, "currency": "INR"},
    }

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/execution-attempts/claim"):
            return httpx.Response(200, json=_attempt(plan, credential_ref=credential_ref))
        if request.url.path.endswith("/finish"):
            payload = json.loads(request.content.decode("utf-8"))
            finish_payloads.append(payload)
            return httpx.Response(
                200,
                json={"attempt_id": "attempt_123", "status": payload["final_status"]},
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    runner = ProtectedActionRunner(
        runner_id="runner_123",
        api_key="zk_test",
        project="proj_123",
        api_base="https://api.zroky.test",
        transport=httpx.MockTransport(_handler),
    )

    result = runner.run_once()

    assert result["status"] == "failed"
    assert finish_payloads[0]["final_status"] == "failed"
    assert finish_payloads[0]["result_summary"]["runner_error"] == "ZrokyRunnerError"


def test_runner_executes_stripe_refund_create(monkeypatch: pytest.MonkeyPatch) -> None:
    credential_ref = "customer-runner-secret://payments/stripe"
    monkeypatch.setenv(
        credential_env_name(credential_ref),
        json.dumps({"secret_key": "sk_test_secret"}),
    )
    stripe_requests: list[httpx.Request] = []
    finish_payloads: list[dict] = []
    plan = {
        "adapter": "stripe_refund",
        "operation": "refund.create",
        "target": {"refund_id": "rf_123", "charge": "ch_123"},
        "arguments": {"amount_minor": 50000, "currency": "USD"},
    }

    def _handler(request: httpx.Request) -> httpx.Response:
        if _is_claim_request(request):
            return httpx.Response(200, json=_attempt(plan, credential_ref=credential_ref))
        if request.url.host == "api.stripe.com":
            stripe_requests.append(request)
            assert request.headers["authorization"] == "Bearer sk_test_secret"
            assert b"charge=ch_123" in request.content
            assert b"amount=50000" in request.content
            return httpx.Response(200, json={"id": "re_123", "status": "succeeded"})
        if request.url.host == "api.zroky.test" and request.url.path.endswith("/finish"):
            payload = json.loads(request.content.decode("utf-8"))
            finish_payloads.append(payload)
            assert "sk_test_secret" not in json.dumps(payload)
            return httpx.Response(
                200,
                json={"attempt_id": "attempt_123", "status": payload["final_status"]},
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    runner = ProtectedActionRunner(
        runner_id="runner_123",
        api_key="zk_test",
        project="proj_123",
        api_base="https://api.zroky.test",
        transport=httpx.MockTransport(_handler),
    )

    result = runner.run_once()

    assert result["status"] == "succeeded"
    assert stripe_requests[0].method == "POST"
    assert finish_payloads[0]["result_summary"]["adapter"] == "stripe_refund"
    assert finish_payloads[0]["result_summary"]["provider_ref"] == "re_123"
