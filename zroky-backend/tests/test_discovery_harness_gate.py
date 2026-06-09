from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


def _load_harness_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "discovery_harness.py"
    spec = importlib.util.spec_from_file_location("discovery_harness", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _report(*, precision: float | None, labelled: int, scored: int = 100) -> dict:
    real = int(round((precision or 0.0) * labelled))
    return {
        "baseline_keys": {
            "total": 1,
            "active": 1,
            "learning": 0,
            "suspect": 0,
            "low_specificity": 0,
        },
        "traces_scored": scored,
        "findings": {"watching": 0, "surfaced": labelled, "dismissed": 0, "items": []},
        "precision": {
            "surfaced_real": real,
            "surfaced_labelled_total": labelled,
            "value": precision,
            "manual_labels_required": precision is None,
        },
    }


def test_gate_passes_with_enough_labelled_precision_and_volume() -> None:
    harness = _load_harness_module()

    gate = harness.evaluate_gate(
        _report(precision=0.95, labelled=20, scored=250),
        harness.GateConfig(
            precision_threshold=0.90,
            min_scored_traces=200,
            min_labelled_surfaced=10,
        ),
    )

    assert gate["passed"] is True
    assert gate["status"] == "pass"
    assert gate["reasons"] == []


def test_gate_fails_without_manual_labels_or_active_baseline() -> None:
    harness = _load_harness_module()
    report = _report(precision=None, labelled=0, scored=0)
    report["baseline_keys"]["active"] = 0

    gate = harness.evaluate_gate(
        report,
        harness.GateConfig(
            precision_threshold=0.90,
            min_scored_traces=200,
            min_labelled_surfaced=5,
        ),
    )

    assert gate["passed"] is False
    assert "no active baseline" in gate["reasons"]
    assert "manual labels required" in gate["reasons"]
    assert any(reason.startswith("traces_scored 0 <") for reason in gate["reasons"])
    assert any(
        reason.startswith("labelled surfaced findings 0 <")
        for reason in gate["reasons"]
    )


def test_manual_labels_accept_aliases_and_reject_unknown(
    tmp_path: Path,
) -> None:
    harness = _load_harness_module()
    labels_path = tmp_path / "labels.csv"
    with labels_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["finding_id", "signature", "manual_label"],
        )
        writer.writeheader()
        writer.writerow(
            {"finding_id": "disc_1", "signature": "sig_1", "manual_label": "TP"}
        )
        writer.writerow(
            {"finding_id": "disc_2", "signature": "sig_2", "manual_label": "fp"}
        )

    labels = harness.read_manual_labels(labels_path)

    assert labels["disc_1"] == "real"
    assert labels["sig_1"] == "real"
    assert labels["disc_2"] == "not_a_failure"
    assert labels["sig_2"] == "not_a_failure"

    bad_path = tmp_path / "bad_labels.csv"
    bad_path.write_text(
        "finding_id,signature,manual_label\n"
        "disc_bad,sig_bad,maybe\n",
        encoding="utf-8",
    )

    assert harness.main(["--demo", "--manual-labels", str(bad_path), "--no-write"]) == 2


def test_label_template_writes_only_surfaced_findings(tmp_path: Path) -> None:
    harness = _load_harness_module()
    template_path = tmp_path / "labels.csv"
    report = {
        "findings": {
            "items": [
                {"tier": "watching", "finding_id": "disc_watch"},
                {
                    "tier": "surfaced",
                    "finding_id": "disc_surface",
                    "signature": "sig_surface",
                    "reason": "critical tool missing against baseline",
                    "confidence": 0.91,
                    "anomaly_score": 4.2,
                    "occurrence_count": 3,
                    "corroboration": ["missing_critical_tool", "outcome_failure"],
                    "sample_call_ids": ["call_1", "call_2"],
                },
            ],
        },
    }

    harness.write_label_template(report, template_path)

    with template_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["finding_id"] == "disc_surface"
    assert rows[0]["signature"] == "sig_surface"
    assert rows[0]["manual_label"] == ""
    assert rows[0]["reviewer_notes"] == ""
    assert json.loads(rows[0]["sample_call_ids"]) == ["call_1", "call_2"]

    rows[0]["manual_label"] = "real"
    with template_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    labels = harness.read_manual_labels(template_path)
    assert labels["disc_surface"] == "real"
    assert labels["sig_surface"] == "real"


def test_fail_on_gate_returns_nonzero_without_labels() -> None:
    harness = _load_harness_module()

    result = harness.main(
        [
            "--demo",
            "--no-write",
            "--min-scored-traces",
            "1",
            "--min-labelled-surfaced",
            "1",
            "--fail-on-gate",
        ]
    )

    assert result == 1
