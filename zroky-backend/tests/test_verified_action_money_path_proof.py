from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "run_verified_action_money_path.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_verified_action_money_path",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verified_action_stripe_money_path_generates_receipted_proof(tmp_path: Path) -> None:
    module = _load_script()
    artifact_dir = tmp_path / "artifacts"

    summary = module.run_verified_action_money_path(artifact_dir=artifact_dir)

    assert summary["mode"] == "deterministic_mock"
    assert summary["runner_status"] == "succeeded"
    assert summary["verification_status"] == "verified"
    assert summary["receipt_final_status"] == "verified"
    assert summary["receipt_signature_valid"] is True
    assert summary["protected_credential_returned"] is False
    assert summary["secrets_redacted"] is True
    assert summary["stripe_request_count"] == 1
    assert summary["source_mutation_matched_classification"] == "matched_receipt"
    assert summary["source_mutation_bypass_classification"] == "policy_bypass"
    assert summary["source_mutation_unreceipted"] == 1
    assert "execution_succeeded" in summary["timeline_event_types"]
    assert summary["timeline_event_types"][-1] == "receipt_generated"

    summary_path = artifact_dir / "verified_action_stripe_money_path_summary.json"
    receipt_path = artifact_dir / "verified_action_stripe_action_receipt.json"
    assert summary_path.exists()
    assert receipt_path.exists()

    saved_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    saved_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert saved_summary["receipt_digest"] == summary["receipt_digest"]
    assert saved_receipt["receipt_digest"] == summary["receipt_digest"]
    assert saved_receipt["receipt"]["verification"]["status"] == "verified"
    assert "sk_test_zroky_verified_action_demo" not in json.dumps(saved_receipt)
