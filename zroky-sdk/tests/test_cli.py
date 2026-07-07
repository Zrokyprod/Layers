# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Tests for the ``zroky`` CLI entry points."""

from __future__ import annotations

import json
from pathlib import Path

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


def test_init_writes_protected_action_starter_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = cli.main(["init", "--path", str(tmp_path)])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["ok"] is True
    env_file = tmp_path / ".env.example"
    quickstart = tmp_path / "zroky_quickstart.py"
    assert env_file.exists()
    assert quickstart.exists()
    env_text = env_file.read_text(encoding="utf-8")
    assert "ZROKY_API_KEY" in env_text
    assert "ZROKY_PROJECT_ID" in env_text
    assert "ZROKY_API_URL" in env_text
    assert "zroky.protect(" in quickstart.read_text(encoding="utf-8")


def test_init_skips_existing_files_without_force(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    quickstart = tmp_path / "zroky_quickstart.py"
    quickstart.write_text("# keep me\n", encoding="utf-8")

    rc = cli.main(["init", "--path", str(tmp_path)])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert str(quickstart) in out["skipped"]
    assert quickstart.read_text(encoding="utf-8") == "# keep me\n"


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
    captured: dict[str, object] = {}

    def _raise(url: str, **_kwargs):  # noqa: ANN001
        captured["url"] = url
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(cli.httpx, "get", _raise)
    rc = cli.main(["health"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert rc == 1
    assert data["status"] == "error"
    assert data["url"].endswith("/health/live")
    assert "boom" in data["error"]


def test_doctor_reports_healthy_setup(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_get: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200
        text = '{"status":"ok"}'

    def _fake_get(url: str, headers: dict, timeout: float):  # noqa: ANN001
        captured_get["url"] = url
        captured_get["headers"] = headers
        captured_get["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(cli.httpx, "get", _fake_get)

    rc = cli.main(["doctor"])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["ok"] is True
    assert captured_get["url"] == "http://localhost:8000/health/live"
    assert captured_get["headers"]["x-api-key"] == "test-key"  # type: ignore[index]
    assert captured_get["headers"]["x-project-id"] == "test-project"  # type: ignore[index]


def test_ingest_test_requires_api_key(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZROKY_API_KEY")

    rc = cli.main(["ingest", "--test"])
    out = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert out["ok"] is False
    assert "ZROKY_API_KEY" in out["error"]


def test_ingest_test_posts_smoke_event(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_post: dict[str, object] = {}

    class _FakeResponse:
        status_code = 202
        text = '{"accepted":1}'

    def _fake_post(url: str, content: str, headers: dict, timeout: float):  # noqa: ANN001
        captured_post["url"] = url
        captured_post["headers"] = headers
        captured_post["timeout"] = timeout
        captured_post["body"] = json.loads(content)
        return _FakeResponse()

    monkeypatch.setattr(cli.httpx, "post", _fake_post)

    rc = cli.main(["ingest", "--test"])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["ok"] is True
    assert captured_post["url"] == "http://localhost:8000/api/v1/ingest"
    assert captured_post["headers"]["x-api-key"] == "test-key"  # type: ignore[index]
    event = captured_post["body"]["events"][0]  # type: ignore[index]
    assert event["provider"] == "zroky"
    assert event["model"] == "ingest-test"
    assert event["metadata"]["command"] == "zroky ingest --test"


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


def test_runner_once_command_uses_runner_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    created: dict[str, object] = {}

    class _FakeRunner:
        def __init__(self, *, runner_id: str) -> None:
            created["runner_id"] = runner_id

        def run_once(self, *, runner_metadata: dict[str, str]) -> dict[str, object]:
            created["runner_instance_id"] = runner_metadata["runner_instance_id"]
            return {"claimed": False, "status": "idle"}

    monkeypatch.setattr(cli, "ProtectedActionRunner", _FakeRunner)

    rc = cli.main(
        ["runner", "once", "--runner-id", "runner_123", "--runner-instance-id", "local_1"]
    )
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out == {"claimed": False, "status": "idle"}
    assert created["runner_id"] == "runner_123"
    assert created["runner_instance_id"] == "local_1"


def test_runner_daemon_command_runs_bounded_loop(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    created: dict[str, object] = {}

    class _FakeRunner:
        def __init__(self, *, runner_id: str) -> None:
            created["runner_id"] = runner_id

        def run_daemon(self, **kwargs: object) -> dict[str, object]:
            created.update(kwargs)
            return {"status": "stopped", "iterations": 1, "claim_errors": 0}

    monkeypatch.setattr(cli, "ProtectedActionRunner", _FakeRunner)

    rc = cli.main(
        [
            "runner",
            "daemon",
            "--runner-id",
            "runner_123",
            "--runner-instance-id",
            "local_1",
            "--supported-operation-kind",
            "TRANSFER",
            "--max-iterations",
            "1",
            "--no-offline-heartbeat",
        ]
    )
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["status"] == "stopped"
    assert created["runner_id"] == "runner_123"
    assert created["max_iterations"] == 1
    assert created["send_offline_heartbeat"] is False
    assert created["supported_operation_kinds"] == ["TRANSFER"]
