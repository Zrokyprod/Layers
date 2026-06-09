from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _load_validator_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "validate_discovery_trace_readiness.py"
    spec = importlib.util.spec_from_file_location("validate_discovery_trace_readiness", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_trace_file(path: Path, *, rows: int, days: int) -> None:
    base = datetime(2026, 6, 1, tzinfo=UTC)
    with path.open("w", encoding="utf-8") as handle:
        for index in range(rows):
            occurred_at = base + timedelta(days=index % days, minutes=index)
            payload = {
                "workflow_name": "refund-status",
                "tool_calls": [{"name": "lookup_order"}, {"name": "get_refund_status"}],
                "output_content": json.dumps({"status": "redacted", "eta_days": 3}),
                "outcome": {"success": True},
            }
            record = {
                "call_id": f"call-{index}",
                "project_id": "project-1",
                "agent_name": "refund-agent",
                "created_at": occurred_at.isoformat(),
                "status": "completed",
                "payload_json": json.dumps(payload, separators=(",", ":")),
                "is_production": True,
            }
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def test_trace_readiness_passes_for_pilot_like_jsonl(tmp_path: Path) -> None:
    validator = _load_validator_module()
    traces = tmp_path / "traces.jsonl"
    summary = tmp_path / "summary.json"
    _write_trace_file(traces, rows=220, days=4)

    result = validator.main(
        [
            "--traces",
            str(traces),
            "--summary-out",
            str(summary),
            "--min-rows",
            "200",
            "--min-days",
            "3",
        ]
    )

    assert result == 0
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["rows"] == 220
    assert payload["time"]["active_days"] == 4
    assert payload["coverage"]["output_signal_pct"] == 1.0
    assert payload["gate"]["passed"] is True


def test_trace_readiness_fails_low_volume_and_short_span(tmp_path: Path) -> None:
    validator = _load_validator_module()
    traces = tmp_path / "low.jsonl"
    _write_trace_file(traces, rows=25, days=1)

    result = validator.main(["--traces", str(traces), "--min-rows", "200", "--min-days", "3"])

    assert result == 1
    report = validator.build_readiness_report(
        validator.load_jsonl_records([traces]),
        args=validator.parse_args(
            ["--traces", str(traces), "--min-rows", "200", "--min-days", "3"]
        ),
    )
    assert "rows 25 < min_rows 200" in report["gate"]["reasons"]
    assert "active_days 1 < min_days 3" in report["gate"]["reasons"]


def test_trace_readiness_rejects_invalid_jsonl(tmp_path: Path) -> None:
    validator = _load_validator_module()
    traces = tmp_path / "bad.jsonl"
    traces.write_text('{"ok": true}\nnot-json\n', encoding="utf-8")

    result = validator.main(["--traces", str(traces)])

    assert result == 2
