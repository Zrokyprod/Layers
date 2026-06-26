from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "zroky-backend"
SDK_DIR = ROOT / "zroky-sdk"

PROJECT_ID = "demo-verified-action-stripe-money-path"
ACTION_IDEMPOTENCY_KEY = "case_1001_stripe_refund"
EXECUTION_IDEMPOTENCY_KEY = "exec_case_1001_stripe_refund"
TRACE_ID = "trace-verified-action-stripe-refund"
CALL_ID = "call-verified-action-stripe-refund"
STRIPE_REFUND_ID = "re_zroky_verified_action_demo"
STRIPE_CHARGE_ID = "ch_zroky_verified_action_demo"
REFUND_AMOUNT_MINOR = 4218


def _configure_env(db_path: Path) -> None:
    os.environ.update(
        {
            "TESTING": "true",
            "APP_ENV": "test",
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "DATABASE_READ_REPLICA_URL": "",
            "ALLOW_PROJECT_HEADER_CONTEXT": "true",
            "INGEST_ENFORCE_RATE_LIMIT": "false",
            "BILLING_ENFORCE_QUOTA": "false",
            "ENABLE_READY_REDIS_CHECK": "false",
            "ACTION_RECEIPT_SIGNING_SECRET": "test-action-receipt-secret-minimum-32-bytes",
            "ACTION_RECEIPT_SIGNING_KEY_ID": "test-action-receipt-key",
            "ZROKY_RUNNER_SECRET_PAYMENTS_STRIPE": json.dumps(
                {"secret_key": "sk_test_zroky_verified_action_demo"}
            ),
        }
    )


def _assert_response(response: Any, expected_status: int, label: str) -> dict[str, Any]:
    if response.status_code != expected_status:
        raise RuntimeError(
            f"{label} failed: HTTP {response.status_code}: {response.text[:1200]}"
        )
    parsed = response.json()
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label} returned a non-object JSON response.")
    return parsed


class _MoneyPathTransport(httpx.BaseTransport):
    def __init__(self, client: Any) -> None:
        self.client = client
        self.stripe_requests: list[dict[str, Any]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.zroky.local":
            headers = dict(request.headers)
            response = self.client.request(
                request.method,
                str(request.url.raw_path.decode("utf-8")),
                headers=headers,
                content=request.content,
            )
            response_headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
            }
            return httpx.Response(
                response.status_code,
                headers=response_headers,
                content=response.content,
                request=request,
            )
        if request.url.host == "api.stripe.com":
            return self._stripe_response(request)
        return httpx.Response(
            502,
            json={"error": f"unexpected outbound host: {request.url.host}"},
            request=request,
        )

    def _stripe_response(self, request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or request.url.path != "/v1/refunds":
            return httpx.Response(404, json={"error": "not_found"}, request=request)
        auth_header = request.headers.get("authorization", "")
        if auth_header != "Bearer sk_test_zroky_verified_action_demo":
            return httpx.Response(401, json={"error": "invalid_api_key"}, request=request)
        form = parse_qs(request.content.decode("utf-8"))
        charge = form.get("charge", [""])[0]
        amount = int(form.get("amount", ["0"])[0])
        self.stripe_requests.append(
            {
                "method": request.method,
                "path": request.url.path,
                "charge": charge,
                "amount": amount,
                "idempotency_key": request.headers.get("idempotency-key"),
            }
        )
        return httpx.Response(
            200,
            json={
                "id": STRIPE_REFUND_ID,
                "object": "refund",
                "charge": charge,
                "amount": amount,
                "currency": "usd",
                "status": "succeeded",
                "metadata": {"zroky_refund_id": "rf_zroky_demo_1001"},
            },
            request=request,
        )


def _headers() -> dict[str, str]:
    return {"X-Project-Id": PROJECT_ID}


def _register_contract(client: Any) -> dict[str, Any]:
    return _assert_response(
        client.post(
            "/v1/action-contracts",
            headers=_headers(),
            json={
                "contract_key": "customer.refund.transfer",
                "version": "1.0",
                "action_type": "customer.refund.transfer",
                "operation_kind": "TRANSFER",
                "domain_family": "customer_operations",
                "risk_class": "R3",
                "connector_family": "stripe_refund",
                "schema": {
                    "type": "object",
                    "required": ["resource", "parameters"],
                    "properties": {
                        "resource": {"type": "object"},
                        "parameters": {"type": "object"},
                    },
                },
                "verification_profile": {
                    "minimum_level": "V4",
                    "source_of_record": "stripe_refunds_api",
                },
            },
        ),
        201,
        "register action contract",
    )


def _create_and_authorize_intent(client: Any) -> dict[str, Any]:
    intent = _assert_response(
        client.post(
            "/v1/action-intents",
            headers={**_headers(), "Idempotency-Key": ACTION_IDEMPOTENCY_KEY},
            json={
                "contract_version": "customer.refund.transfer/1.0",
                "action_type": "customer.refund.transfer",
                "operation_kind": "TRANSFER",
                "environment": "production",
                "principal": {"type": "user", "id": "support-owner"},
                "actor_chain": [
                    {"type": "agent", "id": "refund-agent", "version": "1.0.0"}
                ],
                "purpose": {
                    "code": "support_refund",
                    "case_id": "case_1001",
                    "summary": "Issue approved support refund for order ORD-1001.",
                },
                "resource": {
                    "type": "payment.refund",
                    "id": "rf_zroky_demo_1001",
                    "provider": "stripe",
                    "charge": STRIPE_CHARGE_ID,
                },
                "parameters": {
                    "amount_minor": REFUND_AMOUNT_MINOR,
                    "currency": "USD",
                    "reason": "requested_by_customer",
                },
                "verification_profile": "stripe.refund.finality/1.0",
                "trace_context": {
                    "trace_id": TRACE_ID,
                    "call_id": CALL_ID,
                    "agent_name": "refund-agent",
                },
            },
        ),
        201,
        "create action intent",
    )
    pending = _assert_response(
        client.post(f"/v1/action-intents/{intent['action_id']}/decide", headers=_headers()),
        200,
        "policy decision pending approval",
    )
    approval_response = client.post(
        f"/v1/runtime-policy/approvals/{pending['runtime_policy_decision_id']}/approve",
        headers=_headers(),
        json={"reason": "Refund amount and customer case reviewed."},
    )
    if approval_response.status_code != 200:
        approval_queue = client.get("/v1/runtime-policy/approvals?status=all", headers=_headers())
        raise RuntimeError(
            "approve protected action failed: "
            f"HTTP {approval_response.status_code}: {approval_response.text[:800]}; "
            f"pending_decision={json.dumps(pending, sort_keys=True, default=str)}; "
            f"approval_queue={approval_queue.text[:1200]}"
        )
    _assert_response(approval_response, 200, "approve protected action")
    authorized = _assert_response(
        client.post(f"/v1/action-intents/{intent['action_id']}/decide", headers=_headers()),
        200,
        "authorize protected action",
    )
    if authorized["status"] != "authorized":
        raise RuntimeError(f"action intent was not authorized: {authorized}")
    return {
        "intent": intent,
        "pending_decision": pending,
        "authorized": authorized,
    }


def _register_runner_and_attempt(client: Any, *, action_id: str) -> dict[str, Any]:
    runner = _assert_response(
        client.post(
            "/v1/action-runners",
            headers=_headers(),
            json={
                "name": "stripe-refund-proof-runner",
                "runner_type": "customer_hosted",
                "environment": "production",
                "supported_operation_kinds": ["TRANSFER"],
                "credential_scope": {
                    "provider": "stripe",
                    "allowed_prefixes": ["customer-runner-secret://payments"],
                },
                "capability_version": "zroky-python-runner/0.1.0",
            },
        ),
        201,
        "register runner",
    )
    attempt = _assert_response(
        client.post(
            f"/v1/action-intents/{action_id}/execution-attempts",
            headers={**_headers(), "Idempotency-Key": EXECUTION_IDEMPOTENCY_KEY},
            json={
                "runner_id": runner["runner_id"],
                "credential_ref": "customer-runner-secret://payments/stripe",
                "execution_plan": {
                    "adapter": "stripe_refund",
                    "operation": "refund.create",
                    "target": {
                        "refund_id": "rf_zroky_demo_1001",
                        "charge": STRIPE_CHARGE_ID,
                    },
                    "arguments": {
                        "amount_minor": REFUND_AMOUNT_MINOR,
                        "currency": "USD",
                        "reason": "requested_by_customer",
                    },
                    "verification": {"source_of_record": "stripe_refunds_api"},
                },
            },
        ),
        201,
        "create execution attempt",
    )
    return {"runner": runner, "attempt": attempt}


def _verify_outcome(client: Any, *, policy_decision_id: str) -> dict[str, Any]:
    return _assert_response(
        client.post(
            "/v1/outcomes/reconciliation",
            headers=_headers(),
            json={
                "call_id": CALL_ID,
                "trace_id": TRACE_ID,
                "runtime_policy_decision_id": policy_decision_id,
                "action_type": "refund",
                "connector_type": "stripe_refunds_api",
                "system_ref": f"stripe:{STRIPE_REFUND_ID}",
                "claimed": {
                    "refund_id": STRIPE_REFUND_ID,
                    "amount": REFUND_AMOUNT_MINOR,
                    "currency": "USD",
                    "status": "succeeded",
                },
                "actual": {
                    "refund_id": STRIPE_REFUND_ID,
                    "amount": REFUND_AMOUNT_MINOR,
                    "currency": "usd",
                    "status": "succeeded",
                },
                "actual_record_found": True,
                "match_fields": ["refund_id", "amount", "currency", "status"],
                "amount_usd": REFUND_AMOUNT_MINOR / 100,
                "currency": "USD",
                "idempotency_key": f"verify:{policy_decision_id}:{STRIPE_REFUND_ID}",
                "metadata": {
                    "source": "verified_action_money_path",
                    "connector": {
                        "provider": "stripe",
                        "http_status": 200,
                        "retryable": False,
                    },
                },
            },
        ),
        201,
        "verify refund outcome",
    )


def _source_mutations(client: Any, *, action_id: str, receipt_id: str) -> dict[str, Any]:
    matched = _assert_response(
        client.post(
            "/v1/outcomes/reconciliation/source-mutations",
            headers=_headers(),
            json={
                "source_system": "stripe",
                "mutation_id": f"evt_{STRIPE_REFUND_ID}",
                "action_type": "refund",
                "resource_type": "refund",
                "resource_id": STRIPE_REFUND_ID,
                "system_ref": f"stripe:{STRIPE_REFUND_ID}",
                "actor_type": "zroky_runner",
                "actor_id": "stripe-refund-proof-runner",
                "zroky_action_id": action_id,
                "action_receipt_id": receipt_id,
                "idempotency_key": ACTION_IDEMPOTENCY_KEY,
                "metadata": {"protected_action": True},
            },
        ),
        201,
        "ingest matched source mutation",
    )
    bypass = _assert_response(
        client.post(
            "/v1/outcomes/reconciliation/source-mutations",
            headers=_headers(),
            json={
                "source_system": "stripe",
                "mutation_id": "evt_unreceipted_agent_refund",
                "action_type": "refund",
                "resource_type": "refund",
                "resource_id": "re_unreceipted_agent_refund",
                "system_ref": "stripe:re_unreceipted_agent_refund",
                "actor_type": "ai_agent",
                "actor_id": "refund-agent",
                "metadata": {"protected_action": True},
            },
        ),
        201,
        "ingest bypass source mutation",
    )
    summary = _assert_response(
        client.get("/v1/outcomes/reconciliation/source-mutations/summary", headers=_headers()),
        200,
        "source mutation summary",
    )
    return {"matched": matched, "bypass": bypass, "summary": summary}


def run_verified_action_money_path(
    *,
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings(
        "ignore",
        message=r"Using `httpx` with `starlette\.testclient` is deprecated.*",
    )
    with tempfile.TemporaryDirectory(prefix="zroky-verified-action-money-path-") as temp_dir:
        db_path = Path(temp_dir) / "money_path.db"
        _configure_env(db_path)
        sys.path.insert(0, str(BACKEND_DIR))
        sys.path.insert(0, str(SDK_DIR))

        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.core.config import get_settings
        from app.db.base import Base
        from app.db.models import Project
        from app.db.session import get_db_session, get_db_session_read
        from app.main import app
        from app.services.entitlements_resolver import invalidate_all
        from zroky import ProtectedActionRunner

        get_settings.cache_clear()
        invalidate_all()
        engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        Base.metadata.create_all(bind=engine)

        def override_get_db_session() -> Any:
            session = session_local()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db_session] = override_get_db_session
        app.dependency_overrides[get_db_session_read] = override_get_db_session

        try:
            with session_local() as session:
                session.add(Project(id=PROJECT_ID, name="Verified Action Stripe Money Path"))
                session.commit()

            with TestClient(app) as client:
                _register_contract(client)
                intent_state = _create_and_authorize_intent(client)
                action_id = str(intent_state["intent"]["action_id"])
                policy_decision_id = str(intent_state["authorized"]["runtime_policy_decision_id"])
                runner_state = _register_runner_and_attempt(client, action_id=action_id)

                transport = _MoneyPathTransport(client)
                runner = ProtectedActionRunner(
                    runner_id=str(runner_state["runner"]["runner_id"]),
                    api_key="zk_demo_verified_action_money_path",
                    project=PROJECT_ID,
                    api_base="https://api.zroky.local",
                    transport=transport,
                )
                run_result = runner.run_once(
                    runner_metadata={"runner_instance_id": "money-path-proof-runner"}
                )
                if run_result["status"] != "succeeded":
                    raise RuntimeError(f"runner did not succeed: {run_result}")

                verification = _verify_outcome(client, policy_decision_id=policy_decision_id)
                receipt = _assert_response(
                    client.post(f"/v1/action-intents/{action_id}/receipt", headers=_headers()),
                    201,
                    "generate action receipt",
                )
                source_mutations = _source_mutations(
                    client,
                    action_id=action_id,
                    receipt_id=str(receipt["receipt_id"]),
                )
                timeline = _assert_response(
                    client.get(f"/v1/action-intents/{action_id}/timeline", headers=_headers()),
                    200,
                    "read action timeline",
                )

            summary = {
                "mode": "deterministic_mock",
                "project_id": PROJECT_ID,
                "action_id": action_id,
                "intent_digest": intent_state["intent"]["intent_digest"],
                "approval_decision_id": intent_state["pending_decision"][
                    "runtime_policy_decision_id"
                ],
                "policy_decision_id": policy_decision_id,
                "runner_id": runner_state["runner"]["runner_id"],
                "attempt_id": runner_state["attempt"]["attempt_id"],
                "runner_status": run_result["status"],
                "stripe_refund_id": STRIPE_REFUND_ID,
                "stripe_request_count": len(transport.stripe_requests),
                "stripe_idempotency_key": transport.stripe_requests[0]["idempotency_key"],
                "verification_id": verification["id"],
                "verification_status": verification["verification_status"],
                "receipt_id": receipt["receipt_id"],
                "receipt_digest": receipt["receipt_digest"],
                "receipt_signature_valid": receipt["signature_valid"],
                "receipt_final_status": receipt["receipt"]["final_status"],
                "receipt_evidence_hash": receipt["receipt"]["evidence"]["evidence_hash"],
                "protected_credential_returned": receipt["receipt"]["runner_execution"][
                    "protected_credential_returned"
                ],
                "source_mutation_matched_classification": source_mutations["matched"][
                    "classification"
                ],
                "source_mutation_bypass_classification": source_mutations["bypass"][
                    "classification"
                ],
                "source_mutation_unreceipted": source_mutations["summary"]["unreceipted"],
                "timeline_event_types": [item["event_type"] for item in timeline["items"]],
                "secrets_redacted": "sk_test_zroky_verified_action_demo"
                not in json.dumps(
                    {
                        "summary": run_result,
                        "receipt": receipt,
                        "verification": verification,
                    },
                    sort_keys=True,
                    default=str,
                ),
                "live_customer_proof_required": True,
                "claim": (
                    "Deterministic verified-action Stripe refund proof passed. "
                    "Final paid launch still requires live design-partner owner proof."
                ),
            }
            if artifact_dir is not None:
                artifact_dir.mkdir(parents=True, exist_ok=True)
                (artifact_dir / "verified_action_stripe_money_path_summary.json").write_text(
                    json.dumps(summary, indent=2, sort_keys=True, default=str),
                    encoding="utf-8",
                )
                (artifact_dir / "verified_action_stripe_action_receipt.json").write_text(
                    json.dumps(receipt, indent=2, sort_keys=True, default=str),
                    encoding="utf-8",
                )
            return summary
        finally:
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)
            engine.dispose()
            invalidate_all()
            get_settings.cache_clear()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the deterministic Zroky Verified Action Stripe money-path proof.",
    )
    parser.add_argument("--json", action="store_true", help="Print compact JSON only.")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Optional directory for summary and action receipt JSON artifacts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    summary = run_verified_action_money_path(artifact_dir=args.artifact_dir)
    if args.json:
        print(json.dumps(summary, sort_keys=True, separators=(",", ":"), default=str))
    else:
        for key in (
            "project_id",
            "action_id",
            "runner_status",
            "verification_status",
            "receipt_final_status",
            "receipt_digest",
            "source_mutation_bypass_classification",
        ):
            print(f"{key}={summary[key]}")
        print("[verified-action-money-path] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
