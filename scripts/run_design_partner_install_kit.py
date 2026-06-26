from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import warnings
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "zroky-backend"
REFUND_FIXTURE_PATH = (
    ROOT / "demos" / "design-partner-install-kit" / "refund_agent_fixture.json"
)
CUSTOMER_RECORD_FIXTURE_PATH = (
    ROOT
    / "demos"
    / "design-partner-install-kit"
    / "customer_record_agent_fixture.json"
)
HANDOFF_GUIDE_PATH = (
    ROOT / "demos" / "design-partner-install-kit" / "HANDOFF.txt"
)
LEDGER_CONNECTOR_TEMPLATE_PATH = (
    ROOT
    / "demos"
    / "design-partner-install-kit"
    / "ledger_refund_connector_config.example.json"
)
CUSTOMER_RECORD_CONNECTOR_TEMPLATE_PATH = (
    ROOT
    / "demos"
    / "design-partner-install-kit"
    / "customer_record_connector_config.example.json"
)
SCENARIO_FIXTURES = {
    "refund": REFUND_FIXTURE_PATH,
    "customer-record": CUSTOMER_RECORD_FIXTURE_PATH,
}

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
    "PROVIDER_KEY_VAULT_KEK",
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


def _owner_headers(args: argparse.Namespace) -> dict[str, str]:
    if not args.owner_admin_token:
        raise RuntimeError(
            "--owner-admin-token is required with --verify-owner-launch-readiness."
        )
    return {args.owner_token_header: args.owner_admin_token}


def _fixture_scenario(fixture: dict[str, Any]) -> str:
    scenario = str(fixture.get("scenario") or "").lower()
    if "customer_record" in scenario or "crm" in scenario or "crm" in fixture:
        return "customer-record"
    return "refund"


def _fixture_package(fixture: dict[str, Any]) -> str:
    package = str(fixture.get("package") or "").strip()
    if package:
        return package
    return (
        "design_partner_crm_v1"
        if _fixture_scenario(fixture) == "customer-record"
        else "design_partner_refund_v1"
    )


def _claimed_value(claimed: dict[str, Any], key: str, fallback: Any = None) -> Any:
    value = claimed.get(key)
    return fallback if value is None else value


def _customer_id(fixture: dict[str, Any], args: argparse.Namespace) -> str:
    claimed = fixture["claimed_outcome"]
    return str(
        args.customer_id
        or _claimed_value(claimed, "customer_id")
        or _claimed_value(claimed, "id")
        or ""
    )


def _connector_secrets(fixture: dict[str, Any], args: argparse.Namespace) -> list[str]:
    return [
        fixture.get("ledger", {}).get("bearer_token") or "",
        fixture.get("crm", {}).get("bearer_token") or "",
        args.api_key or "",
        args.bearer_token or "",
        args.owner_admin_token or "",
        args.ledger_bearer_token or "",
        args.crm_bearer_token or "",
    ]


def _runtime_policy_payload(
    fixture: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    agent = fixture["agent"]
    trace = fixture["trace"]
    risky_action = fixture["risky_action"]
    claim = fixture["claimed_outcome"]
    amount = (
        args.amount_usd
        if args.amount_usd is not None
        else _claimed_value(claim, "amount_usd", risky_action.get("impact_usd"))
    )
    tool_args = dict(risky_action.get("tool_args") or {})
    if _fixture_scenario(fixture) == "customer-record":
        customer_id = _customer_id(fixture, args)
        tool_args.update(
            {
                "customer_id": customer_id,
                "email": args.email or _claimed_value(claim, "email"),
                "account_id": args.account_id or _claimed_value(claim, "account_id"),
                "status": args.customer_status
                or args.status
                or _claimed_value(claim, "status"),
            }
        )
    else:
        refund_id = args.refund_id or claim["refund_id"]
        tool_args.update(
            {
                "refund_id": refund_id,
                "order_id": claim.get("order_id"),
                "amount_usd": amount,
                "currency": args.currency or claim.get("currency", "USD"),
            }
        )
    return {
        "trace_id": args.trace_id or trace["trace_id"],
        "call_id": args.call_id or trace["call_id"],
        "agent_name": args.agent_name or agent["name"],
        "workflow_name": agent["workflow"],
        "environment": args.environment,
        "action_type": risky_action["action_type"],
        "tool_name": risky_action["tool_name"],
        "tool_args": tool_args,
        "external_action": True,
        "business_impact_summary": risky_action["business_impact_summary"],
        "impact_usd": amount,
        "customer_id": tool_args.get("customer_id"),
        "account_id": tool_args.get("account_id"),
        "order_id": tool_args.get("order_id"),
        "metadata": {
            "install_kit": _fixture_package(fixture),
            "agent_type": agent["type"],
            "proof_mode": "live_customer" if args.api_base_url else "local_demo",
        },
    }


def _proof_mode(args: argparse.Namespace, runtime_policy_decision_id: str | None) -> str:
    if runtime_policy_decision_id is None:
        return "preflight"
    if args.api_base_url:
        return "live_customer"
    return "local_demo"


def _proof_metadata(
    fixture: dict[str, Any],
    args: argparse.Namespace,
    *,
    runtime_policy_decision_id: str | None,
) -> dict[str, Any]:
    proof_mode = _proof_mode(args, runtime_policy_decision_id)
    return {
        "install_kit": _fixture_package(fixture),
        "partner_run_id": args.partner_run_id,
        "proof_mode": proof_mode,
        "real_customer_proof_candidate": proof_mode == "live_customer",
    }


def _connector_endpoints(fixture: dict[str, Any]) -> dict[str, str]:
    slug = (
        "customer-record"
        if _fixture_scenario(fixture) == "customer-record"
        else "ledger-refund"
    )
    base_path = f"/v1/integrations/system-of-record/{slug}"
    return {
        "status_endpoint": f"{base_path}/status",
        "config_endpoint": f"{base_path}/config",
        "test_endpoint": f"{base_path}/test",
    }


def _saved_connector_endpoint(fixture: dict[str, Any]) -> str:
    slug = (
        "customer-record"
        if _fixture_scenario(fixture) == "customer-record"
        else "ledger-refund"
    )
    return f"/v1/outcomes/reconciliation/{slug}/saved"


def _connector_config_payload(
    fixture: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    if _fixture_scenario(fixture) == "customer-record":
        crm = fixture["crm"]
        return {
            "base_url": args.crm_base_url or crm["base_url"],
            "path_template": args.crm_path_template or crm["path_template"],
            "record_path": args.crm_record_path or crm["record_path"],
            "bearer_token": args.crm_bearer_token or crm.get("bearer_token"),
        }
    ledger = fixture["ledger"]
    return {
        "base_url": args.ledger_base_url or ledger["base_url"],
        "path_template": args.ledger_path_template or ledger["path_template"],
        "record_path": args.ledger_record_path or ledger["record_path"],
        "bearer_token": args.ledger_bearer_token or ledger.get("bearer_token"),
    }


def _connector_test_payload(
    fixture: dict[str, Any],
    args: argparse.Namespace,
    *,
    runtime_policy_decision_id: str | None,
) -> dict[str, Any]:
    if _fixture_scenario(fixture) == "customer-record":
        return _customer_record_connector_test_payload(
            fixture, args, runtime_policy_decision_id=runtime_policy_decision_id
        )
    return _ledger_connector_test_payload(
        fixture, args, runtime_policy_decision_id=runtime_policy_decision_id
    )


def _ledger_connector_test_payload(
    fixture: dict[str, Any],
    args: argparse.Namespace,
    *,
    runtime_policy_decision_id: str | None,
) -> dict[str, Any]:
    trace = fixture["trace"]
    claim = dict(fixture["claimed_outcome"])
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
            **_proof_metadata(
                fixture, args, runtime_policy_decision_id=runtime_policy_decision_id
            ),
        },
    }


def _customer_record_connector_test_payload(
    fixture: dict[str, Any],
    args: argparse.Namespace,
    *,
    runtime_policy_decision_id: str | None,
) -> dict[str, Any]:
    trace = fixture["trace"]
    claim = dict(fixture["claimed_outcome"])
    customer_id = _customer_id(fixture, args)
    claim.update(
        {
            "customer_id": customer_id,
            "email": args.email or claim.get("email"),
            "account_id": args.account_id or claim.get("account_id"),
            "status": args.customer_status or args.status or claim.get("status"),
        }
    )
    return {
        "call_id": args.call_id or trace["call_id"],
        "trace_id": args.trace_id or trace["trace_id"],
        "runtime_policy_decision_id": runtime_policy_decision_id,
        "action_type": "customer_record_update",
        "customer_id": customer_id,
        "claimed": claim,
        "match_fields": ["customer_id", "email", "account_id", "status"],
        "amount_usd": args.amount_usd,
        "currency": args.currency,
        "metadata": {
            **_proof_metadata(
                fixture, args, runtime_policy_decision_id=runtime_policy_decision_id
            ),
        },
    }


def _next_live_command(fixture: dict[str, Any]) -> str:
    if _fixture_scenario(fixture) == "customer-record":
        return (
            "python scripts/run_design_partner_install_kit.py --scenario customer-record "
            "--api-base-url https://api.zroky.com --api-key <zroky_api_key> "
            "--crm-base-url https://crm.example.com/api "
            "--crm-bearer-token <crm_token> --customer-id <customer_id> --json "
            "--write-summary artifacts/design-partner-crm-live-summary.json "
            "--write-evidence artifacts/design-partner-crm-live-evidence.json"
        )
    return (
        "python scripts/run_design_partner_install_kit.py --scenario refund "
        "--api-base-url https://api.zroky.com --api-key <zroky_api_key> "
        "--ledger-base-url https://ledger.example.com/api "
        "--ledger-bearer-token <ledger_token> --refund-id <refund_id> --json "
        "--write-summary artifacts/design-partner-refund-live-summary.json "
        "--write-evidence artifacts/design-partner-refund-live-evidence.json"
    )


def _next_saved_connector_live_command(fixture: dict[str, Any]) -> str:
    if _fixture_scenario(fixture) == "customer-record":
        return (
            "python scripts/run_design_partner_install_kit.py --scenario customer-record "
            "--use-saved-connector --api-base-url https://api.zroky.com "
            "--api-key <zroky_api_key> --customer-id <customer_id> --json "
            "--write-summary artifacts/design-partner-crm-saved-live-summary.json "
            "--write-evidence artifacts/design-partner-crm-saved-live-evidence.json"
        )
    return (
        "python scripts/run_design_partner_install_kit.py --scenario refund "
        "--use-saved-connector --api-base-url https://api.zroky.com "
        "--api-key <zroky_api_key> --refund-id <refund_id> --json "
        "--write-summary artifacts/design-partner-refund-saved-live-summary.json "
        "--write-evidence artifacts/design-partner-refund-saved-live-evidence.json"
    )


def _next_live_preflight_command(fixture: dict[str, Any]) -> str:
    if _fixture_scenario(fixture) == "customer-record":
        return (
            "python scripts/run_design_partner_install_kit.py --scenario customer-record "
            "--preflight-only --api-base-url https://api.zroky.com "
            "--api-key <zroky_api_key> --crm-base-url https://crm.example.com/api "
            "--crm-bearer-token <crm_token> --customer-id <customer_id> --json "
            "--write-summary artifacts/design-partner-crm-preflight-summary.json"
        )
    return (
        "python scripts/run_design_partner_install_kit.py --scenario refund "
        "--preflight-only --api-base-url https://api.zroky.com "
        "--api-key <zroky_api_key> --ledger-base-url https://ledger.example.com/api "
        "--ledger-bearer-token <ledger_token> --refund-id <refund_id> --json "
        "--write-summary artifacts/design-partner-refund-preflight-summary.json"
    )


def _next_saved_connector_preflight_command(fixture: dict[str, Any]) -> str:
    if _fixture_scenario(fixture) == "customer-record":
        return (
            "python scripts/run_design_partner_install_kit.py --scenario customer-record "
            "--preflight-only --use-saved-connector "
            "--api-base-url https://api.zroky.com --api-key <zroky_api_key> "
            "--customer-id <customer_id> --json "
            "--write-summary artifacts/design-partner-crm-preflight-summary.json"
        )
    return (
        "python scripts/run_design_partner_install_kit.py --scenario refund "
        "--preflight-only --use-saved-connector "
        "--api-base-url https://api.zroky.com --api-key <zroky_api_key> "
        "--refund-id <refund_id> --json "
        "--write-summary artifacts/design-partner-refund-preflight-summary.json"
    )


def _connector_template_path(fixture: dict[str, Any]) -> Path:
    if _fixture_scenario(fixture) == "customer-record":
        return CUSTOMER_RECORD_CONNECTOR_TEMPLATE_PATH
    return LEDGER_CONNECTOR_TEMPLATE_PATH


def _connector_template_relative_path(fixture: dict[str, Any]) -> str:
    return _connector_template_path(fixture).relative_to(ROOT).as_posix()


def _connector_metadata(reconciliation: dict[str, Any]) -> dict[str, Any]:
    metadata = reconciliation.get("metadata") or {}
    connector_metadata = metadata.get("connector") or {}
    return dict(connector_metadata) if isinstance(connector_metadata, Mapping) else {}


def _as_positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None


def _as_bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _derived_connector_readiness(
    *,
    status: dict[str, Any],
    connector_metadata: dict[str, Any],
) -> dict[str, Any]:
    api_readiness = status.get("readiness")
    if isinstance(api_readiness, Mapping):
        return dict(api_readiness)

    http_status = connector_metadata.get("http_status") or status.get(
        "last_http_status"
    )
    attempts = connector_metadata.get("attempts") or status.get("last_attempts")
    error_code = connector_metadata.get("error_code") or status.get("last_error_code")
    retryable = _as_bool_or_none(
        connector_metadata.get("retryable", status.get("last_retryable"))
    )
    parsed_http_status = _as_positive_int(http_status)
    checks = {
        "config_saved": status.get("connected") is True,
        "bearer_token_present": status.get("has_bearer_token") is True,
        "saved_test_matched": status.get("last_verdict") == "matched",
        "connector_attempted": _as_positive_int(attempts) is not None,
        "http_2xx": parsed_http_status is not None
        and 200 <= parsed_http_status <= 299,
        "no_connector_error_code": error_code in (None, ""),
        "not_retryable_failure": retryable in (None, False),
    }
    blockers = [key for key, passed in checks.items() if not passed]
    return {
        "status": "ready" if not blockers else "not_ready",
        "checks": checks,
        "blockers": blockers,
    }


def _outcome_reconciliation_summary(
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    metadata = reconciliation.get("metadata") or {}
    connector_metadata = _connector_metadata(reconciliation)
    return {
        "id": reconciliation["id"],
        "verdict": reconciliation["verdict"],
        "reason": reconciliation.get("reason"),
        "connector_type": reconciliation["connector_type"],
        "system_ref": reconciliation.get("system_ref"),
        "match_fields": metadata.get("match_fields"),
        "connector_http_status": connector_metadata.get("http_status"),
        "connector_request_url": connector_metadata.get("request_url"),
        "connector_attempts": connector_metadata.get("attempts"),
        "connector_retry_count": connector_metadata.get("retry_count"),
        "connector_max_attempts": connector_metadata.get("max_attempts"),
        "connector_timeout_seconds": connector_metadata.get("timeout_seconds"),
        "connector_error": connector_metadata.get("error"),
        "connector_error_code": connector_metadata.get("error_code"),
        "connector_retryable": connector_metadata.get("retryable"),
    }


def _connector_setup_summary(
    *,
    endpoints: dict[str, str],
    initial_status: dict[str, Any],
    saved_status: dict[str, Any],
    test_response: dict[str, Any],
    final_status: dict[str, Any],
    reconciliation: dict[str, Any],
    secrets: list[str],
) -> dict[str, Any]:
    connector_metadata = _connector_metadata(reconciliation)
    connector_status = test_response.get("connector") or final_status
    readiness = _derived_connector_readiness(
        status=connector_status,
        connector_metadata=connector_metadata,
    )
    setup = {
        **endpoints,
        "connected": connector_status.get("connected") is True,
        "connector_type": connector_status.get("connector_type"),
        "config_saved": saved_status.get("connected") is True,
        "has_bearer_token": saved_status.get("has_bearer_token") is True,
        "bearer_token_last4": saved_status.get("bearer_token_last4"),
        "initial_health_status": initial_status.get("health_status"),
        "health_status": final_status.get("health_status"),
        "last_verdict": final_status.get("last_verdict"),
        "last_http_status": final_status.get("last_http_status"),
        "last_attempts": final_status.get("last_attempts"),
        "last_error": final_status.get("last_error"),
        "last_error_code": final_status.get("last_error_code"),
        "last_retryable": final_status.get("last_retryable"),
        "last_checked_at": final_status.get("last_checked_at"),
        "last_tested_at": final_status.get("last_tested_at"),
        "test_ok": test_response.get("ok") is True,
        "test_check_id": reconciliation.get("id"),
        "test_source": (reconciliation.get("metadata") or {}).get("source"),
        "attempts": connector_metadata.get("attempts"),
        "retry_count": connector_metadata.get("retry_count"),
        "max_attempts": connector_metadata.get("max_attempts"),
        "timeout_seconds": connector_metadata.get("timeout_seconds"),
        "error": connector_metadata.get("error"),
        "error_code": connector_metadata.get("error_code"),
        "retryable": connector_metadata.get("retryable"),
        "adapter": connector_metadata.get("adapter"),
        "readiness": readiness,
        "readiness_status": readiness.get("status"),
        "readiness_checks": readiness.get("checks") or {},
        "readiness_blockers": readiness.get("blockers") or [],
        "readiness_contract": readiness.get("contract") or {},
    }
    setup["secrets_redacted"] = not _contains_secret(
        {
            "initial_status": initial_status,
            "saved_status": saved_status,
            "test_response": test_response,
            "final_status": final_status,
            "setup": setup,
        },
        secrets,
    )
    return _redact(setup, secrets)


def _saved_connector_setup_summary(
    *,
    endpoint: str,
    reconciliation: dict[str, Any],
    secrets: list[str],
) -> dict[str, Any]:
    connector_metadata = _connector_metadata(reconciliation)
    connector_type = reconciliation.get("connector_type")
    system_of_record = (
        "customer_record" if connector_type == "customer_record_api" else "ledger_refund"
    )
    verdict = reconciliation.get("verdict")
    http_status = connector_metadata.get("http_status")
    attempts = connector_metadata.get("attempts")
    retryable = _as_bool_or_none(connector_metadata.get("retryable"))
    error_code = connector_metadata.get("error_code")
    parsed_http_status = _as_positive_int(http_status)
    ready = (
        verdict == "matched"
        and _as_positive_int(attempts) is not None
        and parsed_http_status is not None
        and 200 <= parsed_http_status <= 299
        and error_code in (None, "")
        and retryable in (None, False)
    )
    readiness_checks = {
        "config_saved": True,
        "saved_runtime_reconciliation_matched": verdict == "matched",
        "connector_attempted": _as_positive_int(attempts) is not None,
        "http_2xx": parsed_http_status is not None
        and 200 <= parsed_http_status <= 299,
        "no_connector_error_code": error_code in (None, ""),
        "not_retryable_failure": retryable in (None, False),
    }
    readiness_blockers = [
        key for key, passed in readiness_checks.items() if not passed
    ]
    setup = {
        "status_endpoint": None,
        "config_endpoint": None,
        "test_endpoint": endpoint,
        "connected": True,
        "connector_type": connector_type,
        "config_saved": True,
        "has_bearer_token": None,
        "bearer_token_last4": None,
        "initial_health_status": None,
        "health_status": "healthy" if ready else "not_verified",
        "last_verdict": verdict,
        "last_http_status": http_status,
        "last_attempts": attempts,
        "last_error": connector_metadata.get("error"),
        "last_error_code": error_code,
        "last_retryable": retryable,
        "last_checked_at": reconciliation.get("checked_at"),
        "last_tested_at": None,
        "test_ok": ready,
        "test_check_id": reconciliation.get("id"),
        "test_source": (reconciliation.get("metadata") or {}).get("source"),
        "attempts": attempts,
        "retry_count": connector_metadata.get("retry_count"),
        "max_attempts": connector_metadata.get("max_attempts"),
        "timeout_seconds": connector_metadata.get("timeout_seconds"),
        "error": connector_metadata.get("error"),
        "error_code": error_code,
        "retryable": retryable,
        "adapter": connector_metadata.get("adapter"),
        "readiness": {
            "status": "ready" if ready else "not_ready",
            "checks": readiness_checks,
            "blockers": readiness_blockers,
        },
        "readiness_status": "ready" if ready else "not_ready",
        "readiness_checks": readiness_checks,
        "readiness_blockers": readiness_blockers,
        "readiness_contract": {
            "schema_version": "system_of_record_connector.v1",
            "connector_type": connector_type,
            "system_of_record": system_of_record,
            "test_endpoint": endpoint,
            "pass_rule": (
                "Saved connector runtime reconciliation must read the system "
                "of record and return a matched outcome without resending the "
                "connector secret."
            ),
        },
    }
    setup["secrets_redacted"] = not _contains_secret(
        {"reconciliation": reconciliation, "setup": setup},
        secrets,
    )
    return _redact(setup, secrets)


def _run_connector_setup(
    client: Any,
    fixture: dict[str, Any],
    args: argparse.Namespace,
    *,
    runtime_policy_decision_id: str | None,
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request_headers = headers or {}
    if args.use_saved_connector:
        endpoint = _saved_connector_endpoint(fixture)
        reconciliation = _assert_response(
            client.post(
                endpoint,
                headers=request_headers,
                json=_connector_test_payload(
                    fixture,
                    args,
                    runtime_policy_decision_id=runtime_policy_decision_id,
                ),
            ),
            201,
            "saved connector reconciliation",
        )
        setup = _saved_connector_setup_summary(
            endpoint=endpoint,
            reconciliation=reconciliation,
            secrets=_connector_secrets(fixture, args),
        )
        return reconciliation, setup

    endpoints = _connector_endpoints(fixture)
    initial_status = _assert_response(
        client.get(endpoints["status_endpoint"], headers=request_headers),
        200,
        "connector status",
    )
    saved_status = _assert_response(
        client.put(
            endpoints["config_endpoint"],
            headers=request_headers,
            json=_connector_config_payload(fixture, args),
        ),
        200,
        "connector config",
    )
    test_response = _assert_response(
        client.post(
            endpoints["test_endpoint"],
            headers=request_headers,
            json=_connector_test_payload(
                fixture,
                args,
                runtime_policy_decision_id=runtime_policy_decision_id,
            ),
        ),
        201,
        "connector test",
    )
    final_status = _assert_response(
        client.get(endpoints["status_endpoint"], headers=request_headers),
        200,
        "connector status after test",
    )
    reconciliation = test_response["check"]
    setup = _connector_setup_summary(
        endpoints=endpoints,
        initial_status=initial_status,
        saved_status=saved_status,
        test_response=test_response,
        final_status=final_status,
        reconciliation=reconciliation,
        secrets=_connector_secrets(fixture, args),
    )
    return reconciliation, setup


def _artifact_prefix(fixture: dict[str, Any]) -> str:
    if _fixture_scenario(fixture) == "customer-record":
        return "design-partner-crm"
    return "design-partner-refund"


def _gate_evidence_value(gate: dict[str, Any], label: str) -> Any:
    for item in gate.get("evidence") or []:
        if item.get("label") == label:
            return item.get("value")
    return None


def _owner_launch_readiness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    gates = {
        str(gate.get("code")): gate
        for gate in payload.get("gates") or []
        if isinstance(gate, dict)
    }
    real_customer_gate = gates.get("real_customer_proof")
    if not real_customer_gate:
        raise RuntimeError("Owner launch readiness did not include real_customer_proof.")
    matched = _gate_evidence_value(
        real_customer_gate, "real_customer_matched_outcomes_7d"
    )
    blockers = list(real_customer_gate.get("blockers") or [])
    status = str(real_customer_gate.get("status") or "")
    if (
        status != "pass"
        or "real_customer_outcome_proof_missing" in blockers
        or int(matched or 0) < 1
    ):
        raise RuntimeError(
            "Owner launch readiness real_customer_proof did not pass: "
            f"status={status}, matched={matched}, blockers={blockers}"
        )
    return {
        "checked": True,
        "generated_at": payload.get("generated_at"),
        "overall_status": payload.get("overall_status"),
        "paid_launch_allowed": payload.get("paid_launch_allowed"),
        "real_customer_proof_status": status,
        "real_customer_matched_outcomes_7d": matched,
        "hard_blockers": list(payload.get("hard_blockers") or []),
    }


def _verify_owner_launch_readiness(client: Any, args: argparse.Namespace) -> dict[str, Any]:
    payload = _assert_response(
        client.get(
            "/v1/owner/launch-readiness",
            headers=_owner_headers(args),
        ),
        200,
        "owner launch readiness",
    )
    return _owner_launch_readiness_summary(payload)


def _summarise(
    fixture: dict[str, Any],
    args: argparse.Namespace,
    *,
    mode: str,
    runtime_decision: dict[str, Any],
    reconciliation: dict[str, Any],
    evidence_pack: dict[str, Any],
    connector_setup: dict[str, Any],
    owner_launch_readiness: dict[str, Any] | None,
    secrets: list[str],
) -> dict[str, Any]:
    evidence_outcomes = evidence_pack.get("outcome_reconciliation") or []
    evidence_call = evidence_pack.get("call") or {}
    reconciliation_metadata = reconciliation.get("metadata") or {}
    artifact_prefix = _artifact_prefix(fixture)
    call_id = (
        runtime_decision.get("call_id")
        or evidence_call.get("id")
        or args.call_id
        or fixture["trace"]["call_id"]
    )
    launch_readiness = {
        "owner_gate": "real_customer_proof",
        "proof_mode": reconciliation_metadata.get("proof_mode"),
        "real_customer_proof_candidate": (
            mode == "live"
            and reconciliation_metadata.get("proof_mode") == "live_customer"
            and reconciliation.get("verdict") == "matched"
            and bool(reconciliation.get("runtime_policy_decision_id"))
            and evidence_pack["verification_status"] == "pass"
            and bool(evidence_pack.get("evidence_hash"))
        ),
        "required_owner_blocker_to_clear": (
            "real_customer_proof:real_customer_outcome_proof_missing"
        ),
    }
    if owner_launch_readiness is not None:
        launch_readiness["owner_launch_readiness"] = owner_launch_readiness

    summary = {
        "mode": mode,
        "project_id": args.project_id or fixture["project_id"],
        "scenario": fixture.get("scenario") or "refund_outcome_proof_v1",
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
        "outcome_reconciliation": _outcome_reconciliation_summary(reconciliation),
        "connector_setup": connector_setup,
        "evidence_pack": {
            "decision_id": evidence_pack["decision_id"],
            "verification_status": evidence_pack["verification_status"],
            "evidence_hash": evidence_pack["evidence_hash"],
            "hash_algorithm": evidence_pack["hash_algorithm"],
            "outcome_count": len(evidence_outcomes),
            "audit_event_count": len(evidence_pack.get("audit_log") or []),
        },
        "launch_readiness": launch_readiness,
        "proof": {
            "captured_call_linked": evidence_call.get("id") == call_id,
            "unsafe_action_stopped": runtime_decision["allowed"] is False,
            "connector_configured": connector_setup.get("connected") is True
            and connector_setup.get("config_saved") is True,
            "connector_health_verified": connector_setup.get("health_status")
            == "healthy"
            and connector_setup.get("last_verdict") == "matched"
            and connector_setup.get("last_attempts") is not None,
            "real_connector_ready": connector_setup.get("readiness_status")
            == "ready",
            "matched_outcome_shown": reconciliation["verdict"] == "matched",
            "evidence_hash_visible": bool(evidence_pack.get("evidence_hash")),
            "evidence_pack_passed": evidence_pack["verification_status"] == "pass",
            "secrets_redacted": not _contains_secret(
                {
                    "connector_setup": connector_setup,
                    "reconciliation": reconciliation,
                    "evidence_pack": evidence_pack,
                },
                secrets,
            ),
        },
        "handoff": {
            "guide": HANDOFF_GUIDE_PATH.relative_to(ROOT).as_posix(),
            "package": _fixture_package(fixture),
            "connector_config_template": _connector_template_relative_path(fixture),
            "pass_criteria": [
                "captured_call_linked",
                "unsafe_action_stopped",
                "connector_configured",
                "connector_health_verified",
                "real_connector_ready",
                "matched_outcome_shown",
                "evidence_hash_visible",
                "evidence_pack_passed",
                "secrets_redacted",
            ],
            "customer_artifacts": [
                {
                    "flag": "--write-summary",
                    "default_path": f"artifacts/{artifact_prefix}-summary.json",
                    "contains": "redacted customer-facing proof summary",
                },
                {
                    "flag": "--write-evidence",
                    "default_path": f"artifacts/{artifact_prefix}-evidence.json",
                    "contains": "redacted audit evidence pack",
                },
            ],
            "failure_policy": (
                "Any false proof value, mismatched outcome, not_verified evidence, "
                "or missing evidence hash blocks partner handoff."
            ),
        },
        "next_live_preflight_command": _next_live_preflight_command(fixture),
        "next_live_command": _next_live_command(fixture),
        "next_saved_connector_preflight_command": _next_saved_connector_preflight_command(
            fixture
        ),
        "next_saved_connector_live_command": _next_saved_connector_live_command(fixture),
    }
    return _redact(summary, secrets)


def _summarise_preflight(
    fixture: dict[str, Any],
    args: argparse.Namespace,
    *,
    mode: str,
    reconciliation: dict[str, Any],
    connector_setup: dict[str, Any],
    secrets: list[str],
) -> dict[str, Any]:
    reconciliation_metadata = reconciliation.get("metadata") or {}
    summary = {
        "mode": mode,
        "project_id": args.project_id or fixture["project_id"],
        "scenario": fixture.get("scenario") or "refund_outcome_proof_v1",
        "connector_setup": connector_setup,
        "outcome_reconciliation": _outcome_reconciliation_summary(reconciliation),
        "launch_readiness": {
            "owner_gate": "real_customer_proof",
            "proof_mode": reconciliation_metadata.get("proof_mode"),
            "real_customer_proof_candidate": False,
            "required_owner_blocker_to_clear": (
                "real_customer_proof:real_customer_outcome_proof_missing"
            ),
        },
        "proof": {
            "connector_configured": connector_setup.get("connected") is True
            and connector_setup.get("config_saved") is True,
            "connector_health_verified": connector_setup.get("health_status")
            == "healthy"
            and connector_setup.get("last_verdict") == "matched"
            and connector_setup.get("last_attempts") is not None,
            "real_connector_ready": connector_setup.get("readiness_status")
            == "ready",
            "matched_outcome_shown": reconciliation["verdict"] == "matched",
            "secrets_redacted": not _contains_secret(
                {
                    "connector_setup": connector_setup,
                    "reconciliation": reconciliation,
                },
                secrets,
            ),
        },
        "handoff": {
            "guide": HANDOFF_GUIDE_PATH.relative_to(ROOT).as_posix(),
            "package": _fixture_package(fixture),
            "connector_config_template": _connector_template_relative_path(fixture),
            "sandbox_test_endpoint": connector_setup.get("test_endpoint"),
            "pass_criteria": [
                "connector_configured",
                "connector_health_verified",
                "real_connector_ready",
                "matched_outcome_shown",
                "secrets_redacted",
            ],
            "failure_policy": (
                "Any false proof value, mismatched outcome, not_verified connector "
                "health, or leaked secret blocks the full proof run."
            ),
        },
        "next_full_proof_command": (
            _next_saved_connector_live_command(fixture)
            if args.use_saved_connector
            else _next_live_command(fixture)
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


def _validate_preflight_summary(summary: dict[str, Any]) -> None:
    proof = summary.get("proof") or {}
    failures = [key for key, value in proof.items() if value is not True]
    if failures:
        raise RuntimeError(
            "Design-partner connector preflight failed: " + ", ".join(sorted(failures))
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
            "PROVIDER_KEY_VAULT_KEK": "design-partner-install-kit-kek-1234567890",
        }
    )
    return snapshot


def _seed_local_call(
    session_local: Any, fixture: dict[str, Any], args: argparse.Namespace
) -> None:
    from app.db.models import Call, Project

    agent = fixture["agent"]
    trace = fixture["trace"]
    claim = fixture["claimed_outcome"]
    risky_action = fixture["risky_action"]
    call_id = args.call_id or trace["call_id"]
    trace_id = args.trace_id or trace["trace_id"]
    project_id = args.project_id or fixture["project_id"]
    tool_args = dict(risky_action.get("tool_args") or {})
    if _fixture_scenario(fixture) == "customer-record":
        tool_args.update(
            {
                "customer_id": _customer_id(fixture, args),
                "email": args.email or claim.get("email"),
                "account_id": args.account_id or claim.get("account_id"),
                "status": args.customer_status or args.status or claim.get("status"),
            }
        )
    else:
        tool_args.update(
            {
                "refund_id": args.refund_id or claim["refund_id"],
                "amount_usd": args.amount_usd
                if args.amount_usd is not None
                else claim["amount_usd"],
            }
        )
    now = datetime.now(timezone.utc)
    with session_local() as session:
        if session.get(Project, project_id) is None:
            session.add(Project(id=project_id, name=project_id))
        session.add(
            Call(
                id=call_id,
                project_id=project_id,
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
                                "name": risky_action["tool_name"],
                                "args": tool_args,
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
                    "attempts": 1,
                    "retry_count": 0,
                    "max_attempts": self.max_attempts,
                    "timeout_seconds": self.timeout_seconds,
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
                "attempts": 1,
                "retry_count": 0,
                "max_attempts": self.max_attempts,
                "timeout_seconds": self.timeout_seconds,
            },
        )

    LedgerRefundApiConnector.fetch = fake_fetch

    def restore() -> None:
        LedgerRefundApiConnector.fetch = original_fetch

    return restore


def _install_local_customer_record_stub(fixture: dict[str, Any]) -> Any:
    from app.services.outcome_reconciliation import SourceRecord
    from app.services.system_of_record_connectors import CustomerRecordApiConnector

    original_fetch = CustomerRecordApiConnector.fetch
    expected_customer_id = fixture["claimed_outcome"]["customer_id"]
    crm = fixture["crm"]
    record = dict(crm["response"]["data"])
    record.setdefault("customer_id", record.get("id", expected_customer_id))

    def fake_fetch(self: Any) -> SourceRecord:
        request_url = (
            f"{str(self.base_url).rstrip('/')}/"
            f"{str(self.path_template).lstrip('/').replace('{customer_id}', self.customer_id)}"
        )
        if self.customer_id != expected_customer_id:
            return SourceRecord(
                record=None,
                record_found=False,
                metadata={
                    "connector_type": "customer_record_api",
                    "request_url": request_url,
                    "http_status": 404,
                    "customer_id": self.customer_id,
                    "adapter": "design_partner_local_stub",
                    "attempts": 1,
                    "retry_count": 0,
                    "max_attempts": self.max_attempts,
                    "timeout_seconds": self.timeout_seconds,
                },
            )
        return SourceRecord(
            record=record,
            record_found=True,
            metadata={
                "connector_type": "customer_record_api",
                "request_url": request_url,
                "http_status": 200,
                "record_path": crm["record_path"],
                "customer_id": self.customer_id,
                "adapter": "design_partner_local_stub",
                "attempts": 1,
                "retry_count": 0,
                "max_attempts": self.max_attempts,
                "timeout_seconds": self.timeout_seconds,
            },
        )

    CustomerRecordApiConnector.fetch = fake_fetch

    def restore() -> None:
        CustomerRecordApiConnector.fetch = original_fetch

    return restore


def _install_local_connector_stub(fixture: dict[str, Any]) -> Any:
    if _fixture_scenario(fixture) == "customer-record":
        return _install_local_customer_record_stub(fixture)
    return _install_local_ledger_stub(fixture)


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
        restore_connector: Any = None
        invalidate_all_fn: Any = None
        settings_cache_clear: Any = None
        try:
            logging.disable(logging.CRITICAL)
            sys.path.insert(0, str(BACKEND_DIR))
            warnings.filterwarnings(
                "ignore",
                message="Using `httpx` with `starlette.testclient` is deprecated.*",
            )

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
            restore_connector = _install_local_connector_stub(fixture)

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
                    reconciliation, connector_setup = _run_connector_setup(
                        client,
                        fixture,
                        args,
                        runtime_policy_decision_id=runtime_decision["id"],
                    )
                    evidence_pack = _assert_response(
                        client.get(
                            f"/v1/runtime-policy/decisions/{runtime_decision['id']}/evidence"
                        ),
                        200,
                        "runtime policy evidence pack",
                    )
            finally:
                if restore_connector is not None:
                    restore_connector()
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

    secrets = _connector_secrets(fixture, args)
    summary = _summarise(
        fixture,
        args,
        mode="local_demo",
        runtime_decision=runtime_decision,
        reconciliation=reconciliation,
        evidence_pack=evidence_pack,
        connector_setup=connector_setup,
        owner_launch_readiness=None,
        secrets=secrets,
    )
    return summary, evidence_pack


def _validate_live_connector_args(fixture: dict[str, Any], args: argparse.Namespace) -> None:
    if not args.api_base_url:
        raise RuntimeError("--api-base-url is required for live mode.")
    if not args.api_key and not args.bearer_token:
        raise RuntimeError(
            "Provide --api-key or --bearer-token for live mode authentication."
        )
    if _fixture_scenario(fixture) == "customer-record":
        if args.use_saved_connector:
            if not args.customer_id:
                raise RuntimeError(
                    "--customer-id is required with --use-saved-connector."
                )
            return
        if not args.crm_base_url:
            raise RuntimeError("--crm-base-url is required for customer-record live mode.")
        if not args.crm_bearer_token:
            raise RuntimeError(
                "--crm-bearer-token is required for customer-record live mode."
            )
        if not args.customer_id:
            raise RuntimeError("--customer-id is required for customer-record live mode.")
    else:
        if args.use_saved_connector:
            if not args.refund_id:
                raise RuntimeError("--refund-id is required with --use-saved-connector.")
            return
        if not args.ledger_base_url:
            raise RuntimeError("--ledger-base-url is required for refund live mode.")
        if not args.ledger_bearer_token:
            raise RuntimeError("--ledger-bearer-token is required for refund live mode.")
        if not args.refund_id:
            raise RuntimeError("--refund-id is required for refund live mode.")


def _run_live_preflight(fixture: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    _validate_live_connector_args(fixture, args)

    import httpx

    headers = _headers(args)
    timeout = args.timeout_seconds
    with httpx.Client(
        base_url=args.api_base_url.rstrip("/"), timeout=timeout
    ) as client:
        reconciliation, connector_setup = _run_connector_setup(
            client,
            fixture,
            args,
            runtime_policy_decision_id=None,
            headers=headers,
        )

    secrets = _connector_secrets(fixture, args)
    return _summarise_preflight(
        fixture,
        args,
        mode="live_preflight",
        reconciliation=reconciliation,
        connector_setup=connector_setup,
        secrets=secrets,
    )


def _run_live(
    fixture: dict[str, Any], args: argparse.Namespace
) -> tuple[dict[str, Any], dict[str, Any]]:
    _validate_live_connector_args(fixture, args)

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
        reconciliation, connector_setup = _run_connector_setup(
            client,
            fixture,
            args,
            runtime_policy_decision_id=runtime_decision["id"],
            headers=headers,
        )
        evidence_pack = _assert_response(
            client.get(
                f"/v1/runtime-policy/decisions/{runtime_decision['id']}/evidence",
                headers=headers,
            ),
            200,
            "runtime policy evidence pack",
        )
        owner_launch_readiness = (
            _verify_owner_launch_readiness(client, args)
            if args.verify_owner_launch_readiness
            else None
        )

    secrets = _connector_secrets(fixture, args)
    summary = _summarise(
        fixture,
        args,
        mode="live",
        runtime_decision=runtime_decision,
        reconciliation=reconciliation,
        evidence_pack=evidence_pack,
        connector_setup=connector_setup,
        owner_launch_readiness=owner_launch_readiness,
        secrets=secrets,
    )
    return summary, evidence_pack


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a design-partner install proof: runtime policy stop, system-of-record "
            "outcome verification, and downloadable evidence hash."
        )
    )
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIO_FIXTURES),
        default="refund",
        help="Proof scenario to run when --fixture is omitted.",
    )
    parser.add_argument(
        "--fixture",
        help="Scenario fixture JSON. Overrides --scenario when provided.",
    )
    parser.add_argument(
        "--write-evidence", help="Write the full evidence pack JSON to this path."
    )
    parser.add_argument(
        "--write-summary",
        help="Write the redacted customer-facing proof summary JSON to this path.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help=(
            "Save connector config and run the sandbox connector test endpoint only. "
            "Requires --api-base-url and does not generate an evidence pack."
        ),
    )
    parser.add_argument(
        "--use-saved-connector",
        action="store_true",
        help=(
            "Use the already saved system-of-record connector for live proof. "
            "Does not send the partner connector token in this run."
        ),
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
        "--verify-owner-launch-readiness",
        action="store_true",
        help=(
            "After a live full proof, verify owner /v1/owner/launch-readiness "
            "shows real_customer_proof=pass."
        ),
    )
    parser.add_argument(
        "--owner-admin-token",
        default=os.getenv("ZROKY_PROVISIONING_TOKEN") or os.getenv("PROVISIONING_TOKEN"),
        help=(
            "Owner provisioning token used only with --verify-owner-launch-readiness. "
            "Defaults to ZROKY_PROVISIONING_TOKEN or PROVISIONING_TOKEN."
        ),
    )
    parser.add_argument(
        "--owner-token-header",
        default=os.getenv("ZROKY_PROVISIONING_TOKEN_HEADER", "x-zroky-admin-token"),
        help="Owner token header name, default x-zroky-admin-token.",
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
    parser.add_argument(
        "--crm-base-url", help="HTTPS base URL for the partner CRM/customer API."
    )
    parser.add_argument(
        "--crm-bearer-token", help="Bearer token for the partner CRM/customer API."
    )
    parser.add_argument(
        "--crm-path-template",
        help="CRM path template, default /customers/{customer_id}.",
    )
    parser.add_argument(
        "--crm-record-path",
        help="Dot path to the customer object, default from fixture.",
    )
    parser.add_argument("--refund-id", help="Refund id to verify.")
    parser.add_argument("--customer-id", help="Customer id to verify in CRM.")
    parser.add_argument("--call-id", help="Zroky call id to link evidence.")
    parser.add_argument("--trace-id", help="Zroky trace id to link evidence.")
    parser.add_argument("--agent-name", help="Agent name shown in policy evidence.")
    parser.add_argument("--amount-usd", type=float, help="Claimed refund amount.")
    parser.add_argument("--currency", default=None, help="Claimed currency, e.g. USD.")
    parser.add_argument("--status", default=None, help="Claimed refund status.")
    parser.add_argument("--email", default=None, help="Claimed CRM email.")
    parser.add_argument("--account-id", default=None, help="Claimed CRM account id.")
    parser.add_argument(
        "--customer-status", default=None, help="Claimed CRM customer status."
    )
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
    print(f"connector_health_status={summary['connector_setup']['health_status']}")
    print(f"connector_readiness_status={summary['connector_setup']['readiness_status']}")
    print(f"connector_last_attempts={summary['connector_setup']['last_attempts']}")
    print(f"outcome_verdict={summary['outcome_reconciliation']['verdict']}")
    print(f"evidence_hash={summary['evidence_pack']['evidence_hash']}")
    print(
        f"evidence_verification_status={summary['evidence_pack']['verification_status']}"
    )
    owner_readiness = summary["launch_readiness"].get("owner_launch_readiness")
    if owner_readiness:
        print(
            "owner_real_customer_proof_status="
            f"{owner_readiness['real_customer_proof_status']}"
        )
        print(
            "owner_real_customer_matched_outcomes_7d="
            f"{owner_readiness['real_customer_matched_outcomes_7d']}"
        )
    print(f"secrets_redacted={str(summary['proof']['secrets_redacted']).lower()}")
    print("[design-partner-install-kit] passed")


def _print_preflight_summary(summary: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, sort_keys=True, separators=(",", ":"), default=str))
        return
    print(f"mode={summary['mode']}")
    print(f"project_id={summary['project_id']}")
    print(f"connector_health_status={summary['connector_setup']['health_status']}")
    print(f"connector_readiness_status={summary['connector_setup']['readiness_status']}")
    print(f"connector_last_attempts={summary['connector_setup']['last_attempts']}")
    print(f"outcome_verdict={summary['outcome_reconciliation']['verdict']}")
    print(f"secrets_redacted={str(summary['proof']['secrets_redacted']).lower()}")
    print("[design-partner-connector-preflight] passed")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    fixture_path = Path(args.fixture) if args.fixture else SCENARIO_FIXTURES[args.scenario]
    fixture = _load_json(fixture_path)
    if args.verify_owner_launch_readiness and args.preflight_only:
        raise RuntimeError(
            "--verify-owner-launch-readiness requires a full proof run; "
            "remove --preflight-only."
        )
    if args.verify_owner_launch_readiness and not args.api_base_url:
        raise RuntimeError(
            "--verify-owner-launch-readiness requires live mode with --api-base-url."
        )
    if args.preflight_only:
        if args.write_evidence:
            raise RuntimeError(
                "--write-evidence cannot be used with --preflight-only because "
                "no evidence pack is generated."
            )
        summary = _run_live_preflight(fixture, args)
        secrets = _connector_secrets(fixture, args)
        _validate_preflight_summary(summary)
        _write_summary(args.write_summary, summary, secrets)
        _print_preflight_summary(summary, as_json=args.json)
        return 0
    if args.api_base_url:
        summary, evidence_pack = _run_live(fixture, args)
    else:
        summary, evidence_pack = _run_local_demo(fixture, args)
    secrets = _connector_secrets(fixture, args)
    _validate_summary(summary)
    _write_summary(args.write_summary, summary, secrets)
    _write_evidence(args.write_evidence, evidence_pack, secrets)
    _print_summary(summary, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
