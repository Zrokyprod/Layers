from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "verify_paid_launch_readiness.ps1"


def test_paid_launch_readiness_script_has_fail_closed_final_phase() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert '"final"' in script
    assert '$RunFinalLaunch = $Phase -contains "final"' in script
    assert '$RunAllPhases = ($Phase -contains "all") -or $RunFinalLaunch' in script
    assert "-Phase all/final cannot be combined with narrower phases." in script
    assert "function Resolve-OwnerProofArtifactPath" in script
    assert "$OwnerProofSummary = Resolve-OwnerProofArtifactPath -PathText $OwnerProofSummary" in script
    assert "$OwnerProofEvidence = Resolve-OwnerProofArtifactPath -PathText $OwnerProofEvidence" in script
    assert script.index("$RootDir = Split-Path -Parent $ScriptDir") < script.index(
        "$OwnerProofSummary = Resolve-OwnerProofArtifactPath -PathText $OwnerProofSummary"
    )
    assert script.index(
        "$OwnerProofEvidence = Resolve-OwnerProofArtifactPath -PathText $OwnerProofEvidence"
    ) < script.index("if ($RunFinalLaunch)")
    assert (
        "Final paid launch requires -OwnerProofSummary and -OwnerProofEvidence"
        in script
    )
    assert "Final paid launch owner proof summary does not exist" in script
    assert "Final paid launch owner proof evidence does not exist" in script
    assert (
        "$RequireOwnerProofArtifact = $RunFinalLaunch -or $RequireOwnerProof.IsPresent"
        in script
    )
    assert "Final paid launch requires both owner proof artifacts" in script
    assert "Owner proof summary and evidence must be supplied together." in script
    assert "Owner proof summary does not exist" in script
    assert "Owner proof evidence does not exist" in script
    assert "--evidence" in script
    assert "Verified Action Stripe money-path proof" in script
    assert "scripts/run_verified_action_money_path.py" in script
    assert (
        "Final paid launch readiness verification passed with live owner proof."
        in script
    )
