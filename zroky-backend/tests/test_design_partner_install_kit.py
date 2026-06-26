from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "run_design_partner_install_kit.py"
FIXTURE_PATH = (
    ROOT / "demos" / "design-partner-install-kit" / "refund_agent_fixture.json"
)
CUSTOMER_RECORD_FIXTURE_PATH = (
    ROOT
    / "demos"
    / "design-partner-install-kit"
    / "customer_record_agent_fixture.json"
)
HANDOFF_GUIDE_PATH = ROOT / "demos" / "design-partner-install-kit" / "HANDOFF.txt"
LEDGER_TEMPLATE_PATH = (
    ROOT
    / "demos"
    / "design-partner-install-kit"
    / "ledger_refund_connector_config.example.json"
)
CUSTOMER_RECORD_TEMPLATE_PATH = (
    ROOT
    / "demos"
    / "design-partner-install-kit"
    / "customer_record_connector_config.example.json"
)
OWNER_PROOF_WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "zroky-design-partner-owner-proof.yml"
)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_design_partner_install_kit", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_design_partner_fixture_has_no_missing_install_inputs() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert fixture["agent"]["name"] == "refund-ops-agent"
    assert fixture["risky_action"]["tool_name"] == "refund_payment"
    assert fixture["risky_action"]["external_action"] is True
    assert fixture["claimed_outcome"]["refund_id"]
    assert fixture["ledger"]["base_url"].startswith("https://")
    assert fixture["ledger"]["record_path"] == "data"
    assert fixture["expected"]["connector_health_status"] == "healthy"
    assert fixture["expected"]["connector_last_attempts"] == 1
    assert fixture["expected"]["connector_retry_count"] == 0
    assert fixture["ledger"]["bearer_token"] not in json.dumps(
        fixture["expected"], sort_keys=True
    )


def test_design_partner_customer_record_fixture_has_no_missing_install_inputs() -> None:
    fixture = json.loads(CUSTOMER_RECORD_FIXTURE_PATH.read_text(encoding="utf-8"))

    assert fixture["scenario"] == "crm_customer_record_proof_v1"
    assert fixture["agent"]["name"] == "customer-ops-agent"
    assert fixture["risky_action"]["tool_name"] == "delete_customer_record"
    assert fixture["risky_action"]["external_action"] is True
    assert fixture["claimed_outcome"]["customer_id"]
    assert fixture["claimed_outcome"]["email"]
    assert fixture["claimed_outcome"]["account_id"]
    assert fixture["crm"]["base_url"].startswith("https://")
    assert fixture["crm"]["record_path"] == "data"
    assert fixture["expected"]["connector_health_status"] == "healthy"
    assert fixture["expected"]["connector_last_attempts"] == 1
    assert fixture["expected"]["connector_retry_count"] == 0
    assert fixture["crm"]["bearer_token"] not in json.dumps(
        fixture["expected"], sort_keys=True
    )


def test_design_partner_connector_templates_are_customer_safe() -> None:
    ledger = json.loads(LEDGER_TEMPLATE_PATH.read_text(encoding="utf-8"))
    crm = json.loads(CUSTOMER_RECORD_TEMPLATE_PATH.read_text(encoding="utf-8"))
    rendered = json.dumps({"ledger": ledger, "crm": crm}, sort_keys=True)

    assert ledger["connector_type"] == "ledger_refund_api"
    assert ledger["config_endpoint"] == (
        "/v1/integrations/system-of-record/ledger-refund/config"
    )
    assert ledger["test_endpoint"] == (
        "/v1/integrations/system-of-record/ledger-refund/test"
    )
    assert ledger["saved_runtime_endpoint"] == (
        "/v1/outcomes/reconciliation/ledger-refund/saved"
    )
    assert ledger["config_payload"]["path_template"] == "/refunds/{refund_id}"
    assert ledger["config_payload"]["bearer_token"] == "<ledger_bearer_token>"
    assert ledger["test_payload"]["match_fields"] == [
        "refund_id",
        "amount_usd",
        "currency",
        "status",
    ]
    assert ledger["test_payload"]["metadata"]["proof_mode"] == "preflight"
    assert (
        ledger["test_payload"]["metadata"]["real_customer_proof_candidate"] is False
    )
    assert ledger["saved_runtime_payload"]["runtime_policy_decision_id"] == (
        "<runtime_policy_decision_id>"
    )
    assert ledger["saved_runtime_payload"]["refund_id"] == "RF-DP-1001"
    assert ledger["saved_runtime_payload"]["metadata"]["proof_mode"] == "live_customer"
    assert (
        ledger["saved_runtime_payload"]["metadata"]["real_customer_proof_candidate"]
        is True
    )
    assert "bearer_token" not in json.dumps(
        ledger["saved_runtime_payload"], sort_keys=True
    )
    assert ledger["readiness_contract"]["system_of_record"] == "ledger_refund"
    assert ledger["readiness_contract"]["required_record_fields"] == [
        "refund_id",
        "status",
    ]
    assert "http_2xx" in ledger["readiness_contract"]["ready_when"]
    assert ledger["pass_criteria"]["readiness_status"] == "ready"
    assert ledger["pass_criteria"]["last_error_code"] is None

    assert crm["connector_type"] == "customer_record_api"
    assert crm["config_endpoint"] == (
        "/v1/integrations/system-of-record/customer-record/config"
    )
    assert crm["test_endpoint"] == (
        "/v1/integrations/system-of-record/customer-record/test"
    )
    assert crm["saved_runtime_endpoint"] == (
        "/v1/outcomes/reconciliation/customer-record/saved"
    )
    assert crm["config_payload"]["path_template"] == "/customers/{customer_id}"
    assert crm["config_payload"]["bearer_token"] == "<crm_bearer_token>"
    assert crm["test_payload"]["match_fields"] == [
        "customer_id",
        "email",
        "account_id",
        "status",
    ]
    assert crm["test_payload"]["metadata"]["proof_mode"] == "preflight"
    assert crm["test_payload"]["metadata"]["real_customer_proof_candidate"] is False
    assert crm["saved_runtime_payload"]["runtime_policy_decision_id"] == (
        "<runtime_policy_decision_id>"
    )
    assert crm["saved_runtime_payload"]["customer_id"] == "CUS-DP-2001"
    assert crm["saved_runtime_payload"]["metadata"]["proof_mode"] == "live_customer"
    assert (
        crm["saved_runtime_payload"]["metadata"]["real_customer_proof_candidate"]
        is True
    )
    assert "bearer_token" not in json.dumps(
        crm["saved_runtime_payload"], sort_keys=True
    )
    assert crm["readiness_contract"]["system_of_record"] == "customer_record"
    assert crm["readiness_contract"]["required_record_fields"] == [
        "customer_id",
        "status",
    ]
    assert "connector_attempted" in crm["readiness_contract"]["ready_when"]
    assert crm["pass_criteria"]["readiness_status"] == "ready"
    assert crm["pass_criteria"]["last_retryable"] is None

    assert "ledger-demo-token-not-persisted" not in rendered
    assert "crm-demo-token-not-persisted" not in rendered


def test_design_partner_handoff_guide_covers_customer_run_contract() -> None:
    guide = HANDOFF_GUIDE_PATH.read_text(encoding="utf-8")
    compact_guide = " ".join(guide.split())

    assert "python scripts/run_design_partner_install_kit.py --scenario refund --json" in guide
    assert (
        "python scripts/run_design_partner_install_kit.py --scenario customer-record --json"
        in guide
    )
    assert "--write-summary artifacts/design-partner-refund-summary.json" in guide
    assert "--write-evidence artifacts/design-partner-refund-evidence.json" in guide
    assert "--write-summary artifacts/design-partner-crm-summary.json" in guide
    assert "--write-evidence artifacts/design-partner-crm-evidence.json" in guide
    assert "ledger_refund_connector_config.example.json" in guide
    assert "customer_record_connector_config.example.json" in guide
    assert "--preflight-only --api-base-url https://api.zroky.com" in compact_guide
    assert "--write-summary artifacts/design-partner-refund-preflight-summary.json" in guide
    assert "--write-summary artifacts/design-partner-crm-preflight-summary.json" in guide
    assert "--use-saved-connector --api-base-url https://api.zroky.com" in compact_guide
    assert "--write-summary artifacts/design-partner-refund-saved-live-summary.json" in guide
    assert "--write-evidence artifacts/design-partner-refund-saved-live-evidence.json" in guide
    assert "--write-summary artifacts/design-partner-crm-saved-live-summary.json" in guide
    assert "--write-evidence artifacts/design-partner-crm-saved-live-evidence.json" in guide
    assert "--api-base-url https://api.zroky.com" in compact_guide
    assert "--ledger-base-url https://ledger.example.com/api" in guide
    assert "--crm-base-url https://crm.example.com/api" in guide
    assert "runtime_policy.allowed" in guide
    assert "connector_setup.status_endpoint" in guide
    assert "connector_setup.config_endpoint" in guide
    assert "connector_setup.test_endpoint" in guide
    assert "connector_setup.health_status" in guide
    assert "connector_setup.readiness_status" in guide
    assert "connector_setup.readiness_blockers" in guide
    assert "connector_setup.last_attempts" in guide
    assert "connector_setup.last_error_code" in guide
    assert "connector_setup.last_retryable" in guide
    assert "outcome_reconciliation.verdict" in guide
    assert "outcome_reconciliation.connector_attempts" in guide
    assert "outcome_reconciliation.connector_error_code" in guide
    assert "launch_readiness.proof_mode" in guide
    assert "launch_readiness.real_customer_proof_candidate" in guide
    assert "owner `real_customer_proof` launch gate" in guide
    assert "--verify-owner-launch-readiness" in guide
    assert "--owner-admin-token <owner_admin_token>" in guide
    assert "launch_readiness.owner_launch_readiness.real_customer_proof_status" in guide
    assert "evidence_pack.evidence_hash" in guide
    assert "secrets_redacted" in guide
    assert "not_verified" in guide
    assert "ledger-demo-token-not-persisted" not in guide
    assert "crm-demo-token-not-persisted" not in guide


def test_design_partner_owner_proof_workflow_runs_live_gate_with_required_secrets() -> None:
    workflow = OWNER_PROOF_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "name: Zroky Design Partner Owner Proof" in workflow
    assert "workflow_dispatch:" in workflow
    assert "api_base_url:" in workflow
    assert "default: https://api-staging.zroky.com" in workflow
    assert ("https://api-staging." + "example" + ".com") not in workflow
    assert "project_id:" in workflow
    assert "call_id:" in workflow
    assert "trace_id:" in workflow
    assert "refund_id:" in workflow
    assert "customer_id:" in workflow
    assert "api_base_url must be a real backend URL, not example.com" in workflow
    assert "secrets.ZROKY_STAGING_API_KEY" in workflow
    assert "secrets.ZROKY_STAGING_PROVISIONING_TOKEN" in workflow
    assert "secrets.ZROKY_STAGING_LEDGER_BEARER_TOKEN" in workflow
    assert "secrets.ZROKY_STAGING_CRM_BEARER_TOKEN" in workflow
    assert "--verify-owner-launch-readiness" in workflow
    assert "--owner-admin-token" in workflow
    assert "--project-id" in workflow
    assert "--call-id" in workflow
    assert "--trace-id" in workflow
    assert "Validate owner proof artifacts" in workflow
    assert "scripts/verify_design_partner_owner_proof_artifact.py" in workflow
    assert "--summary artifacts/design-partner-owner-proof-summary.json" in workflow
    assert "--evidence artifacts/design-partner-owner-proof-evidence.json" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "design-partner-owner-proof-summary.json" in workflow
    assert "design-partner-owner-proof-evidence.json" in workflow


def test_design_partner_install_kit_local_demo_outputs_auditable_proof(
    capsys,
) -> None:
    module = _load_script()

    assert module.main(["--json"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "local_demo"
    assert output["scenario"] == "refund_outcome_proof_v1"
    assert output["call_id"] == "dp-call-refund-1001"
    assert output["trace_id"] == "dp-trace-refund-1001"
    assert output["runtime_policy"]["allowed"] is False
    assert output["runtime_policy"]["status"] in {"blocked", "pending_approval"}
    assert output["outcome_reconciliation"]["verdict"] == "matched"
    assert output["outcome_reconciliation"]["connector_type"] == "ledger_refund_api"
    assert output["outcome_reconciliation"]["connector_attempts"] == 1
    assert output["outcome_reconciliation"]["connector_retry_count"] == 0
    assert output["outcome_reconciliation"]["connector_max_attempts"] == 2
    assert output["outcome_reconciliation"]["connector_timeout_seconds"] is not None
    assert output["outcome_reconciliation"]["connector_error"] is None
    assert output["outcome_reconciliation"]["connector_error_code"] is None
    assert output["outcome_reconciliation"]["connector_retryable"] is None
    assert output["connector_setup"]["status_endpoint"] == (
        "/v1/integrations/system-of-record/ledger-refund/status"
    )
    assert output["connector_setup"]["config_endpoint"] == (
        "/v1/integrations/system-of-record/ledger-refund/config"
    )
    assert output["connector_setup"]["test_endpoint"] == (
        "/v1/integrations/system-of-record/ledger-refund/test"
    )
    assert output["connector_setup"]["connected"] is True
    assert output["connector_setup"]["config_saved"] is True
    assert output["connector_setup"]["has_bearer_token"] is True
    assert output["connector_setup"]["bearer_token_last4"] == "sted"
    assert output["connector_setup"]["health_status"] == "healthy"
    assert output["connector_setup"]["last_verdict"] == "matched"
    assert output["connector_setup"]["last_http_status"] == 200
    assert output["connector_setup"]["last_attempts"] == 1
    assert output["connector_setup"]["last_error_code"] is None
    assert output["connector_setup"]["last_retryable"] is None
    assert output["connector_setup"]["readiness_status"] == "ready"
    assert output["connector_setup"]["readiness_blockers"] == []
    assert all(output["connector_setup"]["readiness_checks"].values())
    assert output["connector_setup"]["readiness_contract"]["system_of_record"] == (
        "ledger_refund"
    )
    assert output["connector_setup"]["retry_count"] == 0
    assert output["connector_setup"]["max_attempts"] == 2
    assert output["connector_setup"]["error_code"] is None
    assert output["connector_setup"]["retryable"] is None
    assert output["connector_setup"]["test_ok"] is True
    assert output["connector_setup"]["test_source"] == "saved_connector_test"
    assert output["connector_setup"]["secrets_redacted"] is True
    assert output["evidence_pack"]["verification_status"] == "pass"
    assert len(output["evidence_pack"]["evidence_hash"]) == 64
    assert output["launch_readiness"] == {
        "owner_gate": "real_customer_proof",
        "proof_mode": "local_demo",
        "real_customer_proof_candidate": False,
        "required_owner_blocker_to_clear": (
            "real_customer_proof:real_customer_outcome_proof_missing"
        ),
    }
    assert output["proof"] == {
        "captured_call_linked": True,
        "unsafe_action_stopped": True,
        "connector_configured": True,
        "connector_health_verified": True,
        "real_connector_ready": True,
        "matched_outcome_shown": True,
        "evidence_hash_visible": True,
        "evidence_pack_passed": True,
        "secrets_redacted": True,
    }
    assert output["handoff"]["guide"] == "demos/design-partner-install-kit/HANDOFF.txt"
    assert output["handoff"]["package"] == "design_partner_refund_v1"
    assert output["handoff"]["connector_config_template"] == (
        "demos/design-partner-install-kit/ledger_refund_connector_config.example.json"
    )
    assert set(output["handoff"]["pass_criteria"]) == set(output["proof"].keys())
    assert output["handoff"]["customer_artifacts"][0]["default_path"] == (
        "artifacts/design-partner-refund-summary.json"
    )
    assert output["handoff"]["customer_artifacts"][1]["default_path"] == (
        "artifacts/design-partner-refund-evidence.json"
    )
    assert "--scenario refund --preflight-only" in output["next_live_preflight_command"]
    assert "--scenario refund" in output["next_live_command"]
    assert "--write-summary artifacts/design-partner-refund-live-summary.json" in output[
        "next_live_command"
    ]
    assert "ledger-demo-token-not-persisted" not in json.dumps(output)


def test_design_partner_install_kit_customer_record_demo_outputs_auditable_proof(
    capsys,
) -> None:
    module = _load_script()

    assert module.main(["--scenario", "customer-record", "--json"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "local_demo"
    assert output["scenario"] == "crm_customer_record_proof_v1"
    assert output["call_id"] == "dp-call-crm-2001"
    assert output["trace_id"] == "dp-trace-crm-2001"
    assert output["runtime_policy"]["allowed"] is False
    assert output["runtime_policy"]["status"] in {"blocked", "pending_approval"}
    assert output["outcome_reconciliation"]["verdict"] == "matched"
    assert output["outcome_reconciliation"]["connector_type"] == "customer_record_api"
    assert output["outcome_reconciliation"]["system_ref"] == "crm:CUS-DP-2001"
    assert output["outcome_reconciliation"]["match_fields"] == [
        "customer_id",
        "email",
        "account_id",
        "status",
    ]
    assert output["outcome_reconciliation"]["connector_attempts"] == 1
    assert output["outcome_reconciliation"]["connector_retry_count"] == 0
    assert output["outcome_reconciliation"]["connector_max_attempts"] == 2
    assert output["outcome_reconciliation"]["connector_error"] is None
    assert output["outcome_reconciliation"]["connector_error_code"] is None
    assert output["outcome_reconciliation"]["connector_retryable"] is None
    assert output["connector_setup"]["status_endpoint"] == (
        "/v1/integrations/system-of-record/customer-record/status"
    )
    assert output["connector_setup"]["config_endpoint"] == (
        "/v1/integrations/system-of-record/customer-record/config"
    )
    assert output["connector_setup"]["test_endpoint"] == (
        "/v1/integrations/system-of-record/customer-record/test"
    )
    assert output["connector_setup"]["connected"] is True
    assert output["connector_setup"]["config_saved"] is True
    assert output["connector_setup"]["has_bearer_token"] is True
    assert output["connector_setup"]["bearer_token_last4"] == "sted"
    assert output["connector_setup"]["health_status"] == "healthy"
    assert output["connector_setup"]["last_verdict"] == "matched"
    assert output["connector_setup"]["last_http_status"] == 200
    assert output["connector_setup"]["last_attempts"] == 1
    assert output["connector_setup"]["last_error_code"] is None
    assert output["connector_setup"]["last_retryable"] is None
    assert output["connector_setup"]["readiness_status"] == "ready"
    assert output["connector_setup"]["readiness_blockers"] == []
    assert all(output["connector_setup"]["readiness_checks"].values())
    assert output["connector_setup"]["readiness_contract"]["system_of_record"] == (
        "customer_record"
    )
    assert output["connector_setup"]["error_code"] is None
    assert output["connector_setup"]["retryable"] is None
    assert output["connector_setup"]["test_ok"] is True
    assert output["connector_setup"]["test_source"] == "saved_connector_test"
    assert output["connector_setup"]["secrets_redacted"] is True
    assert output["evidence_pack"]["verification_status"] == "pass"
    assert len(output["evidence_pack"]["evidence_hash"]) == 64
    assert output["launch_readiness"]["proof_mode"] == "local_demo"
    assert output["launch_readiness"]["real_customer_proof_candidate"] is False
    assert output["proof"] == {
        "captured_call_linked": True,
        "unsafe_action_stopped": True,
        "connector_configured": True,
        "connector_health_verified": True,
        "real_connector_ready": True,
        "matched_outcome_shown": True,
        "evidence_hash_visible": True,
        "evidence_pack_passed": True,
        "secrets_redacted": True,
    }
    assert output["handoff"]["package"] == "design_partner_crm_v1"
    assert output["handoff"]["connector_config_template"] == (
        "demos/design-partner-install-kit/customer_record_connector_config.example.json"
    )
    assert output["handoff"]["customer_artifacts"][0]["default_path"] == (
        "artifacts/design-partner-crm-summary.json"
    )
    assert output["handoff"]["customer_artifacts"][1]["default_path"] == (
        "artifacts/design-partner-crm-evidence.json"
    )
    assert (
        "--scenario customer-record --preflight-only"
        in output["next_live_preflight_command"]
    )
    assert "--scenario customer-record" in output["next_live_command"]
    assert "crm-demo-token-not-persisted" not in json.dumps(output)


def test_design_partner_live_preflight_runs_connector_test_without_evidence(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    module = _load_script()
    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    def status_payload(*, connected: bool, healthy: bool = False):
        return {
            "connected": connected,
            "connector_type": "ledger_refund_api",
            "base_url": "https://ledger.partner.example/api" if connected else None,
            "path_template": "/refunds/{refund_id}" if connected else None,
            "record_path": "data" if connected else None,
            "query": None,
            "has_bearer_token": connected,
            "bearer_token_last4": "cret" if connected else None,
            "last_tested_at": "2026-06-21T12:00:00Z" if healthy else None,
            "health_status": "healthy" if healthy else "not_verified",
            "last_verdict": "matched" if healthy else None,
            "last_error": None,
            "last_error_code": None,
            "last_http_status": 200 if healthy else None,
            "last_attempts": 1 if healthy else None,
            "last_retryable": None,
            "last_checked_at": "2026-06-21T12:00:00Z" if healthy else None,
            "created_at": "2026-06-21T12:00:00Z" if connected else None,
            "updated_at": "2026-06-21T12:00:00Z" if connected else None,
        }

    check_payload = {
        "id": "rec-live-preflight-1",
        "verdict": "matched",
        "reason": None,
        "connector_type": "ledger_refund_api",
        "system_ref": "ledger:RF-LIVE-1",
        "metadata": {
            "source": "saved_connector_test",
            "proof_mode": "preflight",
            "real_customer_proof_candidate": False,
            "match_fields": ["refund_id", "amount_usd", "currency", "status"],
            "connector": {
                "connector_type": "ledger_refund_api",
                "request_url": "https://ledger.partner.example/api/refunds/RF-LIVE-1",
                "http_status": 200,
                "attempts": 1,
                "retry_count": 0,
                "max_attempts": 2,
                "timeout_seconds": 10.0,
            },
        },
    }

    class FakeClient:
        def __init__(self, *, base_url, timeout):
            assert base_url == "https://api.zroky.com"
            assert timeout == 10.0
            self.saved = False
            self.tested = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def get(self, path, headers=None):
            calls.append(("get", path, headers, None))
            if self.tested:
                return FakeResponse(200, status_payload(connected=True, healthy=True))
            return FakeResponse(200, status_payload(connected=self.saved))

        def put(self, path, headers=None, json=None):
            calls.append(("put", path, headers, json))
            assert path == "/v1/integrations/system-of-record/ledger-refund/config"
            assert headers["x-api-key"] == "zroky-live-key"
            assert json["base_url"] == "https://ledger.partner.example/api"
            assert json["bearer_token"] == "ledger-live-token-secret"
            self.saved = True
            return FakeResponse(200, status_payload(connected=True))

        def post(self, path, headers=None, json=None):
            calls.append(("post", path, headers, json))
            assert path == "/v1/integrations/system-of-record/ledger-refund/test"
            assert json["runtime_policy_decision_id"] is None
            assert json["refund_id"] == "RF-LIVE-1"
            assert json["metadata"]["proof_mode"] == "preflight"
            assert json["metadata"]["real_customer_proof_candidate"] is False
            self.tested = True
            return FakeResponse(
                201,
                {
                    "ok": True,
                    "check": check_payload,
                    "connector": status_payload(connected=True, healthy=True),
                },
            )

    import httpx

    monkeypatch.setattr(httpx, "Client", FakeClient)
    summary_path = tmp_path / "preflight-summary.json"

    assert module.main(
        [
            "--scenario",
            "refund",
            "--preflight-only",
            "--api-base-url",
            "https://api.zroky.com",
            "--api-key",
            "zroky-live-key",
            "--ledger-base-url",
            "https://ledger.partner.example/api",
            "--ledger-bearer-token",
            "ledger-live-token-secret",
            "--refund-id",
            "RF-LIVE-1",
            "--json",
            "--write-summary",
            str(summary_path),
        ]
    ) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "live_preflight"
    assert "runtime_policy" not in output
    assert "evidence_pack" not in output
    assert output["connector_setup"]["config_saved"] is True
    assert output["connector_setup"]["health_status"] == "healthy"
    assert output["connector_setup"]["readiness_status"] == "ready"
    assert output["connector_setup"]["readiness_blockers"] == []
    assert output["connector_setup"]["last_error_code"] is None
    assert output["connector_setup"]["last_retryable"] is None
    assert output["outcome_reconciliation"]["verdict"] == "matched"
    assert output["outcome_reconciliation"]["connector_error_code"] is None
    assert output["launch_readiness"]["proof_mode"] == "preflight"
    assert output["launch_readiness"]["real_customer_proof_candidate"] is False
    assert output["proof"] == {
        "connector_configured": True,
        "connector_health_verified": True,
        "real_connector_ready": True,
        "matched_outcome_shown": True,
        "secrets_redacted": True,
    }
    assert output["handoff"]["sandbox_test_endpoint"] == (
        "/v1/integrations/system-of-record/ledger-refund/test"
    )
    assert output["handoff"]["connector_config_template"] == (
        "demos/design-partner-install-kit/ledger_refund_connector_config.example.json"
    )
    assert "--scenario refund" in output["next_full_proof_command"]
    assert [call[0] for call in calls] == ["get", "put", "post", "get"]
    assert "ledger-live-token-secret" not in json.dumps(output)
    assert "ledger-live-token-secret" not in summary_path.read_text(encoding="utf-8")


def test_design_partner_live_preflight_can_use_saved_connector_without_partner_secret(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    module = _load_script()
    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *, base_url, timeout):
            assert base_url == "https://api.zroky.com"
            assert timeout == 10.0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def post(self, path, headers=None, json=None):
            calls.append(("post", path, headers, json))
            assert path == "/v1/outcomes/reconciliation/ledger-refund/saved"
            assert headers["x-api-key"] == "zroky-live-key"
            assert "connector" not in json
            assert json["refund_id"] == "RF-SAVED-1"
            assert json["runtime_policy_decision_id"] is None
            assert json["metadata"]["proof_mode"] == "preflight"
            assert json["metadata"]["real_customer_proof_candidate"] is False
            return FakeResponse(
                201,
                {
                    "id": "rec-saved-preflight-1",
                    "project_id": "proj_live",
                    "call_id": "call_saved",
                    "trace_id": "trace_saved",
                    "runtime_policy_decision_id": None,
                    "action_type": "refund",
                    "connector_type": "ledger_refund_api",
                    "system_ref": "ledger:RF-SAVED-1",
                    "verdict": "matched",
                    "reason": "all_compared_fields_matched",
                    "amount_usd": 42.5,
                    "currency": "USD",
                    "claimed": {},
                    "actual": {},
                    "comparison": {},
                    "idempotency_key": "saved_ledger_refund:call_saved:RF-SAVED-1",
                    "metadata": {
                        "source": "saved_connector_runtime",
                        "proof_mode": "preflight",
                        "real_customer_proof_candidate": False,
                        "match_fields": ["refund_id", "amount_usd", "currency", "status"],
                        "connector": {
                            "connector_type": "ledger_refund_api",
                            "request_url": "https://ledger.partner.example/api/refunds/RF-SAVED-1",
                            "http_status": 200,
                            "attempts": 1,
                            "retry_count": 0,
                            "max_attempts": 2,
                            "timeout_seconds": 10.0,
                            "retryable": False,
                        },
                    },
                    "checked_at": "2026-06-21T12:00:00Z",
                    "created_at": "2026-06-21T12:00:00Z",
                },
            )

    import httpx

    monkeypatch.setattr(httpx, "Client", FakeClient)
    summary_path = tmp_path / "saved-preflight-summary.json"

    assert module.main(
        [
            "--scenario",
            "refund",
            "--preflight-only",
            "--use-saved-connector",
            "--api-base-url",
            "https://api.zroky.com",
            "--api-key",
            "zroky-live-key",
            "--refund-id",
            "RF-SAVED-1",
            "--json",
            "--write-summary",
            str(summary_path),
        ]
    ) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "live_preflight"
    assert output["connector_setup"]["config_saved"] is True
    assert output["connector_setup"]["test_source"] == "saved_connector_runtime"
    assert output["connector_setup"]["health_status"] == "healthy"
    assert output["connector_setup"]["readiness_status"] == "ready"
    assert output["connector_setup"]["readiness_blockers"] == []
    assert output["launch_readiness"]["proof_mode"] == "preflight"
    assert output["launch_readiness"]["real_customer_proof_candidate"] is False
    assert output["handoff"]["sandbox_test_endpoint"] == (
        "/v1/outcomes/reconciliation/ledger-refund/saved"
    )
    assert output["proof"]["connector_configured"] is True
    assert output["proof"]["connector_health_verified"] is True
    assert output["proof"]["real_connector_ready"] is True
    assert output["proof"]["secrets_redacted"] is True
    assert "--use-saved-connector" in output["next_full_proof_command"]
    assert "--write-evidence artifacts/design-partner-refund-saved-live-evidence.json" in (
        output["next_full_proof_command"]
    )
    assert [call[0] for call in calls] == ["post"]
    assert "ledger-live-token-secret" not in json.dumps(output)
    assert "ledger-live-token-secret" not in summary_path.read_text(encoding="utf-8")


def test_design_partner_live_full_proof_can_use_saved_connector_with_evidence_hash(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    module = _load_script()
    calls = []
    evidence_hash = "a" * 64

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    runtime_decision = {
        "id": "decision_saved_live_1",
        "project_id": "proj_live",
        "call_id": "dp-call-refund-1001",
        "trace_id": "dp-trace-refund-1001",
        "agent_name": "refund-ops-agent",
        "decision": "block",
        "status": "blocked",
        "allowed": False,
        "requires_approval": False,
        "reasons": [{"code": "unsafe_refund_action"}],
    }
    reconciliation = {
        "id": "rec-saved-live-1",
        "project_id": "proj_live",
        "call_id": "dp-call-refund-1001",
        "trace_id": "dp-trace-refund-1001",
        "runtime_policy_decision_id": "decision_saved_live_1",
        "action_type": "refund",
        "connector_type": "ledger_refund_api",
        "system_ref": "ledger:RF-SAVED-1",
        "verdict": "matched",
        "reason": "all_compared_fields_matched",
        "amount_usd": 42.5,
        "currency": "USD",
        "claimed": {
            "refund_id": "RF-SAVED-1",
            "amount_usd": 42.5,
            "currency": "USD",
            "status": "posted",
        },
        "actual": {
            "refund_id": "RF-SAVED-1",
            "amount_usd": 42.5,
            "currency": "USD",
            "status": "posted",
        },
        "comparison": {
            "compared_fields": [
                {
                    "field": "refund_id",
                    "claimed": "RF-SAVED-1",
                    "actual": "RF-SAVED-1",
                    "matched": True,
                }
            ],
            "mismatches": [],
        },
        "idempotency_key": "saved_ledger_refund:decision_saved_live_1:RF-SAVED-1",
        "metadata": {
            "source": "saved_connector_runtime",
            "proof_mode": "live_customer",
            "real_customer_proof_candidate": True,
            "match_fields": ["refund_id", "amount_usd", "currency", "status"],
            "connector": {
                "connector_type": "ledger_refund_api",
                "adapter": "https_json_record",
                "request_url": "https://ledger.partner.example/api/refunds/RF-SAVED-1",
                "http_status": 200,
                "attempts": 1,
                "retry_count": 0,
                "max_attempts": 2,
                "timeout_seconds": 10.0,
                "retryable": False,
            },
        },
        "checked_at": "2026-06-21T12:00:00Z",
        "created_at": "2026-06-21T12:00:00Z",
    }
    evidence_pack = {
        "decision_id": "decision_saved_live_1",
        "verification_status": "pass",
        "evidence_hash": evidence_hash,
        "hash_algorithm": "sha256",
        "call": {"id": "dp-call-refund-1001"},
        "outcome_reconciliation": [reconciliation],
        "audit_log": [{"id": "audit-saved-live-1"}],
    }
    owner_launch_readiness = {
        "generated_at": "2026-06-21T12:02:00Z",
        "overall_status": "blocked",
        "paid_launch_allowed": False,
        "hard_blockers": ["durable_ci_gate:ci_gate_run_missing"],
        "gates": [
            {
                "code": "real_customer_proof",
                "title": "Real Customer Proof",
                "status": "pass",
                "summary": "Real pilot proof is present.",
                "blockers": [],
                "evidence": [
                    {"label": "candidate_matched_outcomes_7d", "value": 1},
                    {"label": "real_customer_matched_outcomes_7d", "value": 1},
                    {"label": "demo_or_synthetic_outcomes_7d", "value": 0},
                ],
                "verification_commands": [],
            }
        ],
        "verification_commands": [],
    }

    class FakeClient:
        def __init__(self, *, base_url, timeout):
            assert base_url == "https://api.zroky.com"
            assert timeout == 10.0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def post(self, path, headers=None, json=None):
            calls.append(("post", path, headers, json))
            assert headers["x-api-key"] == "zroky-live-key"
            if path == "/v1/runtime-policy/check":
                assert json["call_id"] == "dp-call-refund-1001"
                assert json["tool_args"]["refund_id"] == "RF-SAVED-1"
                assert json["metadata"]["proof_mode"] == "live_customer"
                return FakeResponse(200, runtime_decision)
            assert path == "/v1/outcomes/reconciliation/ledger-refund/saved"
            assert "connector" not in json
            assert json["refund_id"] == "RF-SAVED-1"
            assert json["runtime_policy_decision_id"] == "decision_saved_live_1"
            assert json["metadata"]["proof_mode"] == "live_customer"
            assert json["metadata"]["real_customer_proof_candidate"] is True
            return FakeResponse(201, reconciliation)

        def get(self, path, headers=None):
            calls.append(("get", path, headers, None))
            if path == "/v1/owner/launch-readiness":
                assert headers == {"x-zroky-admin-token": "owner-live-token"}
                return FakeResponse(200, owner_launch_readiness)
            assert headers["x-api-key"] == "zroky-live-key"
            assert path == "/v1/runtime-policy/decisions/decision_saved_live_1/evidence"
            return FakeResponse(200, evidence_pack)

    import httpx

    monkeypatch.setattr(httpx, "Client", FakeClient)
    summary_path = tmp_path / "saved-live-summary.json"
    evidence_path = tmp_path / "saved-live-evidence.json"

    assert module.main(
        [
            "--scenario",
            "refund",
            "--use-saved-connector",
            "--api-base-url",
            "https://api.zroky.com",
            "--api-key",
            "zroky-live-key",
            "--verify-owner-launch-readiness",
            "--owner-admin-token",
            "owner-live-token",
            "--refund-id",
            "RF-SAVED-1",
            "--json",
            "--write-summary",
            str(summary_path),
            "--write-evidence",
            str(evidence_path),
        ]
    ) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "live"
    assert output["runtime_policy"]["allowed"] is False
    assert output["connector_setup"]["test_endpoint"] == (
        "/v1/outcomes/reconciliation/ledger-refund/saved"
    )
    assert output["connector_setup"]["test_source"] == "saved_connector_runtime"
    assert output["connector_setup"]["readiness_contract"]["system_of_record"] == (
        "ledger_refund"
    )
    assert output["connector_setup"]["health_status"] == "healthy"
    assert output["connector_setup"]["readiness_status"] == "ready"
    assert output["outcome_reconciliation"]["verdict"] == "matched"
    assert output["evidence_pack"]["verification_status"] == "pass"
    assert output["evidence_pack"]["evidence_hash"] == evidence_hash
    assert output["launch_readiness"]["owner_gate"] == "real_customer_proof"
    assert output["launch_readiness"]["proof_mode"] == "live_customer"
    assert output["launch_readiness"]["real_customer_proof_candidate"] is True
    assert output["launch_readiness"]["required_owner_blocker_to_clear"] == (
        "real_customer_proof:real_customer_outcome_proof_missing"
    )
    assert output["launch_readiness"]["owner_launch_readiness"] == {
        "checked": True,
        "generated_at": "2026-06-21T12:02:00Z",
        "overall_status": "blocked",
        "paid_launch_allowed": False,
        "real_customer_proof_status": "pass",
        "real_customer_matched_outcomes_7d": 1,
        "hard_blockers": ["durable_ci_gate:ci_gate_run_missing"],
    }
    assert output["proof"] == {
        "captured_call_linked": True,
        "unsafe_action_stopped": True,
        "connector_configured": True,
        "connector_health_verified": True,
        "real_connector_ready": True,
        "matched_outcome_shown": True,
        "evidence_hash_visible": True,
        "evidence_pack_passed": True,
        "secrets_redacted": True,
    }
    assert "--use-saved-connector" in output["next_saved_connector_live_command"]
    assert [call[1] for call in calls] == [
        "/v1/runtime-policy/check",
        "/v1/outcomes/reconciliation/ledger-refund/saved",
        "/v1/runtime-policy/decisions/decision_saved_live_1/evidence",
        "/v1/owner/launch-readiness",
    ]
    assert "zroky-live-key" not in json.dumps(output)
    assert "owner-live-token" not in json.dumps(output)
    assert "zroky-live-key" not in summary_path.read_text(encoding="utf-8")
    assert "owner-live-token" not in summary_path.read_text(encoding="utf-8")
    assert "zroky-live-key" not in evidence_path.read_text(encoding="utf-8")
    assert "owner-live-token" not in evidence_path.read_text(encoding="utf-8")
    assert evidence_hash in evidence_path.read_text(encoding="utf-8")


def test_design_partner_install_kit_writes_redacted_handoff_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_script()
    summary_path = tmp_path / "handoff" / "summary.json"
    evidence_path = tmp_path / "evidence" / "pack.json"

    assert module.main(
        [
            "--json",
            "--write-summary",
            str(summary_path),
            "--write-evidence",
            str(evidence_path),
        ]
    ) == 0

    capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["scenario"] == "refund_outcome_proof_v1"
    assert summary["handoff"]["customer_artifacts"][0]["flag"] == "--write-summary"
    assert summary["proof"]["secrets_redacted"] is True
    assert summary["connector_setup"]["health_status"] == "healthy"
    assert summary["connector_setup"]["last_attempts"] == 1
    assert summary["outcome_reconciliation"]["connector_attempts"] == 1
    assert len(summary["evidence_pack"]["evidence_hash"]) == 64
    assert "ledger-demo-token-not-persisted" not in json.dumps(summary)

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["schema_version"] == "runtime_policy_evidence.v1"
    assert evidence["verification_status"] == "pass"
    assert evidence["call"]["id"] == "dp-call-refund-1001"
    assert len(evidence["evidence_hash"]) == 64
    assert evidence["outcome_reconciliation"][0]["verdict"] == "matched"
    assert evidence["outcome_reconciliation"][0]["metadata"]["source"] == (
        "saved_connector_test"
    )
    assert evidence["outcome_reconciliation"][0]["metadata"]["proof_mode"] == (
        "local_demo"
    )
    assert evidence["outcome_reconciliation"][0]["metadata"][
        "real_customer_proof_candidate"
    ] is False
    assert evidence["outcome_reconciliation"][0]["metadata"]["connector"][
        "attempts"
    ] == 1
    assert "ledger-demo-token-not-persisted" not in json.dumps(evidence)


def test_design_partner_install_kit_writes_redacted_customer_record_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_script()
    summary_path = tmp_path / "handoff" / "crm-summary.json"
    evidence_path = tmp_path / "evidence" / "crm-pack.json"

    assert module.main(
        [
            "--scenario",
            "customer-record",
            "--json",
            "--write-summary",
            str(summary_path),
            "--write-evidence",
            str(evidence_path),
        ]
    ) == 0

    capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["scenario"] == "crm_customer_record_proof_v1"
    assert summary["handoff"]["customer_artifacts"][0]["flag"] == "--write-summary"
    assert summary["proof"]["secrets_redacted"] is True
    assert summary["connector_setup"]["health_status"] == "healthy"
    assert summary["connector_setup"]["last_attempts"] == 1
    assert summary["outcome_reconciliation"]["connector_attempts"] == 1
    assert len(summary["evidence_pack"]["evidence_hash"]) == 64
    assert "crm-demo-token-not-persisted" not in json.dumps(summary)

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["schema_version"] == "runtime_policy_evidence.v1"
    assert evidence["verification_status"] == "pass"
    assert evidence["call"]["id"] == "dp-call-crm-2001"
    assert len(evidence["evidence_hash"]) == 64
    assert evidence["outcome_reconciliation"][0]["verdict"] == "matched"
    assert evidence["outcome_reconciliation"][0]["metadata"]["source"] == (
        "saved_connector_test"
    )
    assert evidence["outcome_reconciliation"][0]["metadata"]["proof_mode"] == (
        "local_demo"
    )
    assert evidence["outcome_reconciliation"][0]["metadata"][
        "real_customer_proof_candidate"
    ] is False
    assert evidence["outcome_reconciliation"][0]["metadata"]["connector"][
        "attempts"
    ] == 1
    assert "crm-demo-token-not-persisted" not in json.dumps(evidence)
