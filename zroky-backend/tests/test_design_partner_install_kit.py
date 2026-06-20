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
    assert fixture["ledger"]["bearer_token"] not in json.dumps(
        fixture["expected"], sort_keys=True
    )


def test_design_partner_install_kit_local_demo_outputs_auditable_proof(
    capsys,
) -> None:
    module = _load_script()

    assert module.main(["--json"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "local_demo"
    assert output["call_id"] == "dp-call-refund-1001"
    assert output["trace_id"] == "dp-trace-refund-1001"
    assert output["runtime_policy"]["allowed"] is False
    assert output["runtime_policy"]["status"] in {"blocked", "pending_approval"}
    assert output["outcome_reconciliation"]["verdict"] == "matched"
    assert output["outcome_reconciliation"]["connector_type"] == "ledger_refund_api"
    assert output["evidence_pack"]["verification_status"] == "pass"
    assert len(output["evidence_pack"]["evidence_hash"]) == 64
    assert output["proof"] == {
        "captured_call_linked": True,
        "unsafe_action_stopped": True,
        "matched_outcome_shown": True,
        "evidence_hash_visible": True,
        "evidence_pack_passed": True,
        "secrets_redacted": True,
    }
    assert "ledger-demo-token-not-persisted" not in json.dumps(output)


def test_design_partner_install_kit_writes_redacted_evidence_json(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_script()
    evidence_path = tmp_path / "evidence" / "pack.json"

    assert module.main(["--json", "--write-evidence", str(evidence_path)]) == 0

    capsys.readouterr()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["schema_version"] == "runtime_policy_evidence.v1"
    assert evidence["verification_status"] == "pass"
    assert evidence["call"]["id"] == "dp-call-refund-1001"
    assert len(evidence["evidence_hash"]) == 64
    assert evidence["outcome_reconciliation"][0]["verdict"] == "matched"
    assert "ledger-demo-token-not-persisted" not in json.dumps(evidence)
