from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from uuid import uuid4


class Failure(RuntimeError):
    pass


def _json(text: str) -> Any:
    try:
        return json.loads(text) if text else None
    except json.JSONDecodeError:
        return None


def _request(method: str, url: str, *, headers: dict[str, str] | None = None, payload: Any = None, timeout: float = 20) -> tuple[int, Any, str]:
    request_headers = dict(headers or {})
    data = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json" if isinstance(payload, dict) else "application/x-www-form-urlencoded"
        data = (json.dumps(payload, separators=(",", ":")) if isinstance(payload, dict) else urllib.parse.urlencode(payload)).encode()
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            text = res.read().decode("utf-8", "replace")
            return res.status, _json(text), text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        return exc.code, _json(text), text


def _url(base: str, path: str) -> str:
    return urllib.parse.urljoin(f"{base.rstrip('/')}/", path.lstrip("/"))


def _expect(status: int, body: Any, text: str, expected: int, label: str) -> Any:
    if status != expected:
        raise Failure(f"{label}: expected {expected}, got {status}: {text[:700]}")
    if not isinstance(body, dict):
        raise Failure(f"{label}: expected JSON object")
    print(f"[PASS] {label}")
    return body


def _backend_headers(args: argparse.Namespace) -> dict[str, str]:
    headers = {"x-project-id": args.project_id}
    if args.api_key:
        headers["x-api-key"] = args.api_key
    bearer = os.environ.get(args.bearer_env, "").strip()
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return headers


def _stripe_headers(secret: str, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {secret}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _stripe_refund(args: argparse.Namespace, secret: str, run_id: str) -> dict[str, Any]:
    if args.stripe_refund_id:
        status, body, text = _request("GET", f"https://api.stripe.com/v1/refunds/{args.stripe_refund_id}", headers=_stripe_headers(secret), timeout=args.timeout)
        return _expect(status, body, text, 200, "stripe refund read")
    if not args.create_test_refund:
        raise Failure("Pass --stripe-refund-id or --create-test-refund.")

    charge_payload = {"amount": str(args.amount), "currency": args.currency, "source": "tok_visa", "description": f"Zroky test loop {run_id}"}
    status, charge, text = _request(
        "POST",
        "https://api.stripe.com/v1/charges",
        headers=_stripe_headers(secret, f"zroky-charge-{run_id}"),
        payload=charge_payload,
        timeout=args.timeout,
    )
    charge = _expect(status, charge, text, 200, "stripe test charge create")
    status, refund, text = _request(
        "POST",
        "https://api.stripe.com/v1/refunds",
        headers=_stripe_headers(secret, f"zroky-refund-{run_id}"),
        payload={"charge": charge["id"], "amount": str(args.amount)},
        timeout=args.timeout,
    )
    return _expect(status, refund, text, 200, "stripe test refund create")


def _publish_pack(args: argparse.Namespace, headers: dict[str, str]) -> dict[str, Any]:
    pack = {
        "schema_version": "zroky.workflow_assurance_pack.v1",
        "workflow_key": "stripe-refund-live-test-loop",
        "version": f"1.0.{int(time.time())}",
        "intent_schema": {"type": "object"},
        "object_types": [{"key": "refund", "schema": {"type": "object"}}],
        "effects": [{"key": "stripe_refund_succeeded", "object_type": "refund", "predicate": "refund.status == 'succeeded'"}],
        "source_bindings": [{"key": "stripe_refund_read", "connector_capability": "stripe.refund.read", "object_type": "refund", "freshness_seconds": 300}],
        "recovery_playbooks": [],
    }
    status, body, text = _request("POST", _url(args.api_base_url, "/v1/assurance-packs"), headers=headers, payload={"environment": "production", "pack": pack}, timeout=args.timeout)
    return _expect(status, body, text, 201, "zroky assurance pack publish")


def _authorize_intent(args: argparse.Namespace, headers: dict[str, str], *, refund_id: str, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    status, intent, text = _request(
        "POST",
        _url(args.api_base_url, "/v1/intents"),
        headers={**headers, "Idempotency-Key": f"stripe-live-intent-{run_id}"},
        payload={"environment": "production", "agent_ref": "stripe-live-test-agent", "intent": {"workflow_key": "stripe-refund-live-test-loop", "action": "stripe.refund.create", "refund_id": refund_id, "amount": args.amount, "currency": args.currency}},
        timeout=args.timeout,
    )
    intent = _expect(status, intent, text, 201, "zroky intent create")
    status, decision, text = _request("POST", _url(args.api_base_url, "/v1/policy/check"), headers=headers, payload={"intent_id": intent["id"], "decision": "approval_required", "reason": "live Stripe test loop"}, timeout=args.timeout)
    decision = _expect(status, decision, text, 201, "zroky policy approval_required")
    approval = decision["approval_requirements"][0]
    status, approved, text = _request("POST", _url(args.api_base_url, f"/v1/approvals/{approval['id']}/approve"), headers=headers, payload={"binding_digest": approval["binding_digest"]}, timeout=args.timeout)
    _expect(status, approved, text, 200, "zroky approval approve")
    return intent, decision


def _verified_case(args: argparse.Namespace, headers: dict[str, str], pack: dict[str, Any], stripe_refund: dict[str, Any], run_id: str) -> None:
    refund_id = str(stripe_refund["id"])
    intent, decision = _authorize_intent(args, headers, refund_id=refund_id, run_id=f"{run_id}-ok")
    status, run, text = _request("POST", _url(args.api_base_url, "/v1/runs"), headers={**headers, "Idempotency-Key": f"stripe-live-run-{run_id}-ok"}, payload={"environment": "production", "external_run_id": f"stripe-live-{run_id}-ok", "intent_id": intent["id"], "workflow_key": "stripe-refund-live-test-loop", "agent_ref": "stripe-live-test-agent", "status": "succeeded", "run": {"claimed": {"refund_id": refund_id, "status": stripe_refund.get("status")}}}, timeout=args.timeout)
    run = _expect(status, run, text, 201, "zroky run declare verified case")
    status, observation, text = _request("POST", _url(args.api_base_url, "/v1/observations"), headers=headers, payload={"environment": "production", "run_id": run["id"], "intent_id": intent["id"], "source_kind": "stripe_refund", "observed_object_ref": f"stripe:refund:{refund_id}", "observed_state": {"refund_id": refund_id, "status": stripe_refund.get("status"), "amount": stripe_refund.get("amount"), "currency": stripe_refund.get("currency")}, "provenance": {"source_binding": "stripe_refund_read", "stripe_object": stripe_refund.get("object"), "mode": "test"}, "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, timeout=args.timeout)
    observation = _expect(status, observation, text, 201, "zroky stripe observation")
    status, graph, text = _request("POST", _url(args.api_base_url, f"/v1/runs/{run['id']}/outcome-graph"), headers=headers, payload={"assurance_pack_id": pack["id"]}, timeout=args.timeout)
    graph = _expect(status, graph, text, 201, "zroky outcome graph verified case")
    if graph.get("verification_status") != "verified":
        raise Failure(f"verified case failed: {json.dumps(graph)[:1000]}")
    status, evidence, text = _request("POST", _url(args.api_base_url, "/v1/evidence/bundles"), headers=headers, payload={"environment": "production", "subject_type": "run", "subject_id": run["id"], "bundle": {"schema_version": "zroky.final_evidence_bundle.v1", "intent": intent, "policy": decision, "observations": [observation], "snapshot": graph, "incident": {"created": False}, "recovery": {"required": False}}}, timeout=args.timeout)
    evidence = _expect(status, evidence, text, 201, "zroky evidence bundle")
    status, verified, text = _request("GET", _url(args.api_base_url, f"/v1/evidence/bundles/{evidence['id']}/verify"), headers=headers, timeout=args.timeout)
    verified = _expect(status, verified, text, 200, "zroky evidence verify")
    if verified.get("verification_status") != "pass":
        raise Failure(f"evidence verification failed: {json.dumps(verified)}")


def _false_success_case(args: argparse.Namespace, headers: dict[str, str], pack: dict[str, Any], run_id: str) -> None:
    intent, _decision = _authorize_intent(args, headers, refund_id=f"re_missing_{run_id}", run_id=f"{run_id}-bad")
    status, run, text = _request("POST", _url(args.api_base_url, "/v1/runs"), headers={**headers, "Idempotency-Key": f"stripe-live-run-{run_id}-bad"}, payload={"environment": "production", "external_run_id": f"stripe-live-{run_id}-bad", "intent_id": intent["id"], "workflow_key": "stripe-refund-live-test-loop", "agent_ref": "stripe-live-test-agent", "status": "succeeded", "run": {"claimed": {"refund_id": f"re_missing_{run_id}", "status": "succeeded"}}}, timeout=args.timeout)
    run = _expect(status, run, text, 201, "zroky run declare false-success case")
    status, graph, text = _request("POST", _url(args.api_base_url, f"/v1/runs/{run['id']}/outcome-graph"), headers=headers, payload={"assurance_pack_id": pack["id"]}, timeout=args.timeout)
    graph = _expect(status, graph, text, 201, "zroky outcome graph false-success case")
    if graph.get("verification_status") != "failed" or graph.get("graph", {}).get("classification") != "missing":
        raise Failure(f"false-success case was not caught: {json.dumps(graph)[:1000]}")
    status, incidents, text = _request("GET", _url(args.api_base_url, "/v1/incidents"), headers=headers, timeout=args.timeout)
    if status != 200 or not any(isinstance(item, dict) and item.get("outcome_graph_id") == graph["id"] and item.get("status") == "open" for item in (incidents or [])):
        raise Failure(f"false-success incident missing: {text[:700]}")
    print("[PASS] zroky false success incident")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run final Zroky Stripe test-mode loop against a live backend.")
    parser.add_argument("--api-base-url", default=os.environ.get("ZROKY_API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--project-id", default=os.environ.get("ZROKY_PROJECT_ID", "stripe-live-test"))
    parser.add_argument("--api-key", default=os.environ.get("ZROKY_API_KEY", ""))
    parser.add_argument("--bearer-env", default="ZROKY_BEARER_TOKEN")
    parser.add_argument("--stripe-secret-env", default="STRIPE_TEST_SECRET_KEY")
    parser.add_argument("--stripe-refund-id", default="")
    parser.add_argument("--create-test-refund", action="store_true")
    parser.add_argument("--amount", type=int, default=1200)
    parser.add_argument("--currency", default="usd")
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args(argv)

    secret = os.environ.get(args.stripe_secret_env, "").strip()
    if not secret.startswith("sk_test_"):
        raise Failure(f"{args.stripe_secret_env} must be set to a Stripe test secret key starting with sk_test_.")

    run_id = uuid4().hex[:10]
    headers = _backend_headers(args)
    stripe_refund = _stripe_refund(args, secret, run_id)
    pack = _publish_pack(args, headers)
    _verified_case(args, headers, pack, stripe_refund, run_id)
    _false_success_case(args, headers, pack, run_id)
    print(json.dumps({"status": "pass", "stripe_refund_id": stripe_refund["id"], "project_id": args.project_id}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Failure as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
