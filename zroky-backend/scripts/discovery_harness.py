#!/usr/bin/env python3
"""Offline harness for the Zroky Discover spike.

This is now a THIN WRAPPER over the shared production logic in
``app.services.discovery`` — the package root exports only the pure (DB-free)
engine, so the harness reuses the EXACT same baseline math, scorer, and
promotion gates that run in production. There is one source of truth; the
harness and the product can never drift apart.

The harness still owns only the offline-spike concerns:
  - trace IO (JSONL / read-only SQLite `calls` / local `.data` scan / demo)
  - injected-failure tagging for recall measurement
  - manual-label ingestion + precision/recall report
It performs no migrations, creates no API/UI, and never writes to inputs.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Make `app` importable when run as a standalone script from the repo root or
# the backend dir.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.discovery import (  # noqa: E402
    AnomalyCandidate,
    BaselineConfig,
    aggregate_cluster,
    behavior_key,
    build_baselines_in_memory,
    decide_tier,
    extract_features,
    make_signature,
    score,
)
from app.services.discovery.promote import (  # noqa: E402
    DEFAULT_RECURRENCE_K,
    DEFAULT_SURFACE_MIN_CONFIDENCE,
    PromotionInputs,
)

DEFAULT_WARMUP_MIN_TRACES = 200
DEFAULT_WARMUP_MIN_DAYS = 3
DEFAULT_CRITICAL_TOOL_PCT = 0.90
DEFAULT_Z_WEAK = 3.0
LABEL_TEMPLATE_FIELDS = [
    "finding_id",
    "signature",
    "manual_label",
    "reason",
    "confidence",
    "anomaly_score",
    "occurrence_count",
    "corroboration",
    "sample_call_ids",
    "reviewer_notes",
]


@dataclass(frozen=True)
class HarnessConfig:
    warmup_min_traces: int = DEFAULT_WARMUP_MIN_TRACES
    warmup_min_days: int = DEFAULT_WARMUP_MIN_DAYS
    recurrence_k: int = DEFAULT_RECURRENCE_K
    critical_tool_pct: float = DEFAULT_CRITICAL_TOOL_PCT
    surface_min_confidence: float = DEFAULT_SURFACE_MIN_CONFIDENCE
    z_weak: float = DEFAULT_Z_WEAK


@dataclass(frozen=True)
class GateConfig:
    precision_threshold: float = 0.90
    min_scored_traces: int = 0
    min_labelled_surfaced: int = 1


VALID_MANUAL_LABELS = {"real", "not_a_failure"}
MANUAL_LABEL_ALIASES = {
    "failure": "real",
    "true_positive": "real",
    "tp": "real",
    "yes": "real",
    "y": "real",
    "false_positive": "not_a_failure",
    "fp": "not_a_failure",
    "not_failure": "not_a_failure",
    "no": "not_a_failure",
    "n": "not_a_failure",
}


# ── trace IO (harness-only) ───────────────────────────────────────────────────


def _parse_time(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return _parse_time(float(raw))
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None
    return None


@dataclass(frozen=True)
class _HarnessTrace:
    """Wraps shared BehavioralFeatures with harness-only fields."""

    features: Any  # BehavioralFeatures
    occurred_at: datetime | None
    injected_failure_type: str | None


def _record_time(record: Mapping[str, Any]) -> datetime | None:
    payload = record.get("payload_json") or record.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
    if not isinstance(payload, Mapping):
        payload = {}
    for source in (record, payload):
        for key in ("created_at", "completed_at"):
            value = source.get(key) if isinstance(source, Mapping) else None
            parsed = _parse_time(value)
            if parsed is not None:
                return parsed
    return None


def normalize(record: Mapping[str, Any], *, source: str, ordinal: int) -> _HarnessTrace:
    features = extract_features(record)
    if features.call_id == "unknown":
        # Give the trace a stable id for reporting when none exists.
        object.__setattr__(features, "call_id", f"{source}:{ordinal}")
    injected = record.get("injected_failure_type")
    injected = str(injected).strip() if injected not in (None, "") else None
    return _HarnessTrace(
        features=features,
        occurred_at=_record_time(record),
        injected_failure_type=injected,
    )


def read_jsonl(path: Path, *, injected: bool = False) -> list[_HarnessTrace]:
    traces: list[_HarnessTrace] = []
    with path.open("r", encoding="utf-8") as handle:
        for ordinal, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            if not isinstance(record, Mapping):
                raise ValueError(f"{path}:{ordinal} is not a JSON object")
            if injected and not record.get("injected_failure_type"):
                record = {**record, "injected_failure_type": "injected"}
            traces.append(normalize(record, source=str(path), ordinal=ordinal))
    return traces


def read_sqlite_calls(path: Path) -> list[_HarnessTrace]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "calls" not in tables:
            return []
        columns = [str(r[1]) for r in conn.execute("PRAGMA table_info(calls)").fetchall()]
        wanted = [
            "id", "project_id", "event_id", "created_at", "agent_name",
            "provider", "model", "status", "error_code", "latency_ms",
            "cost_total", "output_fingerprint", "tool_lifecycle_summary_json",
            "payload_json", "metadata",
        ]
        selected = [c for c in wanted if c in columns]
        if not selected:
            return []
        sql = f"SELECT {', '.join(selected)} FROM calls"
        if "created_at" in selected:
            sql += " ORDER BY created_at"
        return [
            normalize(dict(row), source=f"sqlite:{path}", ordinal=ordinal)
            for ordinal, row in enumerate(conn.execute(sql), start=1)
        ]
    finally:
        conn.close()


def discover_data_dbs() -> list[Path]:
    candidates: list[Path] = []
    for root in (Path.cwd() / ".data", _BACKEND_ROOT / ".data"):
        if root.exists():
            candidates.extend(sorted(root.glob("*.db")))
    return candidates


# ── pipeline (delegates to shared pure logic) ─────────────────────────────────


def run_harness(
    traces: Sequence[_HarnessTrace],
    config: HarnessConfig,
    labels: Mapping[str, str],
    gate_config: GateConfig | None = None,
) -> dict[str, Any]:
    baseline_config = BaselineConfig(
        warmup_min_traces=config.warmup_min_traces,
        warmup_min_days=config.warmup_min_days,
        critical_tool_pct=config.critical_tool_pct,
    )
    # 1) Baselines — built from NON-injected traces only (don't poison normal).
    normal_stream = [
        (t.features, t.occurred_at) for t in traces if not t.injected_failure_type
    ]
    baselines = build_baselines_in_memory(normal_stream, baseline_config)

    # 2) Score every trace against its key's baseline.
    candidates: list[AnomalyCandidate] = []
    injected_by_call: dict[str, str] = {}
    scored = 0
    for t in traces:
        key, _ = behavior_key(t.features)
        baseline = baselines.get(key)
        if not baseline or baseline.get("status") == "learning":
            continue
        scored += 1
        candidate = score(t.features, baseline, behavior_key=key, z_weak=config.z_weak)
        if candidate is not None:
            candidates.append(candidate)
            if t.injected_failure_type:
                injected_by_call[t.features.call_id] = t.injected_failure_type

    # 3) Promote (cluster → tier) using the SHARED gates.
    suspect_keys = {k for k, b in baselines.items() if b.get("status") == "suspect"}
    findings = _promote(candidates, baselines, suspect_keys, config, labels)

    injected_call_ids = {t.features.call_id for t in traces if t.injected_failure_type}
    return _build_report(
        baselines=baselines,
        traces_scored=scored,
        findings=findings,
        injected_call_ids=injected_call_ids,
        gate_config=gate_config or GateConfig(),
    )


def _promote(
    candidates: Sequence[AnomalyCandidate],
    baselines: Mapping[str, dict],
    suspect_keys: set[str],
    config: HarnessConfig,
    labels: Mapping[str, str],
) -> list[dict]:
    # Suspect baselines already emit very low confidence (the scorer subtracts
    # 0.30) and are caught by decide_tier's watching floor, so we pass
    # baseline_suspect=False here and let confidence carry the suppression.
    clustered: dict[str, list[AnomalyCandidate]] = defaultdict(list)
    for candidate in candidates:
        clustered[candidate.signature].append(candidate)

    findings: list[dict] = []
    for signature, group in sorted(clustered.items()):
        agg = aggregate_cluster(group)
        tier = decide_tier(
            PromotionInputs(
                occurrence_count=agg["occurrence_count"],
                max_confidence=agg["max_confidence"],
                has_outcome=agg["has_outcome"],
                has_strong_structural=agg["has_strong_structural"],
                has_multi_dim=agg["has_multi_dim"],
                baseline_suspect=False,
                surface_min_confidence=config.surface_min_confidence,
                recurrence_k=config.recurrence_k,
            )
        )
        finding_id = "disc_" + make_signature(signature, tier)[:12]
        manual_label = labels.get(finding_id) or labels.get(signature) or ""
        findings.append(
            {
                "finding_id": finding_id,
                "signature": signature,
                "tier": tier,
                "anomaly_score": round(float(agg["anomaly_score"]), 4),
                "confidence": round(float(agg["max_confidence"]), 4),
                "reason": agg["reason"],
                "corroboration": list(agg["corroboration"]),
                "sample_call_ids": list(agg["call_ids"][:8]),
                "occurrence_count": agg["occurrence_count"],
                "manual_label": manual_label,
                "call_ids": list(agg["call_ids"]),
            }
        )
    return findings


# ── report (harness-only) ─────────────────────────────────────────────────────


def read_manual_labels(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    labels: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            label = _normalize_manual_label(row.get("manual_label"))
            if not label:
                continue
            if label not in VALID_MANUAL_LABELS:
                raise ValueError(
                    f"{path}:{line_number} has invalid manual_label {label!r}; "
                    "use 'real' or 'not_a_failure'"
                )
            for key_field in ("finding_id", "signature"):
                key = (row.get(key_field) or "").strip()
                if key:
                    labels[key] = label
    return labels


def _normalize_manual_label(value: object) -> str:
    raw = str(value or "").strip().lower()
    return MANUAL_LABEL_ALIASES.get(raw, raw)


def _build_report(
    *,
    baselines: Mapping[str, dict],
    traces_scored: int,
    findings: Sequence[dict],
    injected_call_ids: set[str],
    gate_config: GateConfig,
) -> dict[str, Any]:
    baseline_counts = Counter(b.get("status", "learning") for b in baselines.values())
    low_specificity = sum(1 for b in baselines.values() if b.get("low_specificity"))
    tier_counts = Counter(f["tier"] for f in findings)
    surfaced = [f for f in findings if f["tier"] == "surfaced"]
    watching = [f for f in findings if f["tier"] == "watching"]

    labelled = [f for f in surfaced if f["manual_label"] in {"real", "not_a_failure"}]
    real = [f for f in labelled if f["manual_label"] == "real"]
    false_positive = [f for f in surfaced if f["manual_label"] == "not_a_failure"]
    surfaced_call_ids = {cid for f in surfaced for cid in f["call_ids"]}
    injected_caught = injected_call_ids & surfaced_call_ids
    promotion_denominator = len(watching) + len(surfaced)

    report = {
        "baseline_keys": {
            "total": len(baselines),
            "active": baseline_counts.get("active", 0),
            "learning": baseline_counts.get("learning", 0),
            "suspect": baseline_counts.get("suspect", 0),
            "low_specificity": low_specificity,
        },
        "traces_scored": traces_scored,
        "findings": {
            "watching": tier_counts.get("watching", 0),
            "surfaced": tier_counts.get("surfaced", 0),
            "dismissed": tier_counts.get("dismissed", 0),
            "items": [{k: v for k, v in f.items() if k != "call_ids"} for f in findings],
        },
        "precision": {
            "surfaced_real": len(real),
            "surfaced_labelled_total": len(labelled),
            "value": len(real) / len(labelled) if labelled else None,
            "manual_labels_required": not labelled,
        },
        "recall": {
            "injected_caught": len(injected_caught),
            "injected_total": len(injected_call_ids),
            "value": len(injected_caught) / len(injected_call_ids) if injected_call_ids else None,
        },
        "false_positive_examples": [
            {"finding_id": f["finding_id"], "signature": f["signature"], "reason": f["reason"]}
            for f in false_positive
        ],
        "watching_to_surfaced_rate": (
            len(surfaced) / promotion_denominator if promotion_denominator else None
        ),
    }
    report["gate"] = evaluate_gate(report, gate_config)
    return report


def evaluate_gate(report: Mapping[str, Any], gate_config: GateConfig) -> dict[str, Any]:
    precision = report["precision"]
    reasons: list[str] = []
    value = precision["value"]
    labelled_total = int(precision["surfaced_labelled_total"])
    traces_scored = int(report["traces_scored"])
    active_baselines = int(report["baseline_keys"]["active"])

    if active_baselines < 1:
        reasons.append("no active baseline")
    if traces_scored < gate_config.min_scored_traces:
        reasons.append(
            f"traces_scored {traces_scored} < min_scored_traces "
            f"{gate_config.min_scored_traces}"
        )
    if labelled_total < gate_config.min_labelled_surfaced:
        reasons.append(
            f"labelled surfaced findings {labelled_total} < "
            f"min_labelled_surfaced {gate_config.min_labelled_surfaced}"
        )
    if value is None:
        reasons.append("manual labels required")
    elif value < gate_config.precision_threshold:
        reasons.append(
            f"precision {value:.3f} < threshold {gate_config.precision_threshold:.3f}"
        )

    passed = not reasons
    return {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "precision_threshold": gate_config.precision_threshold,
        "min_scored_traces": gate_config.min_scored_traces,
        "min_labelled_surfaced": gate_config.min_labelled_surfaced,
        "reasons": reasons,
    }


def print_report(report: Mapping[str, Any]) -> None:
    bl = report["baseline_keys"]
    fnd = report["findings"]
    precision = report["precision"]
    recall = report["recall"]
    gate = report["gate"]
    rate = report["watching_to_surfaced_rate"]

    print("=== Discovery Harness Report ===")
    print(
        "Baseline keys found:           "
        f"{bl['total']}   (active: {bl['active']}, learning: {bl['learning']}, "
        f"suspect: {bl['suspect']}, low_specificity: {bl['low_specificity']})"
    )
    print(f"Traces scored:                 {report['traces_scored']}")
    print(f"Findings - watching:           {fnd['watching']}")
    print(f"Findings - surfaced:           {fnd['surfaced']}")
    print(f"Findings - dismissed:          {fnd['dismissed']}")
    print()
    print("For each SURFACED finding:")
    print(
        "  finding_id | signature | anomaly_score | confidence | reason | "
        "corroboration[] | sample_call_ids | manual_label"
    )
    for item in fnd["items"]:
        if item["tier"] != "surfaced":
            continue
        print(
            "  " + " | ".join([
                item["finding_id"],
                item["signature"],
                f"{item['anomaly_score']:.4f}",
                f"{item['confidence']:.4f}",
                item["reason"],
                json.dumps(item["corroboration"], ensure_ascii=False),
                json.dumps(item["sample_call_ids"], ensure_ascii=False),
                item["manual_label"],
            ])
        )
    print()
    if precision["value"] is None:
        precision_text = (
            f"{precision['surfaced_real']}/{precision['surfaced_labelled_total']} "
            "(manual labels required)"
        )
    else:
        precision_text = (
            f"{precision['surfaced_real']}/{precision['surfaced_labelled_total']} = "
            f"{precision['value']:.3f}"
        )
    print(
        f"Precision (surfaced):          {precision_text}   <- GATE: >= "
        f"{gate['precision_threshold']:.2f}"
    )
    if recall["value"] is None:
        recall_text = f"{recall['injected_caught']}/{recall['injected_total']}"
    else:
        recall_text = (
            f"{recall['injected_caught']}/{recall['injected_total']} = {recall['value']:.3f}"
        )
    print(f"Recall on injected failures:   {recall_text}")
    print(
        "False-positive examples:       "
        + json.dumps(report["false_positive_examples"], ensure_ascii=False)
    )
    print(f"Watching->surfaced rate:        {'n/a' if rate is None else f'{rate:.3f}'}")
    print(
        "Gate status:                   "
        f"{gate['status']} "
        f"(min_scored_traces={gate['min_scored_traces']}, "
        f"min_labelled_surfaced={gate['min_labelled_surfaced']})"
    )
    if gate["reasons"]:
        print("Gate failure reasons:          " + "; ".join(gate["reasons"]))


def write_artifacts(report: Mapping[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "discovery_harness_report.json"
    csv_path = out_dir / "discovery_harness_findings.csv"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "finding_id", "signature", "tier", "anomaly_score", "confidence",
                "reason", "corroboration", "sample_call_ids", "occurrence_count",
                "manual_label",
            ],
        )
        writer.writeheader()
        for item in report["findings"]["items"]:
            writer.writerow({
                **item,
                "corroboration": json.dumps(item["corroboration"], ensure_ascii=False),
                "sample_call_ids": json.dumps(item["sample_call_ids"], ensure_ascii=False),
            })
    print(f"Wrote report: {report_path}")
    print(f"Wrote findings CSV: {csv_path}")


def write_label_template(report: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_TEMPLATE_FIELDS)
        writer.writeheader()
        for item in report["findings"]["items"]:
            if item.get("tier") != "surfaced":
                continue
            writer.writerow(
                {
                    "finding_id": item["finding_id"],
                    "signature": item["signature"],
                    "manual_label": "",
                    "reason": item["reason"],
                    "confidence": item["confidence"],
                    "anomaly_score": item["anomaly_score"],
                    "occurrence_count": item["occurrence_count"],
                    "corroboration": json.dumps(item["corroboration"], ensure_ascii=False),
                    "sample_call_ids": json.dumps(item["sample_call_ids"], ensure_ascii=False),
                    "reviewer_notes": "",
                }
            )
    print(f"Wrote label template: {path}")


# ── demo data (harness-only smoke set) ────────────────────────────────────────


def demo_traces() -> list[_HarnessTrace]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    records: list[dict[str, Any]] = []
    for index in range(260):
        day = index // 70
        records.append({
            "call_id": f"demo_normal_{index:03d}",
            "project_id": "demo_project",
            "agent_name": "refund_agent",
            "workflow_name": "refund_status_check",
            "created_at": (base + timedelta(days=day, minutes=index)).isoformat(),
            "status": "completed",
            "latency_ms": 620 + (index % 30),
            "cost_usd": 0.002 + ((index % 5) * 0.0001),
            "tool_calls": [{"name": "lookup_order"}, {"name": "get_refund_status"}],
            "output": json.dumps({"status": "pending", "eta_days": 3, "message": "Refund is pending."}),
            "finish_reason": "stop",
            "outcome": {"success": True},
        })
    for index in range(5):
        records.append({
            "call_id": f"demo_missing_tool_{index:03d}",
            "project_id": "demo_project",
            "agent_name": "refund_agent",
            "workflow_name": "refund_status_check",
            "created_at": (base + timedelta(days=5, minutes=index)).isoformat(),
            "status": "completed",
            "latency_ms": 410,
            "cost_usd": 0.001,
            "tool_calls": [{"name": "lookup_order"}],
            "output": "I think your refund is probably complete.",
            "finish_reason": "stop",
            "injected_failure_type": "missing_critical_tool",
        })
    for index in range(3):
        records.append({
            "call_id": f"demo_schema_break_{index:03d}",
            "project_id": "demo_project",
            "agent_name": "refund_agent",
            "workflow_name": "refund_status_check",
            "created_at": (base + timedelta(days=5, minutes=20 + index)).isoformat(),
            "status": "completed",
            "latency_ms": 600,
            "cost_usd": 0.002,
            "tool_calls": [{"name": "lookup_order"}, {"name": "get_refund_status"}],
            "output": json.dumps({"unexpected": "plain text fallback"}),
            "finish_reason": "stop",
            "injected_failure_type": "schema_break",
        })
    for index in range(3):
        records.append({
            "call_id": f"demo_outcome_mismatch_{index:03d}",
            "project_id": "demo_project",
            "agent_name": "refund_agent",
            "workflow_name": "refund_status_check",
            "created_at": (base + timedelta(days=5, minutes=40 + index)).isoformat(),
            "status": "completed",
            "latency_ms": 635,
            "cost_usd": 0.0021,
            "tool_calls": [{"name": "lookup_order"}, {"name": "get_refund_status"}],
            "output": json.dumps({"status": "pending", "eta_days": 3, "message": "Refund is pending."}),
            "finish_reason": "stop",
            "outcome": {"success": False},
            "injected_failure_type": "outcome_mismatch",
        })
    return [
        normalize(record, source="demo", ordinal=ordinal)
        for ordinal, record in enumerate(records, start=1)
    ]


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", action="append", type=Path, default=[], help="JSONL trace file")
    parser.add_argument("--inject", action="append", type=Path, default=[], help="JSONL injected known-bad traces")
    parser.add_argument("--sqlite", action="append", type=Path, default=[], help="SQLite DB with calls table")
    parser.add_argument("--scan-data", action="store_true", help="Read local .data/*.db stores read-only")
    parser.add_argument("--demo", action="store_true", help="Run deterministic mechanics-only demo data")
    parser.add_argument("--manual-labels", type=Path, help="CSV with finding_id/signature/manual_label")
    parser.add_argument(
        "--write-label-template",
        type=Path,
        help="Write a surfaced-finding CSV for manual gate labels.",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/discovery_harness"))
    parser.add_argument("--no-write", action="store_true", help="Print report only; do not write artifacts")
    parser.add_argument("--warmup-min-traces", type=int, default=DEFAULT_WARMUP_MIN_TRACES)
    parser.add_argument("--warmup-min-days", type=int, default=DEFAULT_WARMUP_MIN_DAYS)
    parser.add_argument("--recurrence-k", type=int, default=DEFAULT_RECURRENCE_K)
    parser.add_argument("--critical-tool-pct", type=float, default=DEFAULT_CRITICAL_TOOL_PCT)
    parser.add_argument("--surface-min-confidence", type=float, default=DEFAULT_SURFACE_MIN_CONFIDENCE)
    parser.add_argument("--z-weak", type=float, default=DEFAULT_Z_WEAK)
    parser.add_argument("--precision-threshold", type=float, default=0.90)
    parser.add_argument("--min-scored-traces", type=int, default=0)
    parser.add_argument("--min-labelled-surfaced", type=int, default=1)
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="Exit non-zero when the precision gate fails.",
    )
    return parser.parse_args(argv)


def load_traces(args: argparse.Namespace) -> list[_HarnessTrace]:
    traces: list[_HarnessTrace] = []
    if args.demo:
        traces.extend(demo_traces())
    for path in args.traces:
        traces.extend(read_jsonl(path, injected=False))
    for path in args.inject:
        traces.extend(read_jsonl(path, injected=True))
    sqlite_paths = list(args.sqlite)
    if args.scan_data:
        sqlite_paths.extend(discover_data_dbs())
    for path in sqlite_paths:
        try:
            traces.extend(read_sqlite_calls(path))
        except sqlite3.Error as exc:
            print(f"warning: skipped {path}: {exc}", file=sys.stderr)
    return traces


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    config = HarnessConfig(
        warmup_min_traces=max(1, args.warmup_min_traces),
        warmup_min_days=max(1, args.warmup_min_days),
        recurrence_k=max(1, args.recurrence_k),
        critical_tool_pct=min(1.0, max(0.0, args.critical_tool_pct)),
        surface_min_confidence=min(1.0, max(0.0, args.surface_min_confidence)),
        z_weak=max(0.1, args.z_weak),
    )
    gate_config = GateConfig(
        precision_threshold=min(1.0, max(0.0, args.precision_threshold)),
        min_scored_traces=max(0, args.min_scored_traces),
        min_labelled_surfaced=max(0, args.min_labelled_surfaced),
    )
    traces = load_traces(args)
    if not traces:
        print(
            "No traces loaded. Pass --demo, --traces, --inject, --sqlite, or --scan-data.",
            file=sys.stderr,
        )
        return 2
    try:
        labels = read_manual_labels(args.manual_labels)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    report = run_harness(traces, config, labels, gate_config)
    print_report(report)
    if not args.no_write:
        write_artifacts(report, args.out_dir)
    if args.write_label_template:
        write_label_template(report, args.write_label_template)
    if args.fail_on_gate and not report["gate"]["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
