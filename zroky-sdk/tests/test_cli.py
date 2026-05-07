"""Tests for the ``zroky`` CLI entry points."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from zroky import cli


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate each test from the user's actual SDK config & buffer."""
    monkeypatch.setenv("ZROKY_INGEST_URL", "http://localhost:8000")
    monkeypatch.setenv("ZROKY_API_KEY", "test-key")
    monkeypatch.setenv("ZROKY_PROJECT", "test-project")
    monkeypatch.setenv("ZROKY_OFFLINE_BUFFER", str(tmp_path / "buf.ndjson"))


def test_config_command_prints_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["config"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert rc == 0
    assert data["api_key"] == "set"
    assert data["project"] == "test-project"
    assert "ingest_url" in data


def test_buffer_status_when_empty(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["buffer", "status"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert rc == 0
    assert data["is_empty"] is True
    assert data["size_bytes"] == 0


def test_buffer_clear_runs(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["buffer", "clear"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert rc == 0
    assert data["cleared"] is True


def test_health_handles_connection_error(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_args, **_kwargs):  # noqa: ANN001
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(cli.httpx, "get", _raise)
    rc = cli.main(["health"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert rc == 1
    assert data["status"] == "error"
    assert "boom" in data["error"]


def test_replay_with_missing_file(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    rc = cli.main(["replay", str(tmp_path / "nope.json")])
    assert rc == 2


def test_replay_ndjson_file_posts_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    src = tmp_path / "events.ndjson"
    src.write_text(
        '{"call_id":"a","status":"success"}\n{"call_id":"b","status":"error"}\n',
        encoding="utf-8",
    )

    captured_post: dict = {}

    class _FakeResponse:
        status_code = 202
        text = "{}"

    def _fake_post(url: str, content: bytes, headers: dict, timeout: float):  # noqa: ANN001
        captured_post["url"] = url
        captured_post["headers"] = headers
        captured_post["body"] = json.loads(content)
        return _FakeResponse()

    monkeypatch.setattr(cli.httpx, "post", _fake_post)

    rc = cli.main(["replay", str(src)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["replayed"] == 2
    assert captured_post["url"].endswith("/api/v1/ingest")
    assert captured_post["body"]["events"][0]["call_id"] == "a"
    assert captured_post["body"]["events"][1]["call_id"] == "b"


def test_buffer_flush_with_empty_buffer(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["buffer", "flush"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["flushed"] == 0
