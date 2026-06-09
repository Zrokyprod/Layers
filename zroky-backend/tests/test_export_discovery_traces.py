from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Call


def _load_exporter_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "export_discovery_traces.py"
    spec = importlib.util.spec_from_file_location("export_discovery_traces", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "calls.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_factory() as db:
        db.add(
            Call(
                id="call-prod-1",
                project_id="project-1",
                event_id="event-prod-1",
                created_at=datetime(2026, 6, 1, tzinfo=UTC),
                agent_name="refund-agent",
                provider="openai",
                model="gpt-test",
                status="completed",
                latency_ms=650,
                cost_total=0.002,
                output_fingerprint="fp-1",
                is_production=True,
                payload_json=json.dumps(
                    {
                        "workflow_name": "refund-status",
                        "tool_calls": [
                            {"name": "lookup_order", "arguments": {"email": "a@example.com"}},
                            {"function": {"name": "get_refund_status", "arguments": "{}"}},
                        ],
                        "output_content": json.dumps(
                            {
                                "status": "pending",
                                "message": "Refund for a@example.com is pending.",
                            }
                        ),
                        "finish_reason": "stop",
                        "outcome": {"success": True},
                    },
                    separators=(",", ":"),
                ),
            )
        )
        db.add(
            Call(
                id="call-non-prod",
                project_id="project-1",
                event_id="event-non-prod",
                created_at=datetime(2026, 6, 1, tzinfo=UTC) + timedelta(minutes=1),
                agent_name="refund-agent",
                provider="openai",
                model="gpt-test",
                status="completed",
                latency_ms=700,
                cost_total=0.002,
                is_production=False,
                payload_json=json.dumps(
                    {
                        "workflow_name": "refund-status",
                        "tool_calls": [{"name": "lookup_order"}],
                        "output_content": "Non production output.",
                    },
                    separators=(",", ":"),
                ),
            )
        )
        db.commit()
    engine.dispose()
    return db_path


def test_exporter_writes_shape_only_production_jsonl_and_summary(tmp_path: Path) -> None:
    exporter = _load_exporter_module()
    db_path = _seed_db(tmp_path)
    out_path = tmp_path / "traces.jsonl"

    result = exporter.main(
        [
            "--database-url",
            f"sqlite:///{db_path}",
            "--project-id",
            "project-1",
            "--out",
            str(out_path),
            "--min-rows",
            "1",
        ]
    )

    assert result == 0
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["call_id"] == "call-prod-1"
    payload = json.loads(rows[0]["payload_json"])
    assert payload["workflow_name"] == "refund-status"
    assert payload["tool_calls"] == [
        {"name": "lookup_order"},
        {"name": "get_refund_status"},
    ]
    assert "a@example.com" not in rows[0]["payload_json"]
    assert json.loads(payload["output_content"]) == {
        "message": "[redacted]",
        "status": "[redacted]",
    }

    summary = json.loads(out_path.with_suffix(".summary.json").read_text(encoding="utf-8"))
    assert summary["rows_exported"] == 1
    assert summary["production_only"] is True
    assert summary["workflows"] == {"refund-status": 1}


def test_exporter_can_include_non_production_and_fail_on_min_rows(tmp_path: Path) -> None:
    exporter = _load_exporter_module()
    db_path = _seed_db(tmp_path)
    out_path = tmp_path / "all_traces.jsonl"

    include_result = exporter.main(
        [
            "--database-url",
            f"sqlite:///{db_path}",
            "--project-id",
            "project-1",
            "--include-non-production",
            "--out",
            str(out_path),
        ]
    )

    assert include_result == 0
    assert len(out_path.read_text(encoding="utf-8").splitlines()) == 2

    fail_result = exporter.main(
        [
            "--database-url",
            f"sqlite:///{db_path}",
            "--project-id",
            "missing-project",
            "--out",
            str(tmp_path / "empty.jsonl"),
            "--min-rows",
            "1",
        ]
    )

    assert fail_result == 1
