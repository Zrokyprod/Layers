#!/usr/bin/env python3
"""Generate a deterministic mixed dataset for the Discover harness.

This is synthetic mechanics data, not a substitute for real-trace precision.
It creates:
  - a warm production-like workflow with normal traces,
  - a low-volume workflow that should stay learning,
  - injected known failures for recall/precision mechanics.

Output files are JSONL so they can be passed directly to discovery_harness.py.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


PROJECT_ID = "synthetic_discovery_project"
PRIMARY_AGENT = "refund-support-agent"
PRIMARY_WORKFLOW = "refund_status_check"
LOW_VOLUME_AGENT = "billing-agent"
LOW_VOLUME_WORKFLOW = "invoice_question"


@dataclass(frozen=True)
class DatasetCounts:
    normal_primary: int
    normal_low_volume: int
    missing_tool_failures: int
    schema_break_failures: int
    outcome_mismatch_failures: int
    latency_cost_failures: int


DEFAULT_COUNTS = DatasetCounts(
    normal_primary=360,
    normal_low_volume=50,
    missing_tool_failures=12,
    schema_break_failures=12,
    outcome_mismatch_failures=12,
    latency_cost_failures=8,
)


def _iso(base: datetime, *, index: int, minutes: int = 11) -> str:
    return (base + timedelta(minutes=index * minutes)).isoformat().replace("+00:00", "Z")


def _normal_refund_trace(index: int, created_at: str, rng: random.Random) -> dict[str, Any]:
    eta = 2 + (index % 4)
    status = ["pending", "processing", "approved"][index % 3]
    latency = 590 + rng.randint(-55, 70)
    cost = round(0.0020 + rng.random() * 0.00045, 7)
    output = {
        "status": status,
        "eta_days": eta,
        "message": f"Refund is {status}; expected update in {eta} days.",
        "next_step": "wait_for_processor_update",
    }
    return {
        "call_id": f"synthetic_normal_refund_{index:04d}",
        "project_id": PROJECT_ID,
        "agent_name": PRIMARY_AGENT,
        "workflow_name": PRIMARY_WORKFLOW,
        "created_at": created_at,
        "status": "completed",
        "latency_ms": latency,
        "cost_usd": cost,
        "tool_calls": [
            {"name": "lookup_order"},
            {"name": "get_refund_status"},
            {"name": "render_refund_answer"},
        ],
        "output_content": json.dumps(output, separators=(",", ":")),
        "finish_reason": "stop",
        "outcome": {"success": True},
        "metadata": {"dataset": "synthetic_discovery_mixed", "ground_truth": "normal"},
    }


def _low_volume_trace(index: int, created_at: str, rng: random.Random) -> dict[str, Any]:
    output = {
        "answer": "Invoice email was sent to the billing contact.",
        "action": "resend_invoice" if index % 7 == 0 else "explain_invoice_status",
    }
    return {
        "call_id": f"synthetic_normal_low_volume_{index:04d}",
        "project_id": PROJECT_ID,
        "agent_name": LOW_VOLUME_AGENT,
        "workflow_name": LOW_VOLUME_WORKFLOW,
        "created_at": created_at,
        "status": "completed",
        "latency_ms": 430 + rng.randint(-45, 45),
        "cost_usd": round(0.0014 + rng.random() * 0.0003, 7),
        "tool_calls": [{"name": "lookup_invoice"}],
        "output_content": json.dumps(output, separators=(",", ":")),
        "finish_reason": "stop",
        "outcome": {"success": True},
        "metadata": {"dataset": "synthetic_discovery_mixed", "ground_truth": "normal"},
    }


def _missing_tool_failure(index: int, created_at: str) -> dict[str, Any]:
    return {
        "call_id": f"synthetic_fail_missing_tool_{index:04d}",
        "project_id": PROJECT_ID,
        "agent_name": PRIMARY_AGENT,
        "workflow_name": PRIMARY_WORKFLOW,
        "created_at": created_at,
        "status": "completed",
        "latency_ms": 380,
        "cost_usd": 0.0012,
        "tool_calls": [{"name": "lookup_order"}],
        "output_content": "Your refund looks complete.",
        "finish_reason": "stop",
        "injected_failure_type": "missing_critical_tool",
        "metadata": {"dataset": "synthetic_discovery_mixed", "ground_truth": "failure"},
    }


def _schema_break_failure(index: int, created_at: str) -> dict[str, Any]:
    return {
        "call_id": f"synthetic_fail_schema_break_{index:04d}",
        "project_id": PROJECT_ID,
        "agent_name": PRIMARY_AGENT,
        "workflow_name": PRIMARY_WORKFLOW,
        "created_at": created_at,
        "status": "completed",
        "latency_ms": 620,
        "cost_usd": 0.0022,
        "tool_calls": [
            {"name": "lookup_order"},
            {"name": "get_refund_status"},
            {"name": "render_refund_answer"},
        ],
        "output_content": json.dumps({"unexpected": "plain fallback"}),
        "finish_reason": "stop",
        "injected_failure_type": "schema_break",
        "metadata": {"dataset": "synthetic_discovery_mixed", "ground_truth": "failure"},
    }


def _outcome_mismatch_failure(index: int, created_at: str) -> dict[str, Any]:
    output = {
        "status": "pending",
        "eta_days": 3,
        "message": "Refund is pending; expected update in 3 days.",
        "next_step": "wait_for_processor_update",
    }
    return {
        "call_id": f"synthetic_fail_outcome_mismatch_{index:04d}",
        "project_id": PROJECT_ID,
        "agent_name": PRIMARY_AGENT,
        "workflow_name": PRIMARY_WORKFLOW,
        "created_at": created_at,
        "status": "completed",
        "latency_ms": 640,
        "cost_usd": 0.0022,
        "tool_calls": [
            {"name": "lookup_order"},
            {"name": "get_refund_status"},
            {"name": "render_refund_answer"},
        ],
        "output_content": json.dumps(output, separators=(",", ":")),
        "finish_reason": "stop",
        "outcome": {"success": False},
        "injected_failure_type": "outcome_mismatch",
        "metadata": {"dataset": "synthetic_discovery_mixed", "ground_truth": "failure"},
    }


def _latency_cost_failure(index: int, created_at: str) -> dict[str, Any]:
    output = {
        "status": "pending",
        "eta_days": 3,
        "message": "Refund is pending; expected update in 3 days.",
        "next_step": "wait_for_processor_update",
    }
    return {
        "call_id": f"synthetic_fail_latency_cost_{index:04d}",
        "project_id": PROJECT_ID,
        "agent_name": PRIMARY_AGENT,
        "workflow_name": PRIMARY_WORKFLOW,
        "created_at": created_at,
        "status": "completed",
        "latency_ms": 4200 + (index * 170),
        "cost_usd": round(0.012 + (index * 0.0009), 7),
        "tool_calls": [
            {"name": "lookup_order"},
            {"name": "get_refund_status"},
            {"name": "render_refund_answer"},
        ],
        "output_content": json.dumps(output, separators=(",", ":")),
        "finish_reason": "stop",
        "injected_failure_type": "latency_cost_spike",
        "metadata": {"dataset": "synthetic_discovery_mixed", "ground_truth": "failure"},
    }


def build_dataset(counts: DatasetCounts, *, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    base = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)

    normal: list[dict[str, Any]] = []
    injected: list[dict[str, Any]] = []

    for i in range(counts.normal_primary):
        normal.append(_normal_refund_trace(i, _iso(base, index=i), rng))

    low_volume_start = base + timedelta(days=1)
    for i in range(counts.normal_low_volume):
        normal.append(_low_volume_trace(i, _iso(low_volume_start, index=i, minutes=37), rng))

    failure_start = base + timedelta(days=5)
    offset = 0
    for i in range(counts.missing_tool_failures):
        injected.append(_missing_tool_failure(i, _iso(failure_start, index=offset + i)))
    offset += counts.missing_tool_failures
    for i in range(counts.schema_break_failures):
        injected.append(_schema_break_failure(i, _iso(failure_start, index=offset + i)))
    offset += counts.schema_break_failures
    for i in range(counts.outcome_mismatch_failures):
        injected.append(_outcome_mismatch_failure(i, _iso(failure_start, index=offset + i)))
    offset += counts.outcome_mismatch_failures
    for i in range(counts.latency_cost_failures):
        injected.append(_latency_cost_failure(i, _iso(failure_start, index=offset + i)))

    return normal, injected


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def write_truth(path: Path, normal: list[dict[str, Any]], injected: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["call_id", "ground_truth", "failure_type"],
        )
        writer.writeheader()
        for row in normal:
            writer.writerow(
                {
                    "call_id": row["call_id"],
                    "ground_truth": "normal",
                    "failure_type": "",
                }
            )
        for row in injected:
            writer.writerow(
                {
                    "call_id": row["call_id"],
                    "ground_truth": "failure",
                    "failure_type": row.get("injected_failure_type", "injected"),
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("artifacts/discovery_synthetic_dataset"),
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--normal-primary", type=int, default=DEFAULT_COUNTS.normal_primary)
    parser.add_argument("--normal-low-volume", type=int, default=DEFAULT_COUNTS.normal_low_volume)
    parser.add_argument(
        "--missing-tool-failures",
        type=int,
        default=DEFAULT_COUNTS.missing_tool_failures,
    )
    parser.add_argument(
        "--schema-break-failures",
        type=int,
        default=DEFAULT_COUNTS.schema_break_failures,
    )
    parser.add_argument(
        "--outcome-mismatch-failures",
        type=int,
        default=DEFAULT_COUNTS.outcome_mismatch_failures,
    )
    parser.add_argument(
        "--latency-cost-failures",
        type=int,
        default=DEFAULT_COUNTS.latency_cost_failures,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    counts = DatasetCounts(
        normal_primary=max(0, args.normal_primary),
        normal_low_volume=max(0, args.normal_low_volume),
        missing_tool_failures=max(0, args.missing_tool_failures),
        schema_break_failures=max(0, args.schema_break_failures),
        outcome_mismatch_failures=max(0, args.outcome_mismatch_failures),
        latency_cost_failures=max(0, args.latency_cost_failures),
    )
    normal, injected = build_dataset(counts, seed=args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    normal_path = args.out_dir / "traces.jsonl"
    injected_path = args.out_dir / "injected_failures.jsonl"
    truth_path = args.out_dir / "ground_truth.csv"
    write_jsonl(normal_path, normal)
    write_jsonl(injected_path, injected)
    write_truth(truth_path, normal, injected)
    total = len(normal) + len(injected)
    failure_pct = (len(injected) / total) if total else 0.0
    print(f"Wrote normal traces:   {normal_path} ({len(normal)})")
    print(f"Wrote injected traces: {injected_path} ({len(injected)})")
    print(f"Wrote ground truth:    {truth_path}")
    print(f"Total traces:          {total} ({failure_pct:.1%} injected failures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
