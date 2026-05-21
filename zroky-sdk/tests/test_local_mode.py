# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Tests for local SQLite mode writer."""
import json
import tempfile
from pathlib import Path

from zroky._internal.local_mode import LocalWriter
from zroky._internal.models import CallEvent


def _make_event(**kwargs: object) -> CallEvent:
    defaults = dict(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
        status="success",
        latency_ms=123.4,
        prompt_tokens=50,
        completion_tokens=20,
    )
    defaults.update(kwargs)
    return CallEvent(**defaults)  # type: ignore[arg-type]


def test_writes_events_to_sqlite(tmp_path: Path):
    db = tmp_path / "test.db"
    writer = LocalWriter(db_path=db)
    events = [_make_event(), _make_event(model="gpt-4o-mini")]
    writer.send_batch(events)
    writer.close()

    import sqlite3  # noqa: PLC0415
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT call_id, model FROM call_events ORDER BY id").fetchall()
    conn.close()

    assert len(rows) == 2
    models = [r[1] for r in rows]
    assert "gpt-4o" in models
    assert "gpt-4o-mini" in models


def test_failed_event_recorded(tmp_path: Path):
    db = tmp_path / "fail.db"
    writer = LocalWriter(db_path=db)
    event = _make_event(status="failed", error_code="AUTH_FAILURE", error_message="401 Unauthorized")
    writer.send_batch([event])
    writer.close()

    import sqlite3  # noqa: PLC0415
    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT status, error_code FROM call_events").fetchone()
    conn.close()

    assert row[0] == "failed"
    assert row[1] == "AUTH_FAILURE"


def test_payload_json_valid(tmp_path: Path):
    db = tmp_path / "json.db"
    writer = LocalWriter(db_path=db)
    event = _make_event()
    writer.send_batch([event])
    writer.close()

    import sqlite3  # noqa: PLC0415
    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT payload_json FROM call_events").fetchone()
    conn.close()

    payload = json.loads(row[0])
    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-4o"


def test_creates_parent_dirs(tmp_path: Path):
    db = tmp_path / "nested" / "dir" / "test.db"
    writer = LocalWriter(db_path=db)
    writer.send_batch([_make_event()])
    writer.close()
    assert db.exists()
