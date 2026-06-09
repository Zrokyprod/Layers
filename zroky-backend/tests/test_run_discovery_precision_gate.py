from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_runner_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_discovery_precision_gate.py"
    spec = importlib.util.spec_from_file_location("run_discovery_precision_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runner_requires_traces_or_project_id(tmp_path: Path) -> None:
    runner = _load_runner_module()

    result = runner.main(["--out-dir", str(tmp_path)])

    assert result == 2


def test_runner_builds_export_and_harness_args(tmp_path: Path) -> None:
    runner = _load_runner_module()
    args = runner.parse_args(
        [
            "--database-url",
            "sqlite:///calls.db",
            "--project-id",
            "project-1",
            "--agent-name",
            "refund-agent",
            "--since",
            "2026-06-01T00:00:00Z",
            "--include-non-production",
            "--manual-labels",
            str(tmp_path / "labels.csv"),
            "--out-dir",
            str(tmp_path),
            "--fail-on-gate",
        ]
    )

    export_args = runner.build_export_argv(
        args,
        traces_path=tmp_path / "traces.jsonl",
        summary_path=tmp_path / "traces.summary.json",
    )
    harness_args = runner.build_harness_argv(
        args,
        trace_paths=[tmp_path / "traces.jsonl"],
        harness_dir=tmp_path / "harness",
        label_template_path=tmp_path / "labels_template.csv",
    )

    assert "--database-url" in export_args
    assert "sqlite:///calls.db" in export_args
    assert "--project-id" in export_args
    assert "project-1" in export_args
    assert "--include-non-production" in export_args
    assert "--manual-labels" in harness_args
    assert str(tmp_path / "labels.csv") in harness_args
    assert "--write-label-template" in harness_args
    assert str(tmp_path / "labels_template.csv") in harness_args
    assert "--fail-on-gate" in harness_args
