from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "zroky-backend"
FIXTURE_PATH = (
    ROOT / "demos" / "design-partner-install-kit" / "refund_agent_fixture.json"
)
HANDOFF_GUIDE_PATH = (
    ROOT / "demos" / "design-partner-install-kit" / "README.md"
)

PROJECT_HEADER = "X-Project-Id"
API_KEY_HEADER = "x-api-key"
AUTH_SECRET = "design-partner-install-kit-secret"
LOCAL_ENV_KEYS = (
    "TESTING",
    "DATABASE_URL",
    "DATABASE_READ_REPLICA_URL",
    "AUTH_JWT_SECRET",
    "ALLOW_PROJECT_HEADER_CONTEXT",
    "LOG_LEVEL",
    "ENABLE_READY_REDIS_CHECK",
    "INGEST_ENFORCE_RATE_LIMIT",
    "BILLING_ENFORCE_QUOTA",
    "OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS",
)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"Expected object JSON in {path}.")
    return loaded


def _assert_response(response: Any, expected_status: int, label: str) -> dict[str, Any]:
    if response.status_code != expected_status:
        body = getattr(response, "text", "")[:1200]
        raise RuntimeError(f"{label} failed: HTTP {response.status_code}: {body}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} returned non-object JSON.")
    return payload


def _redact(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in secrets:
            if secret:
                redacted = redacted.replace(secret, "[redacted]")
        return redacted
    return value


def _contains_secret(value: Any, secrets: list[str]) -> bool:
    rendered = json.dumps(value, sort_keys=True, default=str)
    return any(secret and secret in rendered for secret in secrets)


def _headers(args: argparse.Namespace) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers[API_KEY_HEADER] = args.api_key
    if args.bearer_token:
        headers["Authorization"] = f"Bearer {args.bearer_token}"
    if args.project_id:
        headers[PROJECT_HEADER] = args.project_id
    return headers


def _runtime_policy_payload(
    fixture: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    agent = fixture["agent"]
    trace = fixture["trace"]
    risky_action = fixture["risky_action"]
    claim = fixture["claimed_outcome"]
    amount = args.amount_usd if args.amount_usd is not None else claim["amount_usd"]
    refund_id = args.refund_id or claim["refund_id"]
    return {
        "trace_id": args.trace_id or trace["trace_id"],
        "call_id": args.call_id or trace["call_id"],
        "agent_name": args.agent_name or agent["name"],
        "workflow_name": agent["workflow"],
        "environment": args.environment,
        "action_type": risky_action["action_type"],
        "tool_name": risky_action["tool_name"],
        "tool_args": {
            "refund_id": refund_id,
            "order_id": claim.get("order_id"),
            "amount_usd": amount,
            "currency": args.currency or claim.get("currency", "USD"),
        },
        "external_action": True,
        "business_impact_summary": risky_action["business_impact_summary"],
        "impact_usd": amount,
        "metadata": {
            "install_kit": "design_partner_refund_v1",
            "agent_type": agent["type"],
        },
    }


def _reconciliation_payload(
    fixture: dict[str, Any],
    args: argparse.Namespace,
    *,
    runtime_policy_decision_id: str,
) -> dict[str, Any]:
    trace = fixture["trace"]
    claim = dict(fixture["claimed_outcome"])
    ledger = fixture["ledger"]
    refund_id = args.refund_id or claim["refund_id"]
    amount = args.amount_usd if args.amount_usd is not None else claim["amount_usd"]
    claim.update(
        {
            "refund_id": refund_id,
            "amount_usd": amount,
            "currency": args.currency or claim.get("currency", "USD"),
            "status": args.status or claim.get("status", "posted"),
        }
    )
    return {
        "call_id": args.call_id or trace["call_id"],
        "trace_id": args.trace_id or trace["trace_id"],
        "runtime_policy_decision_id": runtime_policy_decision_id,
        "action_type": "refund",
        "refund_id": refund_id,
        "claimed": claim,
        "match_fields": ["refund_id", "amount_usd", "currency", "status"],
        "amount_usd": amount,
        "currency": args.currency or claim.get("currency", "USD"),
        "metadata": {
            "install_kit": "design_partner_refund_v1",
            "partner_run_id": args.partner_run_id,
        },
        "connector": {
            "base_url": args.ledger_base_url or ledger["base_url"],
            "path_template": args.ledger_path_template or ledger["path_template"],
            "record_path": args.ledger_record_path or ledger["record_path"],
            "bearer_token": args.ledger_bearer_token or ledger.get("bearer_token"),
        },
    }


def _summarise(
    fixture: dict[str, Any],
    args: argparse.Namespace,
    *,
    mode: str,
    runtime_decision: dict[str, Any],
    reconciliation: dict[str, Any],
    evidence_pack: dict[str, Any],
    secrets: list[str],
) -> dict[str, Any]:
    metadata = reconciliation.get("metadata") or {}
    connector_metadata = metadata.get("connector") or {}
    evidence_outcomes = evidence_pack.get("outcome_reconciliation") or []
    evidence_call = evidence_pack.get("call") or {}
    call_id = (
        runtime_decision.get("call_id")
        or evidence_call.get("id")
        or args.call_id
        or fixture["trace"]["call_id"]
    )
    summary = {
        "mode": mode,
        "project_id": args.project_id or fixture["project_id"],
        "scenario": "refund_outcome_proof_v1",
        "agent_name": runtime_decision.get("agent_name"),
        "call_id": call_id,
        "trace_id": runtime_decision.get("trace_id"),
        "runtime_policy": {
            "decision_id": runtime_decision["id"],
            "decision": runtime_decision["decision"],
            "status": runtime_decision["status"],
            "allowed": runtime_decision["allowed"],
            "requires_approval": runtime_decision["requires_approval"],
            "reason_count": len(runtime_decision.get("reasons") or []),
        },
        "outcome_reconciliation": {
            "id": reconciliation["id"],
            "verdict": reconciliation["verdict"],
            "reason": reconciliation.get("reason"),
            "connector_type": reconciliation["connector_type"],
            "system_ref": reconciliation.get("system_ref"),
            "match_fields": metadata.get("match_fields"),
            "connector_http_status": connector_metadata.get("http_status"),
            "connector_request_url": connector_metadata.get("request_url"),
        },
        "evidence_pack": {
            "decision_id": evidence_pack["decision_id"],
            "verification_status": evidence_pack["verification_status"],
            "evidence_hash": evidence_pack["evidence_hash"],
            "hash_algorithm": evidence_pack["hash_algorithm"],
            "outcome_count": len(evidence_outcomes),
            "audit_event_count": len(evidence_pack.get("audit_log") or []),
        },
        "proof": {
            "captured_call_linked": evidence_call.get("id") == call_id,
            "unsafe_action_stopped": runtime_decision["allowed"] is False,
            "matched_outcome_shown": reconciliation["verdict"] == "matched",
            "evidence_hash_visible": bool(evidence_pack.get("evidence_hash")),
            "evidence_pack_passed": evidence_pack["verification_status"] == "pass",
            "secrets_redacted": not _contains_secret(
                {"reconciliation": reconciliation, "evidence_pack": evidence_pack},
                secrets,
            ),
        },
        "handoff": {
            "guide": HANDOFF_GUIDE_PATH.relative_to(ROOT).as_posix(),
            "package": "design_partner_refund_v1",
            "pass_criteria": [
                "captured_call_linked",
                "unsafe_action_stopped",
                "matched_outcome_shown",
                "evidence_hash_visible",
                "evidence_pack_passed",
                "secrets_redacted",
            ],
            "customer_artifacts": [
                {
                    "flag": "--write-summary",
                    "default_path": "artifacts/design-partner-summary.json",
                    "contains": "redacted customer-facing proof summary",
                },
                {
                    "flag": "--write-evidence",
                    "default_path": "artifacts/design-partner-evidence.json",
                    "contains": "redacted audit evidence pack",
                },
            ],
            "failure_policy": (
                "Any false proof value, mismatched outcome, not_verified evidence, "
                "or missing evidence hash blocks partner handoff."
            ),
        },
        "next_live_command": (
            "python scripts/run_design_partner_install_kit.py --api-base-url https://api.zroky.ai "
            "--api-key <zroky_api_key> --ledger-base-url https://ledger.example.com/api "
            "--ledger-bearer-token <ledger_token> --refund-id <refund_id> --json "
            "--write-summary artifacts/design-partner-live-summary.json "
            "--write-evidence artifacts/design-partner-live-evidence.json"
        ),
    }
    return _redact(summary, secrets)


def _validate_summary(summary: dict[str, Any]) -> None:
    proof = summary.get("proof") or {}
    failures = [key for key, value in proof.items() if value is not True]
    if failures:
        raise RuntimeError(
            "Design-partner install kit proof failed: " + ", ".join(sorted(failures))
        )


def _write_json_artifact(
    path_text: str | None, payload: dict[str, Any], secrets: list[str]
) -> None:
    if not path_text:
        return
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            _redact(payload, secrets), indent=2, sort_keys=True, default=str
        ),
        encoding="utf-8",
    )


def _write_evidence(
    path_text: str | None, evidence_pack: dict[str, Any], secrets: list[str]
) -> None:
    _write_json_artifact(path_text, evidence_pack, secrets)


def _write_summary(
    path_text: str | None, summary: dict[str, Any], secrets: list[str]
) -> None:
    _write_json_artifact(path_text, summary, secrets)


def _restore_env(snapshot: dict[str, str | None]) -> None:
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _configure_local_env(db_path: Path) -> dict[str, str | None]:
    snapshot = {key: os.environ.get(key) for key in LOCAL_ENV_KEYS}
    os.environ.update(
        {
            "TESTING": "true",
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "DATABASE_READ_REPLICA_URL": "",
            "AUTH_JWT_SECRET": AUTH_SECRET,
            "ALLOW_PROJECT_HEADER_CONTEXT": "true",
            "LOG_LEVEL": "CRITICAL",
            "ENABLE_READY_REDIS_CHECK": "false",
            "INGEST_ENFORCE_RATE_LIMIT": "false",
            "BILLING_ENFORCE_QUOTA": "false",
            "OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS": "false",
        }
    )
    return snapshot


def _seed_local_call(
    session_local: Any, fixture: dict[str, Any], args: argparse.Namespace
) -> None:
    from app.db.models import Call

    agent = fixture["agent"]
    trace = fixture["trace"]
    claim = fixture["claimed_outcome"]
    call_id = args.call_id or trace["call_id"]
    trace_id = args.trace_id or trace["trace_id"]
    now = datetime.now(timezone.utc)
    with session_local() as session:
        session.add(
            Call(
                id=call_id,
                project_id=args.project_id or fixture["project_id"],
                event_id=f"evt-{call_id}",
                created_at=now,
                agent_name=args.agent_name or agent["name"],
                user_id="customer-design-partner-demo",
                call_type="tool_action",
                provider="fixture",
                model="design-partner-install-kit",
                status="completed",
                latency_ms=260,
                input_tokens=80,
                output_tokens=28,
                total_tokens=108,
                cost_total=0.0025,
                cost_confidence="high",
                output_fingerprint="design-partner-refund-proof",
                is_production=True,
                tool_lifecycle_summary_json=json.dumps(
                    {
                        "tool_calls": [
                            {
                                "name": "refund_payment",
                                "args": {
                                    "refund_id": args.refund_id or claim["refund_id"],
                                    "amount_usd": args.amount_usd
                                    if args.amount_usd is not None
                                    else claim["amount_usd"],
                                },
                            }
                        ],
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                payload_json=json.dumps(
                    {
                        "trace_id": trace_id,
                        "input": "Issue this refund.",
                        "claimed_outcome": claim,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                metadata_json=json.dumps(
                    {"source": "design_partner_install_kit"},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        )
        session.commit()


def _install_local_ledger_stub(fixture: dict[str, Any]) -> Any:
    from app.services.outcome_reconciliation import SourceRecord
    from app.services.system_of_record_connectors import LedgerRefundApiConnector

    original_fetch = LedgerRefundApiConnector.fetch
    expected_refund_id = fixture["claimed_outcome"]["refund_id"]
    ledger = fixture["ledger"]
    record = dict(ledger["response"]["data"])
    record.setdefault("refund_id", record.get("id", expected_refund_id))
    record.setdefault("amount_usd", record.get("amount"))
    if isinstance(record.get("currency"), str):
        record["currency"] = record["currency"].upper()

    def fake_fetch(self: Any) -> SourceRecord:
        request_url = (
            f"{str(self.base_url).rstrip('/')}/"
            f"{str(self.path_template).lstrip('/').replace('{refund_id}', self.refund_id)}"
        )
        if self.refund_id != expected_refund_id:
            return SourceRecord(
                record=None,
                record_found=False,
                metadata={
                    "connector_type": "ledger_refund_api",
                    "request_url": request_url,
                    "http_status": 404,
                    "refund_id": self.refund_id,
                    "adapter": "design_partner_local_stub",
                },
            )
        return SourceRecord(
            record=record,
            record_found=True,
            metadata={
                "connector_type": "ledger_refund_api",
                "request_url": request_url,
                "http_status": 200,
                "record_path": ledger["record_path"],
                "refund_id": self.refund_id,
                "adapter": "design_partner_local_stub",
            },
        )

    LedgerRefundApiConnector.fetch = fake_fetch

    def restore() -> None:
        LedgerRefundApiConnector.fetch = original_fetch

    return restore


def _run_local_demo(
    fixture: dict[str, Any], args: argparse.Namespace
) -> tuple[dict[str, Any], dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="zroky-design-partner-kit-") as temp_dir:
        db_path = Path(temp_dir) / "install_kit.db"
        env_snapshot = _configure_local_env(db_path)
        previous_disable_level = logging.root.manager.disable
        engine: Any = None
        base_metadata: Any = None
        app_ref: Any = None
        restore_ledger: Any = None
        invalidate_all_fn: Any = None
        settings_cache_clear: Any = None
        try:
            logging.disable(logging.CRITICAL)
            sys.path.insert(0, str(BACKEND_DIR))

            from fastapi.testclient import TestClient
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            from app.api.dependencies.tenant import (
                TenantContext,
                require_tenant_context,
            )
            from app.core.config import get_settings
            from app.db.base import Base
            from app.db.session import get_db_session, get_db_session_read
            from app.main import app
            from app.services.entitlements_resolver import invalidate_all

            app_ref = app
            base_metadata = Base.metadata
            invalidate_all_fn = invalidate_all
            settings_cache_clear = get_settings.cache_clear
            settings_cache_clear()
            invalidate_all_fn()

            engine = create_engine(
                f"sqlite:///{db_path.as_posix()}",
                connect_args={"check_same_thread": False},
                future=True,
            )
            session_local = sessionmaker(
                bind=engine,
                autoflush=False,
                autocommit=False,
                future=True,
            )
            base_metadata.create_all(bind=engine)
            _seed_local_call(session_local, fixture, args)

            def override_get_db_session() -> Any:
                session = session_local()
                try:
                    yield session
                finally:
                    session.close()

            def override_tenant_context() -> TenantContext:
                return TenantContext(
                    tenant_id=args.project_id or fixture["project_id"],
                    role="admin",
                    subject="design-partner-install-kit",
                )

            app_ref.dependency_overrides[get_db_session] = override_get_db_session
            app_ref.dependency_overrides[get_db_session_read] = override_get_db_session
            app_ref.dependency_overrides[require_tenant_context] = (
                override_tenant_context
            )
            restore_ledger = _install_local_ledger_stub(fixture)

            try:
                with TestClient(app_ref) as client:
                    runtime_decision = _assert_response(
                        client.post(
                            "/v1/runtime-policy/check",
                            json=_runtime_policy_payload(fixture, args),
                        ),
                        200,
                        "runtime policy check",
                    )
                    reconciliation = _assert_response(
                        client.post(
                            "/v1/outcomes/reconciliation/ledger-refund",
                            json=_reconciliation_payload(
                                fixture,
                                args,
                                runtime_policy_decision_id=runtime_decision["id"],
                            ),
                        ),
                        201,
                        "ledger refund reconciliation",
                    )
                    evidence_pack = _assert_response(
                        client.get(
                            f"/v1/runtime-policy/decisions/{runtime_decision['id']}/evidence"
                        ),
                        200,
                        "runtime policy evidence pack",
                    )
            finally:
                if restore_ledger is not None:
                    restore_ledger()
                if app_ref is not None:
                    app_ref.dependency_overrides.clear()
                if engine is not None and base_metadata is not None:
                    base_metadata.drop_all(bind=engine)
                    engine.dispose()
                if invalidate_all_fn is not None:
                    invalidate_all_fn()
                if settings_cache_clear is not None:
                    settings_cache_clear()
        finally:
            logging.disable(previous_disable_level)
            _restore_env(env_snapshot)
            if settings_cache_clear is not None:
                settings_cache_clear()

    secrets = [fixture["ledger"].get("bearer_token") or ""]
    summary = _summarise(
        fixture,
        args,
        mode="local_demo",
        runtime_decision=runtime_decision,
        reconciliation=reconciliation,
        evidence_pack=evidence_pack,
        secrets=secrets,
    )
    return summary, evidence_pack


def _run_live(
    fixture: dict[str, Any], args: argparse.Namespace
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not args.api_base_url:
        raise RuntimeError("--api-base-url is required for live mode.")
    if not args.api_key and not args.bearer_token:
        raise RuntimeError(
            "Provide --api-key or --bearer-token for live mode authentication."
        )
    if not args.ledger_base_url:
        raise RuntimeError("--ledger-base-url is required for live mode.")
    if not args.ledger_bearer_token:
        raise RuntimeError("--ledger-bearer-token is required for live mode.")

    import httpx

    headers = _headers(args)
    timeout = args.timeout_seconds
    with httpx.Client(
        base_url=args.api_base_url.rstrip("/"), timeout=timeout
    ) as client:
        runtime_decision = _assert_response(
            client.post(
                "/v1/runtime-policy/check",
                headers=headers,
                json=_runtime_policy_payload(fixture, args),
            ),
            200,
            "runtime policy check",
        )
        reconciliation = _assert_response(
            client.post(
                "/v1/outcomes/reconciliation/ledger-refund",
                headers=headers,
                json=_reconciliation_payload(
                    fixture,
                    args,
                    runtime_policy_decision_id=runtime_decision["id"],
                ),
            ),
            201,
            "ledger refund reconciliation",
        )
        evidence_pack = _assert_response(
            client.get(
                f"/v1/runtime-policy/decisions/{runtime_decision['id']}/evidence",
                headers=headers,
            ),
            200,
            "runtime policy evidence pack",
        )

    secrets = [
        args.api_key or "",
        args.bearer_token or "",
        args.ledger_bearer_token or "",
    ]
    summary = _summarise(
        fixture,
        args,
        mode="live",
        runtime_decision=runtime_decision,
        reconciliation=reconciliation,
        evidence_pack=evidence_pack,
        secrets=secrets,
    )
    return summary, evidence_pack


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a design-partner install proof: runtime policy stop, ledger refund "
            "outcome verification, and downloadable evidence hash."
        )
    )
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    parser.add_argument(
        "--fixture", default=str(FIXTURE_PATH), help="Scenario fixture JSON."
    )
    parser.add_argument(
        "--write-evidence", help="Write the full evidence pack JSON to this path."
    )
    parser.add_argument(
        "--write-summary",
        help="Write the redacted customer-facing proof summary JSON to this path.",
    )
    parser.add_argument(
        "--api-base-url", help="Zroky API base URL. Omit for local demo mode."
    )
    parser.add_argument("--api-key", help="Zroky API key for x-api-key authentication.")
    parser.add_argument(
        "--bearer-token", help="Bearer token for Zroky API authentication."
    )
    parser.add_argument(
        "--project-id", help="Project/tenant id. Sent as X-Project-Id in live mode."
    )
    parser.add_argument(
        "--ledger-base-url", help="HTTPS base URL for the partner ledger adapter."
    )
    parser.add_argument(
        "--ledger-bearer-token", help="Bearer token for the partner ledger adapter."
    )
    parser.add_argument(
        "--ledger-path-template", help="Ledger path template, default from fixture."
    )
    parser.add_argument(
        "--ledger-record-path",
        help="Dot path to the refund object, default from fixture.",
    )
    parser.add_argument("--refund-id", help="Refund id to verify.")
    parser.add_argument("--call-id", help="Zroky call id to link evidence.")
    parser.add_argument("--trace-id", help="Zroky trace id to link evidence.")
    parser.add_argument("--agent-name", help="Agent name shown in policy evidence.")
    parser.add_argument("--amount-usd", type=float, help="Claimed refund amount.")
    parser.add_argument("--currency", default=None, help="Claimed currency, e.g. USD.")
    parser.add_argument("--status", default=None, help="Claimed refund status.")
    parser.add_argument(
        "--environment", default="production", help="Runtime environment label."
    )
    parser.add_argument(
        "--partner-run-id",
        default="design-partner-install-kit",
        help="Run id stored in reconciliation metadata.",
    )
    parser.add_argument(
        "--timeout-seconds", type=float, default=10.0, help="Live HTTP timeout."
    )
    return parser.parse_args(argv)


def _print_summary(summary: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, sort_keys=True, separators=(",", ":"), default=str))
        return
    print(f"mode={summary['mode']}")
    print(f"project_id={summary['project_id']}")
    print(f"runtime_policy_decision_id={summary['runtime_policy']['decision_id']}")
    print(f"runtime_policy_status={summary['runtime_policy']['status']}")
    print(f"runtime_policy_allowed={str(summary['runtime_policy']['allowed']).lower()}")
    print(f"outcome_verdict={summary['outcome_reconciliation']['verdict']}")
    print(f"evidence_hash={summary['evidence_pack']['evidence_hash']}")
    print(
        f"evidence_verification_status={summary['evidence_pack']['verification_status']}"
    )
    print(f"secrets_redacted={str(summary['proof']['secrets_redacted']).lower()}")
    print("[design-partner-install-kit] passed")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    fixture = _load_json(Path(args.fixture))
    if args.api_base_url:
        summary, evidence_pack = _run_live(fixture, args)
    else:
        summary, evidence_pack = _run_local_demo(fixture, args)
    secrets = [
        fixture.get("ledger", {}).get("bearer_token") or "",
        args.api_key or "",
        args.bearer_token or "",
        args.ledger_bearer_token or "",
    ]
    _validate_summary(summary)
    _write_summary(args.write_summary, summary, secrets)
    _write_evidence(args.write_evidence, evidence_pack, secrets)
    _print_summary(summary, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
