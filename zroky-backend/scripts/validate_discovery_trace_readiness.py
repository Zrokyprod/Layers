#!/usr/bin/env python3
"""Validate trace JSONL readiness before running the Discovery precision gate.

This is intentionally a preflight checker, not a precision gate. It proves that
an exported/pilot trace file has enough volume, time coverage, and observable
signals for the offline harness to produce meaningful baseline results.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OUTPUT_KEYS = (
    "output",
    "normalized_output",
    "output_content",
    "response",
    "completion",
)
TOOL_KEYS = (
    "tool_calls",
    "tool_calls_made",
    "tool_lifecycle_summary",
    "tool_lifecycle_summary_json",
)
OUTCOME_KEYS = ("outcome", "outcome_success", "evaluation", "eval_result")
WORKFLOW_KEYS = ("workflow_name", "workflow", "flow_name")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--traces",
        action="append",
        type=Path,
        default=[],
        help="Harness JSONL trace file. Repeatable.",
    )
    parser.add_argument("--summary-out", type=Path, help="Optional JSON summary output.")
    parser.add_argument("--min-rows", type=int, default=200)
    parser.add_argument("--min-days", type=int, default=3)
    parser.add_argument("--min-agents", type=int, default=1)
    parser.add_argument("--min-workflows", type=int, default=1)
    parser.add_argument("--min-output-signal-pct", type=float, default=0.80)
    parser.add_argument("--min-status-signal-pct", type=float, default=0.80)
    parser.add_argument("--min-tool-signal-pct", type=float, default=0.0)
    parser.add_argument("--min-outcome-signal-pct", type=float, default=0.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not args.traces:
        print("Pass at least one --traces JSONL file.", file=sys.stderr)
        return 2

    try:
        records = load_jsonl_records(args.traces)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    report = build_readiness_report(records, args=args)
    print_report(report)
    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Wrote readiness summary: {args.summary_out}")
    return 0 if report["gate"]["passed"] else 1


def load_jsonl_records(paths: Sequence[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number} invalid JSON: {exc}") from exc
                if not isinstance(row, dict):
                    raise ValueError(f"{path}:{line_number} must be a JSON object")
                records.append(row)
    return records


def build_readiness_report(
    records: Sequence[Mapping[str, Any]],
    *,
    args: argparse.Namespace,
) -> dict[str, Any]:
    total = len(records)
    projects: Counter[str] = Counter()
    agents: Counter[str] = Counter()
    workflows: Counter[str] = Counter()
    timestamps: list[datetime] = []
    output_signal = 0
    tool_signal = 0
    outcome_signal = 0
    status_signal = 0
    production = Counter()

    for row in records:
        sources = _sources(row)
        projects[_first_text(sources, "project_id", "tenant_id") or "unknown"] += 1
        agents[_first_text(sources, "agent_name", "agent") or "unknown"] += 1
        workflows[_first_text(sources, *WORKFLOW_KEYS) or "unknown"] += 1
        timestamp = _parse_time(_first_text(sources, "created_at", "timestamp"))
        if timestamp:
            timestamps.append(timestamp)
        if _has_output_signal(row, sources):
            output_signal += 1
        if _has_tool_signal(row, sources):
            tool_signal += 1
        if _has_key_with_value(sources, OUTCOME_KEYS):
            outcome_signal += 1
        if _first_text(sources, "status", "error_code", "finish_reason"):
            status_signal += 1
        production[_production_bucket(row)] += 1

    active_days = len({ts.date().isoformat() for ts in timestamps})
    first_seen = min(timestamps).isoformat() if timestamps else None
    last_seen = max(timestamps).isoformat() if timestamps else None
    span_days = (
        round((max(timestamps) - min(timestamps)).total_seconds() / 86400, 4)
        if len(timestamps) >= 2
        else 0.0
    )

    report = {
        "rows": total,
        "projects": dict(projects),
        "agents": dict(agents),
        "workflows": dict(workflows),
        "time": {
            "first_seen_at": first_seen,
            "last_seen_at": last_seen,
            "span_days": span_days,
            "active_days": active_days,
        },
        "coverage": {
            "created_at_pct": _pct(len(timestamps), total),
            "output_signal_pct": _pct(output_signal, total),
            "tool_signal_pct": _pct(tool_signal, total),
            "outcome_signal_pct": _pct(outcome_signal, total),
            "status_signal_pct": _pct(status_signal, total),
            "production_true": production["true"],
            "production_false": production["false"],
            "production_unknown": production["unknown"],
        },
    }
    report["gate"] = evaluate_readiness(report, args=args)
    return report


def evaluate_readiness(report: Mapping[str, Any], *, args: argparse.Namespace) -> dict[str, Any]:
    reasons: list[str] = []
    rows = int(report["rows"])
    active_days = int(report["time"]["active_days"])
    agent_count = len([name for name in report["agents"] if name != "unknown"])
    workflow_count = len([name for name in report["workflows"] if name != "unknown"])
    coverage = report["coverage"]

    if rows < max(0, int(args.min_rows)):
        reasons.append(f"rows {rows} < min_rows {args.min_rows}")
    if active_days < max(0, int(args.min_days)):
        reasons.append(f"active_days {active_days} < min_days {args.min_days}")
    if agent_count < max(0, int(args.min_agents)):
        reasons.append(f"known_agents {agent_count} < min_agents {args.min_agents}")
    if workflow_count < max(0, int(args.min_workflows)):
        reasons.append(
            f"known_workflows {workflow_count} < min_workflows {args.min_workflows}"
        )
    _require_pct(
        reasons,
        "output_signal_pct",
        float(coverage["output_signal_pct"]),
        float(args.min_output_signal_pct),
    )
    _require_pct(
        reasons,
        "status_signal_pct",
        float(coverage["status_signal_pct"]),
        float(args.min_status_signal_pct),
    )
    _require_pct(
        reasons,
        "tool_signal_pct",
        float(coverage["tool_signal_pct"]),
        float(args.min_tool_signal_pct),
    )
    _require_pct(
        reasons,
        "outcome_signal_pct",
        float(coverage["outcome_signal_pct"]),
        float(args.min_outcome_signal_pct),
    )

    return {
        "status": "pass" if not reasons else "fail",
        "passed": not reasons,
        "reasons": reasons,
        "thresholds": {
            "min_rows": args.min_rows,
            "min_days": args.min_days,
            "min_agents": args.min_agents,
            "min_workflows": args.min_workflows,
            "min_output_signal_pct": args.min_output_signal_pct,
            "min_status_signal_pct": args.min_status_signal_pct,
            "min_tool_signal_pct": args.min_tool_signal_pct,
            "min_outcome_signal_pct": args.min_outcome_signal_pct,
        },
    }


def print_report(report: Mapping[str, Any]) -> None:
    print("=== Discovery Trace Readiness ===")
    print(f"Rows:                         {report['rows']}")
    print(f"Projects:                     {len(report['projects'])}")
    print(f"Known agents:                 {len([k for k in report['agents'] if k != 'unknown'])}")
    print(
        "Known workflows:              "
        f"{len([k for k in report['workflows'] if k != 'unknown'])}"
    )
    print(f"Active days:                  {report['time']['active_days']}")
    coverage = report["coverage"]
    print(f"Output signal coverage:       {coverage['output_signal_pct']:.3f}")
    print(f"Tool signal coverage:         {coverage['tool_signal_pct']:.3f}")
    print(f"Outcome signal coverage:      {coverage['outcome_signal_pct']:.3f}")
    print(f"Status signal coverage:       {coverage['status_signal_pct']:.3f}")
    gate = report["gate"]
    print(f"Readiness status:             {gate['status']}")
    if gate["reasons"]:
        print("Readiness failure reasons:    " + "; ".join(gate["reasons"]))


def _sources(row: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    sources: list[Mapping[str, Any]] = [row]
    for key in ("payload_json", "metadata_json"):
        nested = _safe_json_object(row.get(key))
        if nested:
            sources.append(nested)
    return tuple(sources)


def _safe_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _first_text(sources: Sequence[Mapping[str, Any]], *keys: str) -> str | None:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value in (None, ""):
                continue
            return str(value).strip() or None
    return None


def _has_key_with_value(sources: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> bool:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value not in (None, "", [], {}):
                return True
    return False


def _has_output_signal(row: Mapping[str, Any], sources: Sequence[Mapping[str, Any]]) -> bool:
    if row.get("output_fingerprint") not in (None, ""):
        return True
    return _has_key_with_value(sources, OUTPUT_KEYS)


def _has_tool_signal(row: Mapping[str, Any], sources: Sequence[Mapping[str, Any]]) -> bool:
    if row.get("tool_lifecycle_summary_json") not in (None, ""):
        return True
    return _has_key_with_value(sources, TOOL_KEYS)


def _production_bucket(row: Mapping[str, Any]) -> str:
    if row.get("is_production") is True:
        return "true"
    if row.get("is_production") is False:
        return "false"
    return "unknown"


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _pct(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _require_pct(reasons: list[str], name: str, value: float, threshold: float) -> None:
    threshold = min(1.0, max(0.0, threshold))
    if value < threshold:
        reasons.append(f"{name} {value:.3f} < {threshold:.3f}")


if __name__ == "__main__":
    raise SystemExit(main())
