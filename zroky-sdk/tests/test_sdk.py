# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Tests for SDK init + call error classification."""
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

import zroky
from zroky._errors import (
    ZrokyOutcomeVerificationError,
    ZrokyRuntimePolicyApprovalRequired,
    ZrokyRuntimePolicyBlocked,
    ZrokyRuntimePolicyError,
    ZrokyVerifiedActionApprovalRequired,
    ZrokyVerifiedActionError,
)
from zroky._internal.config import load_config
from zroky._internal.models import ErrorCode
from zroky._internal.prompt_fingerprint import generate_prompt_fingerprint
from zroky._runtime_policy import _runtime_policy_url
from zroky._verified_action import _api_url


def _reset_sdk():
    """Reset SDK global state between tests."""
    zroky._config = None
    zroky._queue = None
    zroky._recent_preflight_calls.clear()
    zroky._payload_guard_logged_call_ids.clear()
    zroky._payload_guard_log_order.clear()


def test_init_sets_config(tmp_path, monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_API_KEY", "test-key-abc")
    monkeypatch.setenv("ZROKY_PROJECT", "my-project")

    with patch("zroky._internal.queue.IngestClient"):
        zroky.init()

    assert zroky._config is not None
    assert zroky._config.api_key == "test-key-abc"
    assert zroky._config.project == "my-project"
    zroky.shutdown()
    _reset_sdk()


def test_init_reads_capture_context_fields(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_AGENT_FRAMEWORK", "langgraph")
    monkeypatch.setenv("ZROKY_SESSION_ID", "sess_1")
    monkeypatch.setenv("ZROKY_WORKFLOW_ID", "wf_1")
    monkeypatch.setenv("ZROKY_WORKFLOW_NAME", "support-resolution")
    monkeypatch.setenv("ZROKY_PROMPT_VERSION", "support-v42")
    monkeypatch.setenv("ZROKY_ENVIRONMENT", "production")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    assert zroky._config is not None
    assert zroky._config.agent_framework == "langgraph"
    assert zroky._config.session_id == "sess_1"
    assert zroky._config.workflow_id == "wf_1"
    assert zroky._config.workflow_name == "support-resolution"
    assert zroky._config.prompt_version == "support-v42"
    assert zroky._config.environment == "production"

    zroky.shutdown()
    _reset_sdk()


def test_load_config_defaults_to_cloud_ingest_url(monkeypatch):
    monkeypatch.delenv("ZROKY_INGEST_URL", raising=False)

    cfg = load_config()

    assert cfg.ingest_url == "https://api.zroky.com"


@pytest.mark.parametrize(
    ("raw_url", "expected_url"),
    [
        ("https://api.zroky.com", "https://api.zroky.com"),
        ("https://api.zroky.com/", "https://api.zroky.com"),
        ("https://api.zroky.com/v1/ingest", "https://api.zroky.com"),
        ("https://api.zroky.com/api/v1/ingest", "https://api.zroky.com"),
        ("http://localhost:8000/api/v1/ingest", "http://localhost:8000"),
        ("http://localhost:8000/v1/ingest", "http://localhost:8000"),
    ],
)
def test_load_config_normalizes_ingest_endpoint_to_api_base(monkeypatch, raw_url, expected_url):
    monkeypatch.setenv("ZROKY_INGEST_URL", raw_url)

    cfg = load_config()

    assert cfg.ingest_url == expected_url


def test_runtime_policy_url_uses_control_plane_endpoint():
    assert (
        _runtime_policy_url("https://api.zroky.com/v1/ingest")
        == "https://api.zroky.com/v1/runtime-policy/check"
    )
    assert (
        _runtime_policy_url("http://localhost:8000/api/v1/ingest")
        == "http://localhost:8000/v1/runtime-policy/check"
    )


def test_verified_action_api_url_uses_control_plane_endpoint():
    assert (
        _api_url("https://api.zroky.com/v1/ingest", "/v1/action-intents")
        == "https://api.zroky.com/v1/action-intents"
    )
    assert (
        _api_url("http://localhost:8000/api/v1/ingest", "/v1/action-intents")
        == "http://localhost:8000/v1/action-intents"
    )


def test_verified_action_creates_intent_and_decides_without_runner_or_credential_pin(monkeypatch):
    _reset_sdk()
    calls: list[dict[str, object]] = []
    responses = [
        {
            "action_id": "act_123",
            "status": "validated",
            "proof_status": "not_started",
            "receipt_status": "missing",
        },
        {
            "action_id": "act_123",
            "status": "authorized",
            "allowed": True,
            "requires_approval": False,
            "proof_status": "not_started",
            "receipt_status": "missing",
        },
    ]

    class _Response:
        status_code = 200
        text = "ok"

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def _fake_request(method, url, *, headers, json, timeout):
        calls.append({"method": method, "url": url, "headers": headers, "json": json, "timeout": timeout})
        return _Response(responses[len(calls) - 1])

    monkeypatch.setattr("zroky._verified_action.httpx.request", _fake_request)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(
            api_key="zk_live_test",
            project="proj_actions",
            ingest_url="https://api.zroky.com/v1/ingest",
            agent_id="agent_profile_inventory",
        )

    decision = zroky.verified_action(
        contract_version="inventory.item.update/1.0",
        action_type="inventory.item.update",
        operation_kind="UPDATE",
        principal={"type": "agent", "id": "inventory-agent"},
        resource={"type": "inventory_item", "id": "item_123"},
        parameters={"fields": {"status": "active"}},
        execution_request={
            "capability": {"adapter": "generic_rest", "operation": "rest.patch"},
            "credential_pointer": "ops-default",
            "execution_plan": {
                "adapter": "generic_rest",
                "operation": "rest.patch",
                "target": {"resource_ref": "item_123"},
                "arguments": {"fields": {"status": "active"}},
            },
        },
        idempotency_key="inventory_item_123_update",
    )

    assert decision["status"] == "authorized"
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == "https://api.zroky.com/v1/action-intents"
    assert calls[1]["url"] == "https://api.zroky.com/v1/action-intents/act_123/decide"
    assert calls[0]["headers"]["Idempotency-Key"] == "inventory_item_123_update"  # type: ignore[index]
    body = calls[0]["json"]  # type: ignore[assignment]
    assert body["agent_id"] == "agent_profile_inventory"  # type: ignore[index]
    assert body["execution_request"]["credential_pointer"] == "ops-default"  # type: ignore[index]
    assert "runner_id" not in body["execution_request"]  # type: ignore[operator,index]
    assert "credential_ref" not in body["execution_request"]  # type: ignore[operator,index]
    zroky.shutdown()
    _reset_sdk()


def test_protect_maps_action_quickstart_to_verified_action(monkeypatch):
    _reset_sdk()
    calls: list[dict[str, object]] = []
    responses = [
        {"action_id": "act_access", "status": "validated"},
        {"action_id": "act_access", "status": "authorized", "allowed": True, "requires_approval": False},
    ]

    class _Response:
        status_code = 200
        text = "ok"

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def _fake_request(method, url, *, headers, json, timeout):
        calls.append({"method": method, "url": url, "headers": headers, "json": json, "timeout": timeout})
        return _Response(responses[len(calls) - 1])

    monkeypatch.setattr("zroky._verified_action.httpx.request", _fake_request)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_actions", agent_id="agent_profile_default")

    decision = zroky.protect(
        action="access.grant",
        operation_kind="update",
        params={"system": "github", "user_id": "user_123", "role": "admin"},
        resource={"type": "workspace_access", "id": "github:user_123"},
        purpose={"reason": "Grant temporary admin access after approval."},
        verification_profile="github-role-match",
        idempotency_key="access_user_123_admin",
    )

    assert decision["status"] == "authorized"
    assert calls[0]["url"] == "https://api.zroky.com/v1/action-intents"
    assert calls[1]["url"] == "https://api.zroky.com/v1/action-intents/act_access/decide"
    body = calls[0]["json"]  # type: ignore[assignment]
    assert body["contract_version"] == "access.grant/1.0"  # type: ignore[index]
    assert body["action_type"] == "access.grant"  # type: ignore[index]
    assert body["operation_kind"] == "UPDATE"  # type: ignore[index]
    assert body["parameters"]["role"] == "admin"  # type: ignore[index]
    assert body["verification_profile"] == "github-role-match"  # type: ignore[index]
    assert calls[0]["headers"]["Idempotency-Key"] == "access_user_123_admin"  # type: ignore[index]
    zroky.shutdown()
    _reset_sdk()


def test_protect_can_wait_for_receipt(monkeypatch):
    _reset_sdk()
    calls: list[dict[str, object]] = []
    responses = [
        {"action_id": "act_done", "status": "validated"},
        {"action_id": "act_done", "status": "authorized", "allowed": True, "requires_approval": False},
        {"action_id": "act_done", "proof_status": "matched", "receipt_status": "generated"},
        {"receipt_id": "receipt_done", "signature_valid": True},
    ]

    class _Response:
        status_code = 200
        text = "ok"

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def _fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        return _Response(responses[len(calls) - 1])

    monkeypatch.setattr("zroky._verified_action.httpx.request", _fake_request)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_actions")

    result = zroky.protect(
        action="access.grant",
        params={"user_id": "user_123"},
        wait_for_receipt=True,
        poll_interval_seconds=0.01,
    )

    assert result["action_id"] == "act_done"
    assert result["decision"]["status"] == "authorized"
    assert result["receipt"]["receipt_id"] == "receipt_done"
    assert result["signature_valid"] is True
    assert calls[-1]["url"] == "https://api.zroky.com/v1/action-intents/act_done/receipt"
    zroky.shutdown()
    _reset_sdk()


def test_protect_raises_on_approval(monkeypatch):
    _reset_sdk()
    responses = [
        {"action_id": "act_pending", "status": "validated"},
        {
            "action_id": "act_pending",
            "status": "approval_pending",
            "allowed": False,
            "requires_approval": True,
            "runtime_policy_decision_id": "decision_pending",
        },
    ]
    index = {"value": 0}

    class _Response:
        status_code = 200
        text = "ok"

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def _fake_request(*_args, **_kwargs):
        payload = responses[index["value"]]
        index["value"] += 1
        return _Response(payload)

    monkeypatch.setattr("zroky._verified_action.httpx.request", _fake_request)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_actions")

    with pytest.raises(ZrokyVerifiedActionApprovalRequired) as error:
        zroky.protect(action="access.grant", operation_kind="UPDATE", params={"role": "admin"})

    assert error.value.action_id == "act_pending"
    assert error.value.approval_id == "decision_pending"
    zroky.shutdown()
    _reset_sdk()


def test_verified_action_allows_per_call_agent_id_override(monkeypatch):
    _reset_sdk()
    calls: list[dict[str, object]] = []
    responses = [
        {"action_id": "act_123", "status": "validated"},
        {"action_id": "act_123", "status": "authorized", "allowed": True, "requires_approval": False},
    ]

    class _Response:
        status_code = 200
        text = "ok"

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def _fake_request(method, url, *, headers, json, timeout):
        calls.append({"method": method, "url": url, "headers": headers, "json": json, "timeout": timeout})
        return _Response(responses[len(calls) - 1])

    monkeypatch.setattr("zroky._verified_action.httpx.request", _fake_request)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_actions", agent_id="agent_profile_default")

    zroky.verified_action(
        agent_id="agent_profile_override",
        contract_version="inventory.item.update/1.0",
        action_type="inventory.item.update",
        operation_kind="UPDATE",
        execution_request={
            "credential_pointer": "ops-default",
            "execution_plan": {"adapter": "generic_rest", "operation": "rest.patch"},
        },
        idempotency_key="inventory_override",
    )

    body = calls[0]["json"]  # type: ignore[assignment]
    assert body["agent_id"] == "agent_profile_override"  # type: ignore[index]
    zroky.shutdown()
    _reset_sdk()


def test_verified_action_raises_with_action_and_approval_ids(monkeypatch):
    _reset_sdk()
    responses = [
        {"action_id": "act_pending", "status": "validated"},
        {
            "action_id": "act_pending",
            "status": "approval_pending",
            "allowed": False,
            "requires_approval": True,
            "runtime_policy_decision_id": "decision_pending",
        },
    ]
    index = {"value": 0}

    class _Response:
        status_code = 200
        text = "ok"

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def _fake_request(*_args, **_kwargs):
        payload = responses[index["value"]]
        index["value"] += 1
        return _Response(payload)

    monkeypatch.setattr("zroky._verified_action.httpx.request", _fake_request)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_actions")

    with pytest.raises(ZrokyVerifiedActionApprovalRequired) as error:
        zroky.verified_action(
            contract_version="inventory.item.delete/1.0",
            action_type="inventory.item.delete",
            operation_kind="UPDATE",
            execution_request={
                "credential_pointer": "ops-default",
                "execution_plan": {
                    "adapter": "generic_rest",
                    "operation": "rest.patch",
                    "target": {"resource_ref": "item_123"},
                },
            },
            idempotency_key="inventory_item_123_delete",
        )

    assert error.value.action_id == "act_pending"
    assert error.value.approval_id == "decision_pending"
    assert error.value.decision["status"] == "approval_pending"
    zroky.shutdown()
    _reset_sdk()


@pytest.mark.parametrize(
    "execution_request",
    [
        {
            "runner_id": "forbidden",
            "execution_plan": {
                "adapter": "generic_rest",
                "operation": "rest.patch",
                "target": {"resource_ref": "item_123"},
            },
        },
        {
            "credential_pointer": "customer-runner-secret://ops/default",
            "execution_plan": {
                "adapter": "generic_rest",
                "operation": "rest.patch",
                "target": {"resource_ref": "item_123"},
            },
        },
    ],
)
def test_verified_action_rejects_runner_or_credential_pins_before_api_call(monkeypatch, execution_request):
    _reset_sdk()
    called = False

    def _fake_request(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("request should not be called")

    monkeypatch.setattr("zroky._verified_action.httpx.request", _fake_request)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_actions")

    with pytest.raises(ZrokyVerifiedActionError):
        zroky.verified_action(
            contract_version="inventory.item.update/1.0",
            action_type="inventory.item.update",
            operation_kind="UPDATE",
            execution_request=execution_request,
        )

    assert called is False
    zroky.shutdown()
    _reset_sdk()


def test_await_action_proof_polls_until_receipt(monkeypatch):
    _reset_sdk()
    calls: list[str] = []
    responses = [
        {"action_id": "act_done", "proof_status": "pending", "receipt_status": "pending"},
        {"action_id": "act_done", "proof_status": "matched", "receipt_status": "generated"},
        {"receipt_id": "receipt_123", "signature_valid": True, "receipt": {"final_status": "matched"}},
    ]

    class _Response:
        status_code = 200
        text = "ok"

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def _fake_request(_method, url, **_kwargs):
        calls.append(url)
        return _Response(responses[len(calls) - 1])

    monkeypatch.setattr("zroky._verified_action.httpx.request", _fake_request)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_actions")

    proof = zroky.await_action_proof("act_done", timeout_seconds=5, poll_interval_seconds=0.01)

    assert proof["proof_status"] == "matched"
    assert proof["receipt_status"] == "generated"
    assert proof["signature_valid"] is True
    assert proof["evidence_id"] == "receipt_123"
    assert calls[-1] == "https://api.zroky.com/v1/action-intents/act_done/receipt"
    zroky.shutdown()
    _reset_sdk()


def test_check_runtime_policy_posts_masked_payload_and_returns_decision(monkeypatch):
    _reset_sdk()
    posted: dict[str, object] = {}

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {"allowed": True, "status": "allowed", "reasons": ["ok"]}

    def _fake_post(url, *, headers, json, timeout):
        posted["url"] = url
        posted["headers"] = headers
        posted["json"] = json
        posted["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("zroky._runtime_policy.httpx.post", _fake_post)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(
            api_key="zk_live_test",
            project="proj_runtime",
            ingest_url="https://api.zroky.com/v1/ingest",
        )

    decision = zroky.check_runtime_policy(
        action_type="email",
        tool_name="send_email",
        output_text="Send receipt to alice@example.com",
        external_action=True,
        trace_id="trace-sdk",
        business_impact={"summary": "Receipt email", "customer_email": "alice@example.com"},
        order_id="ord_123",
    )

    assert decision["allowed"] is True
    assert posted["url"] == "https://api.zroky.com/v1/runtime-policy/check"
    assert posted["headers"]["x-api-key"] == "zk_live_test"  # type: ignore[index]
    assert posted["headers"]["x-project-id"] == "proj_runtime"  # type: ignore[index]
    assert posted["json"]["output_text"] == "Send receipt to [REDACTED_EMAIL]"  # type: ignore[index]
    assert posted["json"]["business_impact"]["customer_email"] == "[REDACTED_EMAIL]"  # type: ignore[index]
    assert posted["json"]["order_id"] == "ord_123"  # type: ignore[index]
    assert posted["json"]["pii_detected"] is True  # type: ignore[index]
    zroky.shutdown()
    _reset_sdk()


def test_check_runtime_policy_raises_on_block(monkeypatch):
    _reset_sdk()

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "id": "decision_check_hold",
                "allowed": False,
                "status": "pending_approval",
                "requires_approval": True,
                "reasons": ["sensitive action requires human approval"],
                "expires_at": "2026-06-20T12:00:00Z",
            }

    monkeypatch.setattr("zroky._runtime_policy.httpx.post", lambda *args, **kwargs: _Response())
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_runtime")

    with pytest.raises(ZrokyRuntimePolicyApprovalRequired) as error:
        zroky.check_runtime_policy(action_type="refund", tool_name="refund_payment")

    assert isinstance(error.value, ZrokyRuntimePolicyBlocked)
    assert error.value.approval_id == "decision_check_hold"
    assert error.value.expires_at == "2026-06-20T12:00:00Z"
    assert error.value.decision["status"] == "pending_approval"
    zroky.shutdown()
    _reset_sdk()


def test_check_runtime_policy_fails_closed_on_transport_error(monkeypatch):
    _reset_sdk()

    def _raise(*_args, **_kwargs):
        import httpx

        raise httpx.ConnectError("backend down")

    monkeypatch.setattr("zroky._runtime_policy.httpx.post", _raise)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_runtime")

    with pytest.raises(ZrokyRuntimePolicyError):
        zroky.check_runtime_policy(action_type="delete", tool_name="delete_user")

    zroky.shutdown()
    _reset_sdk()


def test_guard_posts_policy_check_and_returns_allowed_decision(monkeypatch):
    _reset_sdk()
    posted: dict[str, object] = {}

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "id": "decision_guard_allow",
                "allowed": True,
                "status": "allowed",
                "reasons": ["runtime policy checks passed"],
            }

    def _fake_post(url, *, headers, json, timeout):
        posted["url"] = url
        posted["headers"] = headers
        posted["json"] = json
        posted["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("zroky._runtime_policy.httpx.post", _fake_post)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(
            api_key="zk_live_test",
            project="proj_runtime",
            ingest_url="https://api.zroky.com/v1/ingest",
        )

    decision = zroky.guard(
        action_type="refund",
        tool_name="refund_payment",
        tool_args={"order_id": "ord_123", "amount": 42.5, "currency": "USD"},
        trace_id="trace-guard",
        external_action=True,
        business_impact={"summary": "Issue approved refund", "estimated_value_usd": 42.5},
    )

    assert decision["id"] == "decision_guard_allow"
    assert decision["allowed"] is True
    assert posted["url"] == "https://api.zroky.com/v1/runtime-policy/check"
    assert posted["headers"]["x-api-key"] == "zk_live_test"  # type: ignore[index]
    assert posted["headers"]["x-project-id"] == "proj_runtime"  # type: ignore[index]
    assert posted["json"]["action_type"] == "refund"  # type: ignore[index]
    assert posted["json"]["tool_name"] == "refund_payment"  # type: ignore[index]
    assert posted["json"]["tool_args"]["order_id"] == "ord_123"  # type: ignore[index]
    assert posted["json"]["business_impact"]["estimated_value_usd"] == 42.5  # type: ignore[index]
    zroky.shutdown()
    _reset_sdk()


def test_guard_raises_on_hold_for_approval(monkeypatch):
    _reset_sdk()

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "id": "decision_guard_hold",
                "allowed": False,
                "status": "pending_approval",
                "requires_approval": True,
                "reasons": ["sensitive action requires human approval"],
                "approval_queue_item": {
                    "id": "decision_guard_hold",
                    "expires_at": "2026-06-20T12:30:00Z",
                },
            }

    monkeypatch.setattr("zroky._runtime_policy.httpx.post", lambda *args, **kwargs: _Response())
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_runtime")

    with pytest.raises(ZrokyRuntimePolicyApprovalRequired) as error:
        zroky.guard(
            action_type="refund",
            tool_name="refund_payment",
            tool_args={"order_id": "ord_hold", "amount": 9000},
            business_impact_summary="High-value refund",
        )

    assert isinstance(error.value, ZrokyRuntimePolicyBlocked)
    assert error.value.approval_id == "decision_guard_hold"
    assert error.value.expires_at == "2026-06-20T12:30:00Z"
    assert error.value.decision["id"] == "decision_guard_hold"
    assert error.value.decision["status"] == "pending_approval"
    zroky.shutdown()
    _reset_sdk()


def test_guard_retries_with_approval_id_after_hold(monkeypatch):
    _reset_sdk()
    posted: list[dict[str, object]] = []
    responses = [
        {
            "id": "decision_guard_hold",
            "allowed": False,
            "status": "pending_approval",
            "requires_approval": True,
            "reasons": ["sensitive action requires human approval"],
        },
        {
            "id": "decision_guard_allowed",
            "allowed": True,
            "status": "allowed",
            "reasons": ["human approval decision_guard_hold accepted"],
        },
    ]

    class _Response:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def _fake_post(_url, *, headers, json, timeout):
        posted.append(json)
        return _Response(responses.pop(0))

    monkeypatch.setattr("zroky._runtime_policy.httpx.post", _fake_post)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_runtime")

    with pytest.raises(ZrokyRuntimePolicyApprovalRequired) as error:
        zroky.guard(
            action_type="refund",
            tool_name="refund_payment",
            tool_args={"order_id": "ord_hold", "amount": 9000},
            external_action=True,
        )

    allowed = zroky.guard(
        action_type="refund",
        tool_name="refund_payment",
        tool_args={"order_id": "ord_hold", "amount": 9000},
        external_action=True,
        approval_id=error.value.approval_id,
    )

    assert allowed["id"] == "decision_guard_allowed"
    assert posted[0].get("approval_id") is None
    assert posted[1]["approval_id"] == "decision_guard_hold"
    zroky.shutdown()
    _reset_sdk()


def test_guard_fails_closed_on_transport_error(monkeypatch):
    _reset_sdk()

    def _raise(*_args, **_kwargs):
        import httpx

        raise httpx.ConnectError("backend down")

    monkeypatch.setattr("zroky._runtime_policy.httpx.post", _raise)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_runtime")

    with pytest.raises(ZrokyRuntimePolicyError):
        zroky.guard(action_type="delete", tool_name="delete_customer")

    zroky.shutdown()
    _reset_sdk()


def test_verify_outcome_posts_generic_rest_saved_reconciliation(monkeypatch):
    _reset_sdk()
    posted: dict[str, object] = {}

    class _Response:
        status_code = 201

        @staticmethod
        def json():
            return {
                "id": "check_generic",
                "verdict": "matched",
                "connector_type": "generic_rest_api",
                "system_ref": "generic:ord_123",
            }

    def _fake_post(url, *, headers, json, timeout):
        posted["url"] = url
        posted["headers"] = headers
        posted["json"] = json
        posted["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("zroky._verify.httpx.post", _fake_post)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(
            api_key="zk_live_test",
            project="proj_runtime",
            ingest_url="https://api.zroky.com/v1/ingest",
        )

    result = zroky.verify_outcome(
        connector="generic_rest",
        record_ref="ord_123",
        runtime_policy_decision_id="decision_123",
        action_type="internal_api_mutation",
        claimed={"record_ref": "ord_123", "status": "approved", "total_usd": 118.42},
        metadata={"run_id": "pilot_1"},
    )

    assert result["id"] == "check_generic"
    assert posted["url"] == (
        "https://api.zroky.com/v1/outcomes/reconciliation/generic-rest/saved"
    )
    assert posted["headers"]["x-api-key"] == "zk_live_test"  # type: ignore[index]
    assert posted["headers"]["x-project-id"] == "proj_runtime"  # type: ignore[index]
    assert posted["json"]["record_ref"] == "ord_123"  # type: ignore[index]
    assert posted["json"]["runtime_policy_decision_id"] == "decision_123"  # type: ignore[index]
    assert posted["json"]["action_type"] == "internal_api_mutation"  # type: ignore[index]
    assert posted["json"]["claimed"]["status"] == "approved"  # type: ignore[index]
    assert "bearer" not in str(posted["json"]).lower()
    zroky.shutdown()
    _reset_sdk()


def test_verify_outcome_maps_saved_ledger_and_crm_routes(monkeypatch):
    _reset_sdk()
    posted: list[dict[str, object]] = []

    class _Response:
        status_code = 201

        @staticmethod
        def json():
            return {"id": "check_saved", "verdict": "matched"}

    def _fake_post(url, *, headers, json, timeout):
        posted.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _Response()

    monkeypatch.setattr("zroky._verify.httpx.post", _fake_post)
    with patch("zroky._internal.queue.IngestClient"):
        zroky.init(api_key="zk_live_test", project="proj_runtime")

    zroky.verify_outcome(
        connector="ledger_refund",
        refund_id="rf_123",
        runtime_policy_decision_id="decision_refund",
        claimed={"refund_id": "rf_123", "amount_usd": 42.5, "currency": "USD"},
    )
    zroky.verify_outcome(
        connector="crm_record",
        customer_id="cus_123",
        runtime_policy_decision_id="decision_customer",
        claimed={"customer_id": "cus_123", "status": "active"},
    )

    assert posted[0]["url"] == (
        "https://api.zroky.com/v1/outcomes/reconciliation/ledger-refund/saved"
    )
    assert posted[0]["json"]["refund_id"] == "rf_123"  # type: ignore[index]
    assert posted[1]["url"] == (
        "https://api.zroky.com/v1/outcomes/reconciliation/customer-record/saved"
    )
    assert posted[1]["json"]["customer_id"] == "cus_123"  # type: ignore[index]
    zroky.shutdown()
    _reset_sdk()


def test_verify_outcome_fails_closed_when_credentials_are_missing(monkeypatch):
    _reset_sdk()
    monkeypatch.delenv("ZROKY_API_KEY", raising=False)
    monkeypatch.delenv("ZROKY_PROJECT", raising=False)

    with patch("zroky._internal.queue.IngestClient"):
        with pytest.raises(ZrokyOutcomeVerificationError):
            zroky.verify_outcome(
                connector="generic_rest",
                record_ref="ord_123",
                claimed={"record_ref": "ord_123", "status": "approved"},
            )

    zroky.shutdown()
    _reset_sdk()


def test_agent_context_sets_agent_name(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_API_KEY", "test-key")
    monkeypatch.setenv("ZROKY_MODE", "local")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    captured_agent: list[str | None] = []

    def mock_enqueue(event):
        captured_agent.append(event.agent_name)

    zroky._queue.enqueue = mock_enqueue  # type: ignore[union-attr]

    with zroky.agent("research-agent"):
        assert zroky._get_agent() == "research-agent"
        from zroky._internal.models import CallEvent  # noqa: PLC0415
        zroky._queue.enqueue(CallEvent(  # type: ignore[union-attr]
            provider="test", model="test", messages=[],
            agent_name=zroky._get_agent(),
        ))

    assert captured_agent[0] == "research-agent"
    assert zroky._get_agent() is None  # restored after context
    zroky.shutdown()
    _reset_sdk()


def test_classify_error_token_overflow():
    exc = Exception("context_length_exceeded: tokens exceed 4096")
    assert zroky._classify_error(exc) == ErrorCode.TOKEN_OVERFLOW


def test_classify_error_token_overflow_provider_patterns():
    provider_errors = [
        "This model's maximum context length is 4096 tokens",
        "too many tokens in request body",
        "token-limit-exceeded by Azure deployment",
    ]
    for message in provider_errors:
        assert zroky._classify_error(Exception(message)) == ErrorCode.TOKEN_OVERFLOW


def test_classify_error_rate_limit():
    exc = Exception("429 Rate limit exceeded")
    assert zroky._classify_error(exc) == ErrorCode.RATE_LIMIT


def test_classify_error_auth_failure():
    exc = Exception("401 Invalid API key provided")
    assert zroky._classify_error(exc) == ErrorCode.AUTH_FAILURE


def test_classify_error_unknown():
    exc = Exception("some random error")
    assert zroky._classify_error(exc) == "UNKNOWN_ERROR"


def test_classify_error_uses_provider_status_code():
    class ProviderRateLimitError(Exception):
        status_code = 429

    assert (
        zroky._classify_error(ProviderRateLimitError("provider rejected request"))
        == ErrorCode.RATE_LIMIT
    )


def test_record_failure_includes_structured_failure_reason(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeResponse:
        status_code = 400
        headers = {"x-request-id": "req_123", "retry-after": "2"}

        def json(self):
            return {
                "error": {
                    "message": "Unknown parameter for user@example.com",
                    "type": "invalid_request_error",
                    "code": "unknown_parameter",
                    "param": "temperature",
                }
            }

    class ProviderBadRequestError(Exception):
        response = FakeResponse()
        request_id = "req_123"

    zroky.record(
        provider="openai",
        model="gpt-4o",
        request={"messages": [{"role": "user", "content": "hi"}]},
        error=ProviderBadRequestError("bad request for user@example.com"),
        latency_ms=12.0,
    )

    event = captured[0]
    assert event.error_code == ErrorCode.UNKNOWN_ERROR
    assert event.failure_reason["http_status"] == 400
    assert event.failure_reason["provider_error_code"] == "unknown_parameter"
    assert event.failure_reason["provider_error_param"] == "temperature"
    assert event.failure_reason["provider_request_id"] == "req_123"
    assert "user@example.com" not in event.failure_reason["message"]

    payload = event.to_ingest_payload()
    assert payload["failure_reason"]["provider_error_type"] == "invalid_request_error"
    assert payload["failure_reason"]["retry_after_seconds"] == 2.0

    zroky.shutdown()
    _reset_sdk()


def test_record_manual_capture(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeResponse:
        class usage:
            prompt_tokens = 100
            completion_tokens = 50
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0
        choices = []

    zroky.record(
        provider="openai",
        model="gpt-4o",
        request={"messages": [{"role": "user", "content": "hi"}]},
        response=FakeResponse(),
        latency_ms=42.0,
    )

    assert len(captured) == 1
    event = captured[0]
    assert event.provider == "openai"
    assert event.model == "gpt-4o"
    assert event.prompt_tokens == 100
    assert event.estimated_prompt_tokens is not None
    assert event.estimated_prompt_tokens > 0
    assert event.model_context_limit == 128000
    assert event.model_context_limit_source == "catalog_exact"
    assert event.model_context_limit_confidence == 0.95
    assert event.model_context_limit_catalog_version == "model_context_limits_2026_05_05"
    assert event.token_estimator_version == "chars_per_token_v1"
    assert event.token_rules_version == "token_rules_v2"
    assert event.latency_ms == 42.0
    assert isinstance(event.prompt_fingerprint, str)
    assert len(event.prompt_fingerprint) == 64
    ingest_payload = event.to_ingest_payload()
    assert ingest_payload["estimated_prompt_tokens"] == event.estimated_prompt_tokens
    assert ingest_payload["model_context_limit"] == 128000
    assert ingest_payload["model_context_limit_source"] == "catalog_exact"
    assert ingest_payload["model_context_limit_catalog_version"] == (
        "model_context_limits_2026_05_05"
    )
    assert ingest_payload["token_estimator_version"] == "chars_per_token_v1"
    assert ingest_payload["token_rules_version"] == "token_rules_v2"

    zroky.shutdown()
    _reset_sdk()


def test_python_sdk_payload_uses_ingest_event_v2_context(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(
            agent_framework="custom",
            session_id="sess_1",
            workflow_id="wf_1",
            workflow_name="support-resolution",
            prompt_version="support-v42",
            environment="production",
        )

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    zroky.record(
        provider="openai",
        model="gpt-4o",
        request={"messages": [{"role": "user", "content": "hi"}]},
        response=None,
        latency_ms=42.0,
        metadata={"release": "2026.05.23"},
    )

    payload = captured[0].to_ingest_payload()
    assert payload["schema_version"] == "v2"
    assert payload["event_id"] == f"{payload['call_id']}:capture"
    assert payload["agent_framework"] == "custom"
    assert payload["session_id"] == "sess_1"
    assert payload["workflow_id"] == "wf_1"
    assert payload["workflow_name"] == "support-resolution"
    assert payload["prompt_version"] == "support-v42"
    assert payload["environment"] == "production"
    assert payload["metadata"] == {"release": "2026.05.23"}

    zroky.shutdown()
    _reset_sdk()


def test_python_sdk_captures_retrieval_and_memory_spans(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(
            workflow_name="support-resolution",
            prompt_version="support-v42",
        )

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    retrieval_id = zroky.capture_retrieval(
        query="refund policy",
        index_name="support-kb",
        retriever_version="hybrid-v3",
        documents=[{"id": "doc_1", "title": "Refunds", "score": 0.91}],
        parent_call_id="parent_call",
    )
    memory_id = zroky.capture_memory(
        operation="write",
        namespace="customer-memory",
        keys=["user_123:preferences"],
        item_count=1,
        bytes_count=512,
        value_preview="prefers email updates",
    )

    assert [event.call_id for event in captured] == [retrieval_id, memory_id]
    retrieval_payload = captured[0].to_ingest_payload()
    assert retrieval_payload["provider"] == "retrieval"
    assert retrieval_payload["call_type"] == "retrieval"
    assert retrieval_payload["workflow_name"] == "support-resolution"
    assert retrieval_payload["prompt_version"] == "support-v42"
    assert retrieval_payload["parent_call_id"] == "parent_call"
    assert retrieval_payload["metadata"]["span_type"] == "retrieval"
    assert retrieval_payload["metadata"]["documents"][0]["id"] == "doc_1"

    memory_payload = captured[1].to_ingest_payload()
    assert memory_payload["provider"] == "memory"
    assert memory_payload["call_type"] == "memory"
    assert memory_payload["metadata"]["span_type"] == "memory"
    assert memory_payload["metadata"]["operation"] == "write"

    zroky.shutdown()
    _reset_sdk()


def test_record_uses_model_context_limit_override(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_MODEL_CONTEXT_LIMITS", '{"custom-model": 12345}')
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    zroky.record(
        provider="openai",
        model="custom-model",
        request={"messages": [{"role": "user", "content": "hi"}]},
        latency_ms=1.0,
    )

    assert captured[0].model_context_limit == 12345
    assert captured[0].model_context_limit_source == "env_override"
    assert captured[0].model_context_limit_source_detail == "ZROKY_MODEL_CONTEXT_LIMITS"

    zroky.shutdown()
    _reset_sdk()


def test_invalid_model_context_limit_override_warns(monkeypatch, caplog):
    monkeypatch.setenv(
        "ZROKY_MODEL_CONTEXT_LIMITS",
        "invalid-sdk-limit=0,custom-sdk-model=12345",
    )

    with caplog.at_level("WARNING", logger="zroky._internal.token_rules"):
        assert zroky._validation.known_model_context_limit("custom-sdk-model") == 12345

    assert "Ignoring invalid ZROKY_MODEL_CONTEXT_LIMITS entry" in caplog.text
    assert "invalid-sdk-limit=0" in caplog.text


def test_call_capture_sets_deterministic_prompt_fingerprint(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    messages_a = [{"role": "user", "content": "Summarize report id 123"}]
    messages_b = [{"role": "user", "content": "Summarize report id 999"}]
    tools = [{"type": "function", "function": {"name": "search"}}]

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=messages_a,
        tools=tools,
        _client=mock_client,
    )
    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=messages_b,
        tools=tools,
        _client=mock_client,
    )

    assert len(captured) == 2
    expected_a = generate_prompt_fingerprint(messages_a, tools, "gpt-4o")
    expected_b = generate_prompt_fingerprint(messages_b, tools, "gpt-4o")

    assert captured[0].prompt_fingerprint == expected_a
    assert captured[1].prompt_fingerprint == expected_b
    assert captured[0].prompt_fingerprint == captured[1].prompt_fingerprint

    zroky.shutdown()
    _reset_sdk()


def test_call_uses_original_provider_payload_and_masked_telemetry(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    messages = [{"role": "user", "content": "Email user@example.com"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Lookup user@example.com",
            },
        }
    ]

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=messages,
        tools=tools,
        _client=mock_client,
    )

    provider_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert provider_kwargs["messages"] == messages
    assert provider_kwargs["messages"] is not messages
    assert provider_kwargs["tools"] == tools
    assert provider_kwargs["tools"] is not tools
    assert provider_kwargs["messages"] is not captured[0].messages
    assert provider_kwargs["tools"] is not captured[0].tools
    assert captured[0].messages[0]["content"] == "Email [REDACTED_EMAIL]"
    assert captured[0].tools[0]["function"]["description"] == "Lookup [REDACTED_EMAIL]"
    assert messages[0]["content"] == "Email user@example.com"
    assert tools[0]["function"]["description"] == "Lookup user@example.com"

    zroky.shutdown()
    _reset_sdk()


def test_streaming_call_uses_original_provider_payload_and_masked_telemetry(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeChunk:
        choices = []

        class usage:
            prompt_tokens = 8
            completion_tokens = 3
            total_tokens = 11

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter([FakeChunk()])

    messages = [{"role": "user", "content": "Stream user@example.com"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Stream user@example.com",
            },
        }
    ]

    stream_iter = zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=messages,
        tools=tools,
        stream=True,
        _client=mock_client,
    )
    list(stream_iter)

    provider_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert provider_kwargs["stream"] is True
    assert provider_kwargs["messages"] == messages
    assert provider_kwargs["messages"] is not messages
    assert provider_kwargs["tools"] == tools
    assert provider_kwargs["tools"] is not tools
    assert provider_kwargs["messages"] is not captured[0].messages
    assert provider_kwargs["tools"] is not captured[0].tools
    assert captured[0].messages[0]["content"] == "Stream [REDACTED_EMAIL]"
    assert captured[0].tools[0]["function"]["description"] == "Stream [REDACTED_EMAIL]"
    assert messages[0]["content"] == "Stream user@example.com"
    assert tools[0]["function"]["description"] == "Stream user@example.com"

    zroky.shutdown()
    _reset_sdk()


def test_call_error_path_uses_original_provider_payload_and_masked_telemetry(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("provider boom")

    messages = [{"role": "user", "content": "Fail user@example.com"}]

    with pytest.raises(RuntimeError, match="provider boom"):
        zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=messages,
            _client=mock_client,
        )

    provider_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert provider_kwargs["messages"] == messages
    assert provider_kwargs["messages"] is not messages
    assert captured[0].status == "failed"
    assert captured[0].messages[0]["content"] == "Fail [REDACTED_EMAIL]"
    assert captured[0].error_message == "provider boom"
    assert messages[0]["content"] == "Fail user@example.com"

    zroky.shutdown()
    _reset_sdk()


def test_streaming_response_chunks_are_masked_in_telemetry(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeFunction:
        name = "lookup"
        arguments = (
            '{"email":"stream-tool@example.com",'
            '"api_key":"sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"}'
        )

    class FakeToolCall:
        id = "tool-1"
        type = "function"
        function = FakeFunction()

    class FakeDelta:
        content = "partial stream@example.com"
        tool_calls = [FakeToolCall()]

    class FakeChoice:
        delta = FakeDelta()

    class FakeChunk:
        choices = [FakeChoice()]
        usage = None

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter([FakeChunk()])

    stream_iter = zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "safe"}],
        stream=True,
        _client=mock_client,
    )
    list(stream_iter)

    rendered_tool_calls = str(captured[0].tool_calls_made)
    assert "stream@example.com" not in captured[0].output_content
    assert "stream-tool@example.com" not in rendered_tool_calls
    assert "sk-proj-" not in rendered_tool_calls
    assert "[REDACTED_EMAIL]" in captured[0].output_content
    assert "[REDACTED_KEY]" in rendered_tool_calls

    zroky.shutdown()
    _reset_sdk()


def test_error_message_is_masked_before_telemetry(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError(
        "provider failed for user@example.com with sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"
    )

    with pytest.raises(RuntimeError):
        zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "safe"}],
            _client=mock_client,
        )

    assert "user@example.com" not in captured[0].error_message
    assert "sk-proj-" not in captured[0].error_message
    assert "[REDACTED_EMAIL]" in captured[0].error_message
    assert "[REDACTED_KEY]" in captured[0].error_message

    zroky.shutdown()
    _reset_sdk()


def test_response_tool_call_arguments_are_masked(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeFunction:
        name = "lookup"
        arguments = (
            '{"email":"tool@example.com",'
            '"api_key":"sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"}'
        )

    class FakeToolCall:
        id = "tool-1"
        type = "function"
        function = FakeFunction()

    class FakeMessage:
        content = "Answer for result@example.com"
        tool_calls = [FakeToolCall()]

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        usage = None
        choices = [FakeChoice()]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "safe"}],
        _client=mock_client,
    )

    rendered_tool_calls = str(captured[0].tool_calls_made)
    assert "tool@example.com" not in rendered_tool_calls
    assert "sk-proj-" not in rendered_tool_calls
    assert "result@example.com" not in captured[0].output_content
    assert "[REDACTED_EMAIL]" in rendered_tool_calls
    assert "[REDACTED_KEY]" in rendered_tool_calls
    assert captured[0].output_fingerprint is not None
    assert "result@example.com" not in (captured[0].normalized_output or "")
    assert captured[0].tool_lifecycle_summary[0]["tool_name"] == "lookup"

    zroky.shutdown()
    _reset_sdk()


def test_call_error_payload_includes_token_estimate_without_usage(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError(
        "maximum context length exceeded"
    )

    messages = [{"role": "user", "content": "x" * 16000}]

    with pytest.raises(RuntimeError, match="maximum context length exceeded"):
        zroky.call(
            provider="openai",
            model="gpt-3.5-turbo",
            messages=messages,
            _client=mock_client,
        )

    event = captured[0]
    assert event.error_code == ErrorCode.TOKEN_OVERFLOW
    assert event.prompt_tokens == 0
    assert event.estimated_prompt_tokens is not None
    assert event.estimated_prompt_tokens > 0
    assert event.model_context_limit == 4096
    assert event.model_context_limit_source == "catalog_exact"
    assert event.model_context_limit_catalog_version == "model_context_limits_2026_05_05"
    assert event.token_estimator_version == "chars_per_token_v1"
    assert event.token_rules_version == "token_rules_v2"
    ingest_payload = event.to_ingest_payload()
    assert ingest_payload["estimated_prompt_tokens"] == event.estimated_prompt_tokens
    assert ingest_payload["model_context_limit"] == 4096
    assert ingest_payload["model_context_limit_source"] == "catalog_exact"
    assert ingest_payload["model_context_limit_catalog_version"] == (
        "model_context_limits_2026_05_05"
    )
    assert ingest_payload["token_estimator_version"] == "chars_per_token_v1"
    assert ingest_payload["token_rules_version"] == "token_rules_v2"

    zroky.shutdown()
    _reset_sdk()


def test_provider_payload_guard_recovers_without_raising(caplog):
    original_messages = [{"role": "user", "content": "Email user@example.com"}]
    telemetry_messages = [{"role": "user", "content": "Email [REDACTED_EMAIL]"}]
    original_tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Lookup user@example.com",
            },
        }
    ]
    telemetry_tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Lookup [REDACTED_EMAIL]",
            },
        }
    ]

    with caplog.at_level("WARNING", logger="zroky"):
        provider_messages, provider_tools = zroky._ensure_provider_payload_is_isolated(
            original_messages=original_messages,
            provider_messages=telemetry_messages,
            telemetry_messages=telemetry_messages,
            original_tools=original_tools,
            provider_tools=telemetry_tools,
            telemetry_tools=telemetry_tools,
            model="gpt-4o",
            call_id="call-123",
            mode="stream",
        )

    assert provider_messages == original_messages
    assert provider_messages is not original_messages
    assert provider_messages is not telemetry_messages
    assert provider_tools == original_tools
    assert provider_tools is not original_tools
    assert provider_tools is not telemetry_tools
    assert "recovered provider payload" in caplog.text
    assert "model=gpt-4o" in caplog.text
    assert "call_id=call-123" in caplog.text
    assert "mode=stream" in caplog.text
    assert caplog.text.count("recovered provider payload") == 1


def test_provider_kwargs_removes_duplicate_payload_keys(caplog):
    kwargs = {
        "messages": [{"role": "user", "content": "ignored"}],
        "tools": [{"type": "function"}],
        "stream": False,
        "temperature": 0.2,
        "extra_body": {"metadata": {"safe": True}},
    }

    with caplog.at_level("ERROR", logger="zroky"):
        provider_kwargs = zroky._build_provider_kwargs(
            kwargs,
            model="gpt-4o",
            call_id="call-456",
            mode="non-stream",
        )

    assert "messages" not in provider_kwargs
    assert "tools" not in provider_kwargs
    assert "stream" not in provider_kwargs
    assert provider_kwargs["temperature"] == 0.2
    assert provider_kwargs["extra_body"] is kwargs["extra_body"]
    assert "messages" in kwargs
    assert "tools" in kwargs
    assert "stream" in kwargs
    assert "keys=messages,stream,tools" in caplog.text
    assert "model=gpt-4o" in caplog.text
    assert "call_id=call-456" in caplog.text
    assert "mode=non-stream" in caplog.text


def test_validate_does_not_mutate_input():
    payload = {
        "model": "gpt-4o",
        "api_key": "sk-example-1234567890",
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [{"type": "function", "function": {"name": "search"}}],
        "meta": {"recent_calls": 2},
    }
    original = deepcopy(payload)

    result = zroky.validate(payload)

    assert isinstance(result, dict)
    assert payload == original


def test_verbose_logs_include_prompt_fingerprint(monkeypatch, capsys):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VERBOSE", "true")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "summarize report id 123"}],
        tools=[{"name": "search"}],
        _client=mock_client,
    )

    captured_stdout = capsys.readouterr().out
    assert "fp=" in captured_stdout
    assert "call captured" in captured_stdout.lower()

    zroky.shutdown()
    _reset_sdk()


def test_init_reads_preflight_validation_flag(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    assert zroky._config is not None
    assert zroky._config.validate_preflight is True

    zroky.shutdown()
    _reset_sdk()


def test_init_reads_preflight_sample_rate(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE", "0.25")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    assert zroky._config is not None
    assert zroky._config.validate_preflight is True
    assert zroky._config.validate_preflight_sample_rate == pytest.approx(0.25)

    zroky.shutdown()
    _reset_sdk()


def test_init_reads_global_fallback_policy(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_FALLBACK_MODELS", "gpt-4o-mini,claude-3-haiku")
    monkeypatch.setenv("ZROKY_FALLBACK_ADAPTIVE", "true")
    monkeypatch.setenv("ZROKY_FALLBACK_MAX", "1")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    assert zroky._config is not None
    assert zroky._config.fallback_models == ("gpt-4o-mini", "claude-3-haiku")
    assert zroky._config.fallback_adaptive is True
    assert zroky._config.fallback_max == 1

    zroky.shutdown()
    _reset_sdk()


def test_init_reads_preflight_blocking_warning_types(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_PREFLIGHT_BLOCKING_WARNINGS", "auth_risk,rate_limit_risk")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    assert zroky._config is not None
    assert zroky._config.preflight_blocking_warning_types == (
        "AUTH_RISK",
        "RATE_LIMIT_RISK",
    )

    zroky.shutdown()
    _reset_sdk()


def test_init_rejects_invalid_preflight_sample_rate(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE", "1.5")

    with patch("zroky._internal.queue.LocalWriter"):
        with pytest.raises(ValueError):
            zroky.init()

    _reset_sdk()


def test_init_rejects_non_numeric_preflight_sample_rate(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE", "abc")

    with patch("zroky._internal.queue.LocalWriter"):
        with pytest.raises(ValueError, match="ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE"):
            zroky.init()

    _reset_sdk()


def test_init_argument_overrides_preflight_env_values(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "false")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE", "0.10")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(
            validate_preflight=True,
            validate_preflight_sample_rate=0.75,
        )

    assert zroky._config is not None
    assert zroky._config.validate_preflight is True
    assert zroky._config.validate_preflight_sample_rate == pytest.approx(0.75)

    zroky.shutdown()
    _reset_sdk()


def test_call_preflight_prints_when_warnings_present(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    validate_calls: list[dict] = []
    print_calls: list[dict] = []

    monkeypatch.setattr(
        zroky._validation,
        "validate",
        lambda payload: validate_calls.append(payload) or {
            "valid": False,
            "warnings": [
                {
                    "type": "TOKEN_OVERFLOW",
                    "confidence": 0.92,
                    "message": "High token usage.",
                    "suggested_fix": "Trim history.",
                }
            ],
        },
    )
    monkeypatch.setattr(
        zroky._validation,
        "print_validation",
        lambda result: print_calls.append(result),
    )

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        _client=mock_client,
    )

    assert len(validate_calls) == 1
    assert len(print_calls) == 1

    zroky.shutdown()
    _reset_sdk()


def test_call_preflight_sampling_zero_skips_validation(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE", "0.0")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    validate_calls: list[dict] = []
    print_calls: list[dict] = []

    monkeypatch.setattr(
        zroky._validation,
        "validate",
        lambda payload: validate_calls.append(payload) or {
            "valid": False,
            "warnings": [
                {
                    "type": "TOKEN_OVERFLOW",
                    "confidence": 0.92,
                    "message": "High token usage.",
                    "suggested_fix": "Trim history.",
                }
            ],
        },
    )
    monkeypatch.setattr(
        zroky._validation,
        "print_validation",
        lambda result: print_calls.append(result),
    )

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        _client=mock_client,
    )

    assert len(validate_calls) == 0
    assert len(print_calls) == 0

    zroky.shutdown()
    _reset_sdk()


def test_call_preflight_silent_when_no_warnings(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    validate_calls: list[dict] = []
    print_calls: list[dict] = []

    monkeypatch.setattr(
        zroky._validation,
        "validate",
        lambda payload: validate_calls.append(payload) or {"valid": True, "warnings": []},
    )
    monkeypatch.setattr(
        zroky._validation,
        "print_validation",
        lambda result: print_calls.append(result),
    )

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        _client=mock_client,
    )

    assert len(validate_calls) == 1
    assert len(print_calls) == 0

    zroky.shutdown()
    _reset_sdk()


def test_call_preflight_failure_never_blocks_provider_call(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    expected_response = FakeResponse()
    mock_client.chat.completions.create.return_value = expected_response

    monkeypatch.setattr(
        zroky._validation,
        "validate",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("validation boom")),
    )

    response = zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        _client=mock_client,
    )

    assert response is expected_response

    zroky.shutdown()
    _reset_sdk()


def test_call_preflight_blocking_auth_risk_records_blocked_event(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(preflight_blocking_warning_types=["AUTH_RISK"])

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    with pytest.raises(zroky.ZrokyPreflightError):
        zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
        )

    assert len(captured) == 1
    event = captured[0]
    assert event.status == "blocked"
    assert event.error_code == ErrorCode.AUTH_FAILURE
    assert event.failure_reason["schema_version"] == "zroky.preflight_block.v1"
    assert event.failure_reason["preflight_warning_types"] == ["AUTH_RISK"]

    zroky.shutdown()
    _reset_sdk()


def test_call_preflight_populates_recent_calls_meta(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    captured_recent_calls: list[int] = []

    def _capture_validate(payload: dict):
        meta = payload.get("meta", {})
        captured_recent_calls.append(int(meta.get("recent_calls", 0)))
        return {"valid": True, "warnings": []}

    monkeypatch.setattr(zroky._validation, "validate", _capture_validate)

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello world"}],
        _client=mock_client,
    )
    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello there"}],
        _client=mock_client,
    )

    assert len(captured_recent_calls) == 2
    assert captured_recent_calls[0] >= 1
    assert captured_recent_calls[1] >= captured_recent_calls[0]

    zroky.shutdown()
    _reset_sdk()


def test_preflight_sampling_is_deterministic_for_same_key() -> None:
    first = zroky._is_preflight_sampled_in(
        sample_rate=0.33,
        sample_key="openai|gpt-4o|fp-abc",
    )
    second = zroky._is_preflight_sampled_in(
        sample_rate=0.33,
        sample_key="openai|gpt-4o|fp-abc",
    )

    assert first == second
