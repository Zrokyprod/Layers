from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "verify_design_partner_owner_proof_artifact.py"
VALID_HASH = "a" * 64


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "verify_design_partner_owner_proof_artifact", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _summary() -> dict:
    return {
        "mode": "live",
        "project_id": "proj_partner_001",
        "scenario": "refund_outcome_proof_v1",
        "call_id": "call_live_001",
        "trace_id": "trace_live_001",
        "runtime_policy": {
            "decision_id": "rpd_live_001",
            "allowed": False,
        },
        "outcome_reconciliation": {
            "verdict": "matched",
            "connector_request_url": "https://ledger.partner.test/api/refunds/RF-1001",
            "connector_http_status": 200,
            "connector_error": None,
            "connector_retryable": False,
            "system_ref": "ledger:RF-1001",
        },
        "connector_setup": {
            "connected": True,
            "config_saved": True,
            "health_status": "healthy",
            "last_verdict": "matched",
            "readiness_status": "ready",
            "secrets_redacted": True,
        },
        "evidence_pack": {
            "decision_id": "rpd_live_001",
            "verification_status": "pass",
            "evidence_hash": VALID_HASH,
            "hash_algorithm": "sha256",
            "outcome_count": 1,
            "audit_event_count": 1,
        },
        "launch_readiness": {
            "owner_gate": "real_customer_proof",
            "proof_mode": "live_customer",
            "real_customer_proof_candidate": True,
            "owner_launch_readiness": {
                "checked": True,
                "real_customer_proof_status": "pass",
                "real_customer_matched_outcomes_7d": 1,
                "hard_blockers": [],
            },
        },
        "proof": {
            "captured_call_linked": True,
            "unsafe_action_stopped": True,
            "connector_configured": True,
            "connector_health_verified": True,
            "real_connector_ready": True,
            "matched_outcome_shown": True,
            "evidence_hash_visible": True,
            "evidence_pack_passed": True,
            "secrets_redacted": True,
        },
    }


def _evidence() -> dict:
    return {
        "decision_id": "rpd_live_001",
        "project_id": "proj_partner_001",
        "verification_status": "pass",
        "evidence_hash": VALID_HASH,
        "hash_algorithm": "sha256",
        "call": {"id": "call_live_001"},
        "audit_log": [{"event": "owner_proof_checked"}],
        "outcome_reconciliation": [{"verdict": "matched"}],
    }


def test_owner_proof_artifact_accepts_live_customer_summary_and_evidence(
    tmp_path: Path, capsys
) -> None:
    module = _load_script()
    summary_path = tmp_path / "summary.json"
    evidence_path = tmp_path / "evidence.json"
    summary_path.write_text(json.dumps(_summary()), encoding="utf-8")
    evidence_path.write_text(json.dumps(_evidence()), encoding="utf-8")

    assert module.main(
        ["--summary", str(summary_path), "--evidence", str(evidence_path)]
    ) == 0

    output = capsys.readouterr().out
    assert "[owner-proof] passed" in output
    assert "project_id=proj_partner_001" in output
    assert f"evidence_hash={VALID_HASH}" in output


def test_owner_proof_artifact_rejects_local_or_unverified_summary(
    tmp_path: Path, capsys
) -> None:
    module = _load_script()
    summary = _summary()
    summary["mode"] = "local_demo"
    summary["launch_readiness"]["proof_mode"] = "local_demo"
    summary["launch_readiness"]["real_customer_proof_candidate"] = False
    summary["launch_readiness"]["owner_launch_readiness"][
        "real_customer_proof_status"
    ] = "not_verified"
    summary["launch_readiness"]["owner_launch_readiness"]["hard_blockers"] = [
        module.OWNER_PROOF_BLOCKER
    ]
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    assert module.main(["--summary", str(summary_path)]) == 1

    error_output = capsys.readouterr().err
    assert "summary.mode must be live" in error_output
    assert "real_customer_proof_status must be pass" in error_output
    assert module.OWNER_PROOF_BLOCKER in error_output


def test_owner_proof_artifact_rejects_tampered_evidence_hash(
    tmp_path: Path, capsys
) -> None:
    module = _load_script()
    summary_path = tmp_path / "summary.json"
    evidence_path = tmp_path / "evidence.json"
    evidence = _evidence()
    evidence["evidence_hash"] = "b" * 64
    summary_path.write_text(json.dumps(_summary()), encoding="utf-8")
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    assert module.main(
        ["--summary", str(summary_path), "--evidence", str(evidence_path)]
    ) == 1

    assert "evidence_hash must match summary evidence_hash" in capsys.readouterr().err


def test_owner_proof_artifact_rejects_missing_required_proof_flag(
    tmp_path: Path, capsys
) -> None:
    module = _load_script()
    summary = _summary()
    del summary["proof"]["real_connector_ready"]
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    assert module.main(["--summary", str(summary_path)]) == 1

    assert "proof object missing required keys: real_connector_ready" in capsys.readouterr().err


def test_owner_proof_artifact_rejects_demo_connector_url(
    tmp_path: Path, capsys
) -> None:
    module = _load_script()
    summary = _summary()
    summary["outcome_reconciliation"][
        "connector_request_url"
    ] = "https://ledger.example.com/api/refunds/RF-1001"
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    assert module.main(["--summary", str(summary_path)]) == 1

    error_output = capsys.readouterr().err
    assert "connector_request_url must be a real https URL" in error_output
