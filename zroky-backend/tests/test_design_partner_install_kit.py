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
    assert fixture["ledger"]["bearer_token"] not in json.dumps(
        fixture["expected"], sort_keys=True
    )


def test_design_partner_handoff_guide_covers_customer_run_contract() -> None:
    guide = HANDOFF_GUIDE_PATH.read_text(encoding="utf-8")

    assert "python scripts/run_design_partner_install_kit.py --json" in guide
    assert "--write-summary artifacts/design-partner-summary.json" in guide
    assert "--write-evidence artifacts/design-partner-evidence.json" in guide
    assert "--api-base-url https://api.zroky.ai" in guide
    assert "runtime_policy.allowed" in guide
    assert "outcome_reconciliation.verdict" in guide
    assert "evidence_pack.evidence_hash" in guide
    assert "secrets_redacted" in guide
    assert "not_verified" in guide
    assert "ledger-demo-token-not-persisted" not in guide


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
    assert output["handoff"]["guide"] == "demos/design-partner-install-kit/HANDOFF.txt"
    assert output["handoff"]["package"] == "design_partner_refund_v1"
    assert set(output["handoff"]["pass_criteria"]) == set(output["proof"].keys())
    assert "--write-summary artifacts/design-partner-live-summary.json" in output[
        "next_live_command"
    ]
    assert "ledger-demo-token-not-persisted" not in json.dumps(output)


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
    assert len(summary["evidence_pack"]["evidence_hash"]) == 64
    assert "ledger-demo-token-not-persisted" not in json.dumps(summary)

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["schema_version"] == "runtime_policy_evidence.v1"
    assert evidence["verification_status"] == "pass"
    assert evidence["call"]["id"] == "dp-call-refund-1001"
    assert len(evidence["evidence_hash"]) == 64
    assert evidence["outcome_reconciliation"][0]["verdict"] == "matched"
    assert "ledger-demo-token-not-persisted" not in json.dumps(evidence)
