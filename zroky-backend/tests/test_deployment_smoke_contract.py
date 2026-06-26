from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "run_deployment_smoke.py"
STAGING_ROLLOUT_WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "zroky-staging-rollout-verify.yml"
)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_deployment_smoke", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_staging_rollout_workflow_defaults_to_zroky_staging_domain() -> None:
    workflow = STAGING_ROLLOUT_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "default: https://api-staging.zroky.com" in workflow
    assert ("https://api-staging." + "example" + ".com") not in workflow


def test_backend_only_deployment_smoke_skips_frontend_surfaces(
    monkeypatch,
    capsys,
) -> None:
    module = _load_script()
    calls: list[str] = []

    monkeypatch.setattr(
        module,
        "_check_health",
        lambda api_base_url, timeout: calls.append(f"health:{api_base_url}:{timeout}"),
    )
    monkeypatch.setattr(
        module,
        "_provision_project",
        lambda api_base_url, provisioning_token, provisioning_header, timeout: (
            calls.append(
                f"provision:{api_base_url}:{provisioning_token}:{provisioning_header}:{timeout}"
            )
            or ("proj_staging_smoke", "zk_live_staging_smoke", "key_smoke")
        ),
    )
    monkeypatch.setattr(
        module,
        "_check_api_key_lifecycle",
        lambda api_base_url, project_id, provisioning_token, provisioning_header, timeout: (
            calls.append(f"api-key-lifecycle:{project_id}:{provisioning_token}")
            or {
                "api_key_lifecycle_key_a_id": "key_a",
                "api_key_lifecycle_key_b_id": "key_b",
            }
        ),
    )
    monkeypatch.setattr(
        module,
        "_ingest_call",
        lambda api_base_url, api_key, timeout: (
            calls.append(f"ingest:{api_key}") or "call_staging_smoke"
        ),
    )
    monkeypatch.setattr(
        module,
        "_check_issues",
        lambda api_base_url, api_key, expected_issue_id, timeout: calls.append(
            f"issues:{api_key}:{expected_issue_id}"
        ),
    )
    monkeypatch.setattr(
        module,
        "_check_provider_vault",
        lambda api_base_url, api_key, timeout: (
            calls.append(f"provider-vault:{api_key}") or "provider_key_smoke"
        ),
    )
    monkeypatch.setattr(
        module,
        "_check_replay_and_ci",
        lambda api_base_url, api_key, call_id, expect_plan_gate, timeout: (
            calls.append(f"replay-ci:{call_id}:{expect_plan_gate}") or {}
        ),
    )

    def frontend_called(*_args, **_kwargs) -> None:
        raise AssertionError("frontend smoke should be skipped in backend-only mode")

    monkeypatch.setattr(module, "_check_dashboard", frontend_called)
    monkeypatch.setattr(module, "_check_landing", frontend_called)

    assert (
        module.main(
            [
                "--api-base-url",
                "https://api-staging.zroky.com",
                "--provisioning-token",
                "staging-provisioning-token",
                "--timeout-seconds",
                "7",
                "--backend-only",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "[SKIP] dashboard smoke skipped" in output
    assert "[SKIP] landing smoke skipped" in output
    assert "[deployment-smoke] passed" in output
    assert calls == [
        "health:https://api-staging.zroky.com:7.0",
        "provision:https://api-staging.zroky.com:staging-provisioning-token:X-Zroky-Admin-Token:7.0",
        "api-key-lifecycle:proj_staging_smoke:staging-provisioning-token",
        "ingest:zk_live_staging_smoke",
        "issues:zk_live_staging_smoke:None",
        "provider-vault:zk_live_staging_smoke",
        "replay-ci:call_staging_smoke:True",
    ]


def test_deployment_smoke_requires_provisioning_token(capsys) -> None:
    module = _load_script()

    assert module.main(["--api-base-url", "https://api-staging.zroky.com"]) == 2

    assert "provisioning-token is required" in capsys.readouterr().out
