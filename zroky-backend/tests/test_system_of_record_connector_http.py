from __future__ import annotations

import json

import httpx

from app.services.system_of_record_connectors import LedgerRefundApiConnector


def test_ledger_refund_http_connector_retries_retryable_status_then_matches() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": "rf_1001",
                    "amount_cents": 4250,
                    "currency": "usd",
                    "state": "posted",
                }
            },
        )

    connector = LedgerRefundApiConnector(
        base_url="https://ledger.example.com/api",
        refund_id="rf_1001",
        bearer_token="ledger-secret-token",
        path_template="/refunds/{refund_id}",
        record_path="data",
        max_attempts=3,
        transport=httpx.MockTransport(handler),
    )

    source = connector.fetch()

    assert len(requests) == 2
    assert requests[0].headers["authorization"] == "Bearer ledger-secret-token"
    assert source.record == {
        "id": "rf_1001",
        "amount_cents": 4250,
        "currency": "USD",
        "state": "posted",
        "refund_id": "rf_1001",
        "amount_usd": 42.5,
        "status": "posted",
    }
    assert source.record_found is True
    assert source.metadata is not None
    assert source.metadata["http_status"] == 200
    assert source.metadata["attempts"] == 2
    assert source.metadata["retry_count"] == 1
    assert source.metadata["max_attempts"] == 3
    assert source.metadata["retryable"] is False
    assert source.metadata["transient_errors"] == ["http_503"]
    assert "ledger-secret-token" not in json.dumps(source.metadata)


def test_ledger_refund_http_connector_classifies_auth_failure_without_retry() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(401, json={"error": "unauthorized"})

    connector = LedgerRefundApiConnector(
        base_url="https://ledger.example.com/api",
        refund_id="rf_auth",
        bearer_token="bad-token",
        path_template="/refunds/{refund_id}",
        record_path="data",
        max_attempts=3,
        transport=httpx.MockTransport(handler),
    )

    source = connector.fetch()

    assert len(requests) == 1
    assert source.record is None
    assert source.record_found is None
    assert source.metadata is not None
    assert source.metadata["http_status"] == 401
    assert source.metadata["error"] == "http_error"
    assert source.metadata["error_code"] == "auth_failed"
    assert source.metadata["attempts"] == 1
    assert source.metadata["max_attempts"] == 3
    assert source.metadata["retryable"] is False
    assert "bad-token" not in json.dumps(source.metadata)


def test_ledger_refund_http_connector_turns_config_error_into_missing_proof() -> None:
    connector = LedgerRefundApiConnector(
        base_url="https://ledger.example.com/api",
        refund_id="rf_config",
        path_template="/refunds/{missing_refund_id}",
        max_attempts=3,
        fail_closed_config_errors=True,
    )

    source = connector.fetch()

    assert source.record is None
    assert source.record_found is None
    assert source.metadata is not None
    assert source.metadata["request_url"] == "connector_url_unavailable"
    assert source.metadata["error"] == "connector_config_error"
    assert source.metadata["error_code"] == "connector_config_invalid"
    assert source.metadata["attempts"] == 0
    assert source.metadata["max_attempts"] == 3
    assert source.metadata["retryable"] is False
