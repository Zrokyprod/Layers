from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone

from app.models import ReplayJob, ReplayResult, ResultPayload
from app.runner import _parse_artifact, run_job


def _job(**overrides: object) -> ReplayJob:
    data = {
        "replay_id": "replay_1",
        "trace_id": "trace_1",
        "fix_pr_id": "fix_1",
        "candidate_fix_diff": "",
        "artifact_url": "https://artifacts.example/replay_1.json.gz",
        "artifact_signature": "bad-signature",
        "created_at": datetime.now(timezone.utc),
        "timeout_seconds": 3,
    }
    data.update(overrides)
    return ReplayJob(**data)


def test_run_job_rejects_invalid_artifact_signature() -> None:
    result = run_job(_job(), signing_key="real-signing-key")

    assert result.status == "error"
    assert result.error_message == "Artifact signature verification failed"


def test_parse_artifact_accepts_plain_json_and_gzip() -> None:
    payload = {"prompt": "hello", "expected_output": "world"}

    assert _parse_artifact(json.dumps(payload).encode()) == payload
    assert _parse_artifact(gzip.compress(json.dumps(payload).encode())) == payload


def test_run_job_without_openrouter_key_returns_controlled_failure(monkeypatch) -> None:
    artifact = json.dumps({"prompt": "say hi", "expected_output": "hi"}).encode()
    monkeypatch.setattr("app.runner.verify_artifact_signature", lambda **_: True)
    monkeypatch.setattr("app.runner.download_artifact", lambda _url: artifact)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("WORKER_TOKEN", raising=False)

    result = run_job(_job(), signing_key="")

    assert result.status == "fail"
    assert result.diff_metric is not None
    assert result.stdout_tail is not None
    assert "OPENROUTER_API_KEY not configured" in result.stdout_tail


def test_result_payload_serializes_for_control_plane() -> None:
    result = ReplayResult(
        replay_id="replay_1",
        trace_id="trace_1",
        fix_pr_id="fix_1",
        status="pass",
        diff_metric=0.1,
        completed_at=datetime.now(timezone.utc),
    )

    payload = ResultPayload(worker_token="worker-token", result=result).model_dump(mode="json")

    assert payload["worker_token"] == "worker-token"
    assert payload["result"]["status"] == "pass"
    assert payload["result"]["replay_id"] == "replay_1"
