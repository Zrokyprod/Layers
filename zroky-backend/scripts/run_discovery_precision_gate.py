#!/usr/bin/env python3
"""Run the Discovery real-trace precision gate in one command.

This orchestrates the existing read-only trace exporter and offline harness:
export calls -> run harness -> write surfaced-finding label template -> enforce
the configured precision gate when requested.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

DEFAULT_OUT_DIR = Path("artifacts/discovery_precision_gate")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--traces",
        action="append",
        type=Path,
        default=[],
        help="Existing harness JSONL trace file. Repeatable. Skips DB export.",
    )
    parser.add_argument(
        "--database-url",
        help="SQLAlchemy DB URL for export. Defaults to Settings.DATABASE_URL.",
    )
    parser.add_argument(
        "--project-id",
        help="Project/tenant id to export when --traces is not provided.",
    )
    parser.add_argument("--agent-name", help="Optional agent_name filter for export.")
    parser.add_argument("--since", help="Inclusive export lower bound, ISO-8601.")
    parser.add_argument("--until", help="Exclusive export upper bound, ISO-8601.")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument(
        "--include-non-production",
        action="store_true",
        help="Include calls where is_production=false during export.",
    )
    parser.add_argument(
        "--privacy-mode",
        choices=("shape-only", "masked"),
        default="shape-only",
    )
    parser.add_argument("--min-rows", type=int, default=1)
    parser.add_argument("--manual-labels", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--precision-threshold", type=float, default=0.90)
    parser.add_argument("--min-scored-traces", type=int, default=200)
    parser.add_argument("--min-labelled-surfaced", type=int, default=1)
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="Return non-zero when the harness precision gate fails.",
    )
    return parser.parse_args(argv)


def build_export_argv(args: argparse.Namespace, *, traces_path: Path, summary_path: Path) -> list[str]:
    export_args = [
        "--out",
        str(traces_path),
        "--summary-out",
        str(summary_path),
        "--limit",
        str(max(1, int(args.limit))),
        "--privacy-mode",
        args.privacy_mode,
        "--min-rows",
        str(max(0, int(args.min_rows))),
    ]
    if args.database_url:
        export_args.extend(["--database-url", args.database_url])
    if args.project_id:
        export_args.extend(["--project-id", args.project_id])
    if args.agent_name:
        export_args.extend(["--agent-name", args.agent_name])
    if args.since:
        export_args.extend(["--since", args.since])
    if args.until:
        export_args.extend(["--until", args.until])
    if args.include_non_production:
        export_args.append("--include-non-production")
    return export_args


def build_harness_argv(
    args: argparse.Namespace,
    *,
    trace_paths: Sequence[Path],
    harness_dir: Path,
    label_template_path: Path,
) -> list[str]:
    harness_args: list[str] = []
    for path in trace_paths:
        harness_args.extend(["--traces", str(path)])
    if args.manual_labels:
        harness_args.extend(["--manual-labels", str(args.manual_labels)])
    harness_args.extend(
        [
            "--out-dir",
            str(harness_dir),
            "--write-label-template",
            str(label_template_path),
            "--precision-threshold",
            str(min(1.0, max(0.0, float(args.precision_threshold)))),
            "--min-scored-traces",
            str(max(0, int(args.min_scored_traces))),
            "--min-labelled-surfaced",
            str(max(0, int(args.min_labelled_surfaced))),
        ]
    )
    if args.fail_on_gate:
        harness_args.append("--fail-on-gate")
    return harness_args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    trace_paths = list(args.traces)

    if not trace_paths:
        if not args.project_id:
            print(
                "Pass --traces or provide --project-id for scoped DB export.",
                file=sys.stderr,
            )
            return 2
        exporter = _load_module(
            "export_discovery_traces",
            _SCRIPT_DIR / "export_discovery_traces.py",
        )
        traces_path = args.out_dir / "traces.jsonl"
        summary_path = args.out_dir / "traces.summary.json"
        export_code = exporter.main(
            build_export_argv(args, traces_path=traces_path, summary_path=summary_path)
        )
        if export_code != 0:
            return int(export_code)
        trace_paths = [traces_path]

    harness = _load_module("discovery_harness", _SCRIPT_DIR / "discovery_harness.py")
    harness_dir = args.out_dir / "harness"
    label_template_path = args.out_dir / "labels_template.csv"
    harness_code = harness.main(
        build_harness_argv(
            args,
            trace_paths=trace_paths,
            harness_dir=harness_dir,
            label_template_path=label_template_path,
        )
    )
    _write_manifest(
        args.out_dir / "precision_gate_manifest.json",
        trace_paths=trace_paths,
        harness_dir=harness_dir,
        label_template_path=label_template_path,
        manual_labels=args.manual_labels,
        exit_code=int(harness_code),
    )
    return int(harness_code)


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_manifest(
    path: Path,
    *,
    trace_paths: Sequence[Path],
    harness_dir: Path,
    label_template_path: Path,
    manual_labels: Path | None,
    exit_code: int,
) -> None:
    manifest = {
        "trace_paths": [str(path) for path in trace_paths],
        "harness_report": str(harness_dir / "discovery_harness_report.json"),
        "harness_findings_csv": str(harness_dir / "discovery_harness_findings.csv"),
        "label_template": str(label_template_path),
        "manual_labels": str(manual_labels) if manual_labels else None,
        "exit_code": exit_code,
    }
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote precision gate manifest: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
