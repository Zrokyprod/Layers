# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from zroky._runner import RunnerExecutionContext, credential_env_name
from zroky.recovery_runner import RecoveryRunner, recovery_step_idempotency_key


def test_recovery_step_idempotency_key_is_deterministic() -> None:
    assert recovery_step_idempotency_key("plan_digest_1", "refund_retry") == hashlib.sha256(
        b"plan_digest_1:refund_retry"
    ).hexdigest()


def test_recovery_runner_claims_executes_and_completes_with_fake_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential_ref = "customer-runner-secret://ops/generic"
    monkeypatch.setenv(credential_env_name(credential_ref), json.dumps({"token": "secret"}))
    complete_payloads: list[dict] = []
    plan_digest = "plan_digest_1"

    def fake_adapter(ctx: RunnerExecutionContext, _client: httpx.Client) -> dict:
        assert ctx.credential == {"token": "secret"}
        assert ctx.idempotency_key == recovery_step_idempotency_key(plan_digest, "refund_retry")
        return {"adapter": "fake", "provider_ref": "rf_123", "secret": "should-redact-token"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/recovery/dispatch/claim":
            return httpx.Response(
                200,
                json={
                    "outbox_job_id": "job_1",
                    "recovery_plan_id": "plan_1",
                    "executor_ref": "customer-recovery-executor://ops/refund",
                    "nonce": "nonce_1",
                    "fencing_token": "job_1:1",
                    "lease_expires_at": "2026-07-30T00:00:00Z",
                    "recovery_plan": {
                        "schema_version": "zroky.recovery_plan.v1",
                        "plan": {
                            "step_key": "refund_retry",
                            "adapter": "generic_rest",
                            "credential_ref": credential_ref,
                            "operation": "rest.post",
                            "target": {"resource_ref": "/refunds/rf_123/retry"},
                        },
                    },
                    "signed_payload": {"plan_digest": plan_digest},
                    "signature": "sig",
                },
            )
        if request.url.path == "/v1/recovery/dispatch/complete":
            payload = json.loads(request.content.decode("utf-8"))
            complete_payloads.append(payload)
            return httpx.Response(
                200,
                json={
                    "outbox_job_id": payload["outbox_job_id"],
                    "recovery_plan_id": "plan_1",
                    "job_status": "completed",
                    "execution_status": payload["overall"],
                    "incident_status": "recovering",
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    runner = RecoveryRunner(
        executor_ref="customer-recovery-executor://ops/refund",
        api_key="zk_test",
        project="proj_123",
        api_base="https://api.zroky.test",
        adapters={"generic_rest": fake_adapter},
        transport=httpx.MockTransport(handler),
    )

    result = runner.run_once(send_heartbeats=False)

    assert result["status"] == "succeeded"
    assert complete_payloads[0]["overall"] == "succeeded"
    assert complete_payloads[0]["fencing_token"] == "job_1:1"
    assert complete_payloads[0]["step_results"][0]["step_key"] == "refund_retry"
    assert complete_payloads[0]["step_results"][0]["status"] == "succeeded"
    assert complete_payloads[0]["step_results"][0]["detail"]["secret"] == "[REDACTED]"
