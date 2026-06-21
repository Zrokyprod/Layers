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


def test_design_partner_handoff_guide_covers_customer_run_contract() -> None:
    guide = HANDOFF_GUIDE_PATH.read_text(encoding="utf-8")

    assert "python scripts/run_design_partner_install_kit.py --scenario refund --json" in guide
    assert (
        "python scripts/run_design_partner_install_kit.py --scenario customer-record --json"
        in guide
    )
    assert "--write-summary artifacts/design-partner-refund-summary.json" in guide
    assert "--write-evidence artifacts/design-partner-refund-evidence.json" in guide
    assert "--write-summary artifacts/design-partner-crm-summary.json" in guide
    assert "--write-evidence artifacts/design-partner-crm-evidence.json" in guide
    assert "--api-base-url https://api.zroky.ai" in guide
    assert "--ledger-base-url https://ledger.example.com/api" in guide
    assert "--crm-base-url https://crm.example.com/api" in guide
    assert "runtime_policy.allowed" in guide
    assert "connector_setup.status_endpoint" in guide
    assert "connector_setup.config_endpoint" in guide
    assert "connector_setup.test_endpoint" in guide
    assert "connector_setup.health_status" in guide
    assert "connector_setup.last_attempts" in guide
    assert "outcome_reconciliation.verdict" in guide
    assert "outcome_reconciliation.connector_attempts" in guide
    assert "evidence_pack.evidence_hash" in guide
    assert "secrets_redacted" in guide
    assert "not_verified" in guide
    assert "ledger-demo-token-not-persisted" not in guide
    assert "crm-demo-token-not-persisted" not in guide


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
    assert output["connector_setup"]["retry_count"] == 0
    assert output["connector_setup"]["max_attempts"] == 2
    assert output["connector_setup"]["test_ok"] is True
    assert output["connector_setup"]["test_source"] == "saved_connector_test"
    assert output["connector_setup"]["secrets_redacted"] is True
    assert output["evidence_pack"]["verification_status"] == "pass"
    assert len(output["evidence_pack"]["evidence_hash"]) == 64
    assert output["proof"] == {
        "captured_call_linked": True,
        "unsafe_action_stopped": True,
        "connector_configured": True,
        "connector_health_verified": True,
        "matched_outcome_shown": True,
        "evidence_hash_visible": True,
        "evidence_pack_passed": True,
        "secrets_redacted": True,
    }
    assert output["handoff"]["guide"] == "demos/design-partner-install-kit/HANDOFF.txt"
    assert output["handoff"]["package"] == "design_partner_refund_v1"
    assert set(output["handoff"]["pass_criteria"]) == set(output["proof"].keys())
    assert output["handoff"]["customer_artifacts"][0]["default_path"] == (
        "artifacts/design-partner-refund-summary.json"
    )
    assert output["handoff"]["customer_artifacts"][1]["default_path"] == (
        "artifacts/design-partner-refund-evidence.json"
    )
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
    assert output["connector_setup"]["test_ok"] is True
    assert output["connector_setup"]["test_source"] == "saved_connector_test"
    assert output["connector_setup"]["secrets_redacted"] is True
    assert output["evidence_pack"]["verification_status"] == "pass"
    assert len(output["evidence_pack"]["evidence_hash"]) == 64
    assert output["proof"] == {
        "captured_call_linked": True,
        "unsafe_action_stopped": True,
        "connector_configured": True,
        "connector_health_verified": True,
        "matched_outcome_shown": True,
        "evidence_hash_visible": True,
        "evidence_pack_passed": True,
        "secrets_redacted": True,
    }
    assert output["handoff"]["package"] == "design_partner_crm_v1"
    assert output["handoff"]["customer_artifacts"][0]["default_path"] == (
        "artifacts/design-partner-crm-summary.json"
    )
    assert output["handoff"]["customer_artifacts"][1]["default_path"] == (
        "artifacts/design-partner-crm-evidence.json"
    )
    assert "--scenario customer-record" in output["next_live_command"]
    assert "crm-demo-token-not-persisted" not in json.dumps(output)


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
    assert evidence["outcome_reconciliation"][0]["metadata"]["connector"][
        "attempts"
    ] == 1
    assert "crm-demo-token-not-persisted" not in json.dumps(evidence)
