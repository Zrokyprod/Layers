"""Run manual Zroky protected-action scenarios.

Examples:
  python agent.py access-grant
  python agent.py refund-high
  python agent.py all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from scenarios import SCENARIOS, ActionIntent, Scenario, get_scenario, scenario_names


ROOT = Path(__file__).resolve().parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(path)
        return
    except ImportError:
        pass

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def normalize_env() -> None:
    legacy_project = os.environ.get("ZROKY_PROJECT")
    if legacy_project and not os.environ.get("ZROKY_PROJECT_ID"):
        os.environ["ZROKY_PROJECT_ID"] = legacy_project

    legacy_api_base = os.environ.get("ZROKY_INGEST_URL") or os.environ.get("ZROKY_API_BASE")
    if legacy_api_base and not os.environ.get("ZROKY_API_URL"):
        os.environ["ZROKY_API_URL"] = legacy_api_base


def require_env() -> None:
    missing = [name for name in ("ZROKY_API_KEY", "ZROKY_PROJECT_ID") if not os.environ.get(name)]
    if missing:
        print(
            "Missing required env: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and paste values from Zroky.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def init_zroky() -> None:
    try:
        import zroky
    except ImportError as exc:
        print("Could not import zroky. Run: pip install zroky python-dotenv", file=sys.stderr)
        raise SystemExit(2) from exc

    zroky.init(
        api_key=os.environ.get("ZROKY_API_KEY"),
        project=os.environ.get("ZROKY_PROJECT_ID"),
        ingest_url=os.environ.get("ZROKY_API_URL"),
        agent_id=os.environ.get("ZROKY_AGENT_ID") or None,
        agent_framework=os.environ.get("ZROKY_AGENT_FRAMEWORK") or "Custom Python",
        environment=os.environ.get("ZROKY_ENVIRONMENT") or "development",
        workflow_name="manual-agent-lab",
    )


def api_base() -> str:
    raw = os.environ.get("ZROKY_API_URL", "https://api.zroky.com").strip().rstrip("/")
    parsed = urlsplit(raw)
    path = parsed.path.rstrip("/")
    for suffix in ("/api/v1/ingest", "/v1/ingest", "/ingest"):
        if path.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            break
    if parsed.scheme and parsed.netloc:
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")
    return raw


def auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['ZROKY_API_KEY']}",
        "Content-Type": "application/json",
        "x-api-key": os.environ["ZROKY_API_KEY"],
        "x-project-id": os.environ["ZROKY_PROJECT_ID"],
    }


def contract_payload(intent: ActionIntent) -> dict[str, Any]:
    contract_key, version = intent.contract_version.rsplit("/", 1)
    required_resource = sorted(intent.resource.keys())
    required_params = sorted(intent.params.keys())
    return {
        "contract_key": contract_key,
        "version": version,
        "action_type": intent.action,
        "operation_kind": intent.operation_kind,
        "domain_family": intent.domain_family,
        "risk_class": intent.risk_class,
        "connector_family": intent.connector_family,
        "schema": {
            "type": "object",
            "required": ["resource", "parameters"],
            "properties": {
                "resource": {
                    "type": "object",
                    "required": required_resource,
                    "additionalProperties": True,
                },
                "parameters": {
                    "type": "object",
                    "required": required_params,
                    "additionalProperties": True,
                },
            },
            "additionalProperties": False,
        },
        "verification_profile": {
            "minimum_level": "V2",
            "source_of_record": intent.connector_family,
            "manual_qa": True,
            "mock_result": intent.mock_result,
        },
    }


def unique_contract_intents() -> list[ActionIntent]:
    seen: set[str] = set()
    intents: list[ActionIntent] = []
    for scenario in SCENARIOS.values():
        for intent in scenario.actions:
            if intent.contract_version in seen:
                continue
            seen.add(intent.contract_version)
            intents.append(intent)
    return intents


def bootstrap_contracts() -> int:
    require_env()
    base = api_base()
    print(f"Registering Manual QA action contracts in {os.environ['ZROKY_PROJECT_ID']}...")
    created = 0
    reused = 0
    for intent in unique_contract_intents():
        payload = contract_payload(intent)
        response = httpx.post(
            f"{base}/v1/action-contracts",
            headers=auth_headers(),
            json=payload,
            timeout=10.0,
        )
        if response.status_code in {200, 201}:
            created += 1
            print(f"  ready  {intent.contract_version}")
            continue
        if response.status_code == 409:
            reused += 1
            print(f"  exists {intent.contract_version}")
            continue
        if response.status_code in {401, 403}:
            print(
                "\nCould not register contracts with this API key.",
                "The runtime key can send actions, but contract registration requires project admin access.",
                sep="\n",
                file=sys.stderr,
            )
            print(
                "Fix: install/register the Manual QA contracts from an admin session, "
                "or create an admin-scoped setup key for bootstrap only.",
                file=sys.stderr,
            )
            print(f"Backend response: HTTP {response.status_code} {response.text[:240]}", file=sys.stderr)
            return 2
        print(f"Failed {intent.contract_version}: HTTP {response.status_code} {response.text[:240]}", file=sys.stderr)
        return 2
    print(f"Done. ready={created} existing={reused}")
    return 0


def submit_action(intent: ActionIntent, scenario_name: str, index: int) -> dict[str, Any]:
    import zroky

    trace_context = {
        "scenario": scenario_name,
        "step": index,
        "agent_name": os.environ.get("ZROKY_AGENT_NAME", "Manual QA Agent"),
        "mock_result": intent.mock_result,
    }

    return zroky.protect(
        action=intent.action,
        contract_version=intent.contract_version,
        operation_kind=intent.operation_kind,
        params=intent.params,
        resource=intent.resource,
        purpose=intent.purpose,
        verification_profile=intent.verification_profile,
        environment=os.environ.get("ZROKY_ENVIRONMENT", "development"),
        trace_context=trace_context,
        raise_on_approval=False,
    )


def run_scenario(scenario: Scenario) -> list[dict[str, Any]]:
    print(f"\n== {scenario.name} ==")
    print(scenario.description)
    print("Expected modules:", ", ".join(scenario.expected_dashboard_modules))

    results: list[dict[str, Any]] = []
    for index, intent in enumerate(scenario.actions, start=1):
        print(f"\n[{index}/{len(scenario.actions)}] {intent.action}")
        try:
            result = submit_action(intent, scenario.name, index)
        except Exception as exc:
            message = str(exc)
            if "Action contract version not found" in message:
                print(
                    "\nThis project does not have the Manual QA action contracts yet.",
                    "Run: python agent.py bootstrap",
                    "Then rerun this scenario.",
                    sep="\n",
                    file=sys.stderr,
                )
            raise
        results.append(result)
        print(json.dumps(result, indent=2, default=str))
    return results


def main() -> int:
    load_env_file(ROOT / ".env")
    normalize_env()

    parser = argparse.ArgumentParser(description="Run Zroky manual protected-action scenarios.")
    parser.add_argument(
        "scenario",
        choices=[*scenario_names(), "all", "bootstrap"],
        help="Scenario to run. Use 'bootstrap' once to register contracts.",
    )
    args = parser.parse_args()

    require_env()
    if args.scenario == "bootstrap":
        return bootstrap_contracts()

    init_zroky()

    names = scenario_names() if args.scenario == "all" else [args.scenario]
    all_results: dict[str, list[dict[str, Any]]] = {}

    for name in names:
        all_results[name] = run_scenario(get_scenario(name))

    print("\nDone. Open the dashboard and verify: Actions, Approvals, Outcomes, Evidence, Policies, Connectors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
