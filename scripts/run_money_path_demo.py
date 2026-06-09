from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import types
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "zroky-backend"
SDK_DIR = ROOT / "zroky-sdk"

PROJECT_HEADER = "X-Project-Id"
PROJECT_ID = "demo-refund-money-path"
CALL_ID = "demo-call-refund-missed-tool"
TRACE_ID = "trace-demo-refund-missed-tool"
PROMPT_FINGERPRINT = "fp-demo-refund-v1"
PROVIDER_KEY_PLAINTEXT = "sk-demo-money-path-1234567890"
EXPECTED_TOOL = "get_refund_status"
BAD_OUTPUT = (
    "Refunds are usually processed within 5-10 business days. Please check your payment provider "
    "or contact support if you still have questions."
)
FIXED_OUTPUT = (
    "Your refund RF-1001 for order ORD-1001 was issued on 2026-01-14 for $42.18. "
    "It should arrive by 2026-01-19."
)
BROKEN_PR_OUTPUT = (
    "Refunds are usually processed within 5-10 business days. Please check your bank for updates."
)


def _configure_env(db_path: Path) -> None:
    os.environ.update(
        {
            "TESTING": "true",
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "DATABASE_READ_REPLICA_URL": "",
            "AUTH_JWT_SECRET": "money-path-secret-key-for-local-demo",
            "ALLOW_PROJECT_HEADER_CONTEXT": "true",
            "REQUIRE_PROVISIONING_TOKEN": "false",
            "JWT_ISSUER": "",
            "JWT_AUDIENCE": "",
            "PROVIDER_KEY_VAULT_KEK": "money-path-demo-kek-must-be-at-least-32-chars",
            "PROVIDER_KEY_VAULT_KEY_ID": "money-path-local-kek-v1",
            "CELERY_BROKER_URL": "memory://",
            "CELERY_RESULT_BACKEND": "cache+memory://",
            "ENABLE_READY_REDIS_CHECK": "false",
            "INGEST_ENFORCE_RATE_LIMIT": "false",
            "BILLING_ENFORCE_QUOTA": "false",
            "LOG_LEVEL": "CRITICAL",
            "ZROKY_AGENT": "refund-support-agent",
        }
    )


def _assert_response(response: Any, expected_status: int, label: str) -> Any:
    if response.status_code != expected_status:
        raise RuntimeError(
            f"{label} failed: HTTP {response.status_code}: {response.text[:1200]}"
        )
    body = response.json()
    return body


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _seed_project_and_plan(session_local: Any) -> None:
    from app.db.models import Project, Subscription
    from app.services.entitlements import seed_plan_entitlements
    from app.services.entitlements_resolver import invalidate_all

    now = datetime.now(timezone.utc)
    with session_local() as session:
        session.add(
            Project(
                id=PROJECT_ID,
                name="Money Path Demo",
                owner_ref="money-path-owner",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            Subscription(
                id=f"sub-{PROJECT_ID}",
                org_id=PROJECT_ID,
                plan_code="pro",
                status="active",
                seats=1,
                stripe_customer_id=f"cus_{PROJECT_ID}",
                stripe_sub_id=f"si_{PROJECT_ID}",
                current_period_end=now + timedelta(days=30),
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
        seed_plan_entitlements(session, org_id=PROJECT_ID, plan_code="pro")
    invalidate_all()


def _install_background_task_stubs() -> list[tuple[str, str]]:
    import app.api.routes.ingest as ingest_routes

    enqueued: list[tuple[str, str]] = []

    class _DiagnosisTask:
        @staticmethod
        def delay(*_args: Any, **_kwargs: Any) -> Any:
            return types.SimpleNamespace(id="money-path-diagnosis-task")

    class _ReplayTask:
        @staticmethod
        def apply_async(
            args: tuple[str, str],
            queue: str | None = None,
            countdown: int | None = None,
        ) -> None:
            enqueued.append((args[1], args[0]))

    ingest_routes.process_diagnosis = _DiagnosisTask
    sys.modules["app.worker.tasks"] = types.SimpleNamespace(process_replay_run=_ReplayTask)
    return enqueued


def _create_api_key(client: Any) -> tuple[str, str, str]:
    admin_headers = {PROJECT_HEADER: PROJECT_ID}
    body = _assert_response(
        client.post(
            f"/v1/projects/{PROJECT_ID}/api-keys",
            headers=admin_headers,
            json={"name": "money-path-demo-sdk", "scopes": ["project:member"]},
        ),
        201,
        "create API key",
    )
    key_id = str(body["key_id"])
    key_prefix = str(body["key_prefix"])
    raw_key = str(body["api_key"])

    listed = _assert_response(
        client.get(f"/v1/projects/{PROJECT_ID}/api-keys", headers=admin_headers),
        200,
        "list API keys",
    )
    items = listed if isinstance(listed, list) else []
    _assert(
        any(str(item.get("key_id")) == key_id and item.get("revoked") is False for item in items),
        "Created API key was not visible in admin API key list.",
    )
    return raw_key, key_id, key_prefix


def _store_provider_key(client: Any, api_headers: dict[str, str]) -> str:
    body = _assert_response(
        client.post(
            "/v1/providers/keys",
            headers=api_headers,
            json={
                "provider": "openai",
                "plaintext_key": PROVIDER_KEY_PLAINTEXT,
                "label": "money-path-demo",
            },
        ),
        201,
        "store provider key",
    )
    serialized = json.dumps(body, sort_keys=True)
    _assert("ciphertext" not in body, "Provider key response leaked ciphertext.")
    _assert("plaintext_key" not in body, "Provider key response leaked plaintext field.")
    _assert(
        PROVIDER_KEY_PLAINTEXT not in serialized,
        "Provider key response echoed the plaintext key.",
    )
    key_id = str(body["id"])

    listed = _assert_response(
        client.get("/v1/providers/keys?provider=openai", headers=api_headers),
        200,
        "list provider keys",
    )
    _assert(
        any(item.get("id") == key_id and item.get("is_active") is True for item in listed["items"]),
        "Stored provider key was not visible in provider key list.",
    )
    return key_id


class _BackendSdkIngest:
    def __init__(self, client: Any, api_headers: dict[str, str]) -> None:
        self.client = client
        self.api_headers = api_headers
        self.payloads: list[dict[str, Any]] = []

    def enqueue(self, event: Any) -> bool:
        payload = dict(event.to_ingest_payload())
        payload.update(
            {
                "call_id": CALL_ID,
                "event_id": f"{CALL_ID}:sdk",
                "trace_id": TRACE_ID,
                "prompt_fingerprint": PROMPT_FINGERPRINT,
                "estimated_cost_usd": 0.0021,
                "output_content": BAD_OUTPUT,
                "status": "failed",
                "error_code": "TOOL_NOT_CALLED",
                "failure_reason": {
                    "classification": "tool_not_called",
                    "message": f"TOOL_NOT_CALLED: refund status questions require {EXPECTED_TOOL} before answering.",
                    "expected_tool": EXPECTED_TOOL,
                    "observed_tools": [],
                },
                "is_production": True,
                "metadata": {
                    **(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
                    "demo": "money_path",
                    "source": "sdk_ingest",
                },
            }
        )
        payload["tool_calls_made"] = []
        payload["tool_calls"] = []
        payload["tools_available"] = [EXPECTED_TOOL]
        payload["expected_tool"] = EXPECTED_TOOL

        body = _assert_response(
            self.client.post(
                "/api/v1/ingest",
                headers=self.api_headers,
                json={"events": [payload]},
            ),
            202,
            "ingest Python SDK call",
        )
        _assert(body["accepted"] == 1, f"Expected one accepted SDK event, got {body}.")
        self.payloads.append(payload)
        return True


def _fake_sdk_response() -> Any:
    return types.SimpleNamespace(
        usage=types.SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=32,
            input_tokens=None,
            output_tokens=None,
            completion_tokens_details=None,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(
                    content=BAD_OUTPUT,
                    tool_calls=[],
                )
            )
        ],
        model="refund-agent-bad-v1",
    )


def _ingest_sdk_call(client: Any, api_headers: dict[str, str]) -> None:
    import zroky

    sdk_ingest = _BackendSdkIngest(client, api_headers)
    with redirect_stdout(StringIO()):
        zroky.init(
            api_key=api_headers["x-api-key"],
            project=PROJECT_ID,
            mode="cloud",
            mask_pii=False,
            ingest_url="http://zroky-money-path.local",
            agent_framework="python-sdk-money-path-demo",
            workflow_id="refund-status",
            workflow_name="refund-status",
            prompt_version="refund-agent.bad.v1",
            environment="production",
            cache_enabled=False,
            rate_limit_enabled=False,
            timeout_enabled=False,
            retry_max_retries=0,
            fallback_models=[],
        )
        _assert(zroky._queue is not None, "Python SDK queue was not initialized.")
        zroky._queue.enqueue = sdk_ingest.enqueue  # type: ignore[method-assign]
        zroky.record(
            provider="fake-provider",
            model="refund-agent-bad-v1",
            request={
                "messages": [
                    {
                        "role": "user",
                        "content": "Where is my refund?",
                    }
                ],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": EXPECTED_TOOL,
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "customer_id": {"type": "string"},
                                    "order_id": {"type": "string"},
                                },
                                "required": ["customer_id", "order_id"],
                            },
                        },
                    }
                ],
            },
            response=_fake_sdk_response(),
            latency_ms=412,
            trace_id=TRACE_ID,
            workflow_id="refund-status",
            workflow_name="refund-status",
            prompt_version="refund-agent.bad.v1",
            agent_framework="python-sdk-money-path-demo",
            environment="production",
            metadata={"demo": "money_path"},
        )
        zroky.flush()
        zroky.shutdown()
    _assert(len(sdk_ingest.payloads) == 1, "Python SDK did not emit exactly one event.")

    detail = _assert_response(
        client.get(f"/v1/calls/{CALL_ID}", headers=api_headers),
        200,
        "get ingested call detail",
    )
    _assert(detail["call"]["call_id"] == CALL_ID, "Call detail did not return the ingested call.")
    _assert(detail["call"]["provider"] == "fake-provider", "Call provider was not persisted.")
    _assert(detail["call"]["status"] in {"error", "failed"}, "Failed call state was not persisted.")
    _assert(detail["call"]["error_code"] == "TOOL_NOT_CALLED", "Failure code was not visible on the call.")

    health = _assert_response(
        client.get("/v1/capture/health", headers=api_headers),
        200,
        "capture health",
    )
    _assert(health["status"] == "connected", f"Capture health is not connected: {health}.")
    _assert(health["last_call_id"] == CALL_ID, "Capture health did not report the latest call.")
    _assert(health["sdk_events_24h"] >= 1, "Capture health did not count the SDK event.")


def _assert_failure_inbox_contains_issue(
    client: Any,
    api_headers: dict[str, str],
    issue_id: str,
) -> None:
    inbox = _assert_response(
        client.get("/v1/issues?status=open&limit=10", headers=api_headers),
        200,
        "list Failure Inbox issues",
    )
    items = inbox.get("items") if isinstance(inbox, dict) else None
    _assert(isinstance(items, list), "Failure Inbox issue list did not return items.")
    _assert(
        any(item.get("id") == issue_id and item.get("sample_call_id") == CALL_ID for item in items),
        "Issue did not appear in the Failure Inbox issue list.",
    )


def _create_issue(session_local: Any) -> str:
    from app.services.issues import upsert_issue

    with session_local() as session:
        anomaly = upsert_issue(
            session,
            project_id=PROJECT_ID,
            failure_code="TOOL_NOT_CALLED",
            prompt_fingerprint=PROMPT_FINGERPRINT,
            agent_name="refund-support-agent",
            call_id=CALL_ID,
            diagnosis_id="demo-diagnosis-refund-tool",
            occurred_at=datetime.now(timezone.utc),
            call_cost_usd=1260.0,
            evidence={
                "summary": "Refund status request got a generic refund policy answer.",
                "root_cause": f"The refund-status tool was required but {EXPECTED_TOOL} was not called.",
                "failure_reason": f"TOOL_NOT_CALLED: refund status questions require {EXPECTED_TOOL} before answering.",
                "failure_code": "TOOL_NOT_CALLED",
                "expected_tool": EXPECTED_TOOL,
                "observed_tools": [],
                "workflow_name": "refund-status",
                "prompt_version": "refund-agent.bad.v1",
            },
        )
        _assert(anomaly is not None, "Issue upsert did not create an anomaly row.")
        return str(anomaly.id)


def _make_run_trusted(session: Any, run: Any, golden_trace: Any, issue_id: str) -> None:
    from app.db.models import ReplayRunTrace
    from app.services.replay_runs import parse_summary

    now = datetime.now(timezone.utc)
    summary = parse_summary(run.summary_json)
    summary.update(
        {
            "source_kind": "issue",
            "source_id": issue_id,
            "source_issue_id": issue_id,
            "source_call_id": CALL_ID,
            "source_issue_failure_code": "TOOL_NOT_CALLED",
            "source_issue_severity": "critical",
            "source_context": {
                "kind": "issue",
                "id": issue_id,
                "issue_id": issue_id,
                "call_id": CALL_ID,
                "title": "Refund status tool skipped",
                "reason": f"TOOL_NOT_CALLED: refund status questions require {EXPECTED_TOOL} before answering.",
                "failure_code": "TOOL_NOT_CALLED",
                "severity": "critical",
                "affected_agent": "refund-support-agent",
                "affected_workflow": "refund-status",
                "occurrence_count": 1,
                "last_seen_at": now.isoformat(),
                "origin": "issue",
            },
            "requested_replay_mode": "mocked-tool",
            "replay_mode": "mocked-tool",
            "verified_fix": True,
            "verification_status": "verified_fix",
            "trace_count_executed": 1,
            "pass_count": 1,
            "fail_count": 0,
            "error_count": 0,
        }
    )
    run.status = "pass"
    run.started_at = run.started_at or now
    run.completed_at = now
    run.summary_json = json.dumps(summary, separators=(",", ":"), default=str)
    session.add(run)
    session.add(
        ReplayRunTrace(
            id=str(uuid4()),
            replay_run_id=run.id,
            golden_trace_id=golden_trace.id,
            project_id=PROJECT_ID,
            call_id_replayed=CALL_ID,
            status="pass",
            output_text=FIXED_OUTPUT,
            judge_scores_json=json.dumps(
                {"tool_behavior": 1.0, "required_tool_called": True},
                separators=(",", ":"),
            ),
            diff_metric=0.0,
            created_at=now,
            completed_at=now,
        )
    )
    session.commit()
    session.refresh(run)


def _create_verified_issue_replay(session_local: Any, issue_id: str) -> str:
    from sqlalchemy import select

    from app.db.models import GoldenTrace
    from app.services.replay_runs import create_replay_from_issue

    with session_local() as session:
        run = create_replay_from_issue(
            session,
            project_id=PROJECT_ID,
            issue_id=issue_id,
            replay_mode="stub",
        )
        _assert(run is not None, "Issue replay dispatch did not create a run.")
        golden_trace = session.execute(
            select(GoldenTrace)
            .where(
                GoldenTrace.project_id == PROJECT_ID,
                GoldenTrace.golden_set_id == run.golden_set_id,
                GoldenTrace.call_id == CALL_ID,
            )
            .order_by(GoldenTrace.created_at.desc(), GoldenTrace.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        _assert(golden_trace is not None, "Issue replay did not create a golden trace.")
        _make_run_trusted(session, run, golden_trace, issue_id)
        return str(run.id)


def _create_trusted_replay_for_promoted_trace(
    session_local: Any,
    *,
    issue_id: str,
    golden_set_id: str,
    golden_trace_id: str,
) -> str:
    from app.db.models import GoldenTrace, ReplayRun

    now = datetime.now(timezone.utc)
    with session_local() as session:
        trace = session.get(GoldenTrace, golden_trace_id)
        _assert(trace is not None, "Promoted golden trace was not found.")
        run = ReplayRun(
            id=str(uuid4()),
            project_id=PROJECT_ID,
            golden_set_id=golden_set_id,
            trigger="manual",
            status="pass",
            started_at=now,
            completed_at=now,
            summary_json=json.dumps(
                {
                    "source_kind": "issue",
                    "source_id": issue_id,
                    "source_issue_id": issue_id,
                    "source_call_id": CALL_ID,
                    "source_issue_failure_code": "TOOL_NOT_CALLED",
                    "source_issue_severity": "critical",
                    "requested_replay_mode": "mocked-tool",
                    "replay_mode": "mocked-tool",
                    "verified_fix": True,
                    "verification_status": "verified_fix",
                    "trace_count_executed": 1,
                    "pass_count": 1,
                    "fail_count": 0,
                    "error_count": 0,
                },
                separators=(",", ":"),
            ),
            created_at=now,
        )
        session.add(run)
        session.flush()
        _make_run_trusted(session, run, trace, issue_id)
        return str(run.id)


def _mark_ci_gate_failed(
    session_local: Any,
    *,
    ci_run_id: str,
    golden_trace_id: str,
    issue_id: str,
) -> None:
    from app.db.models import GoldenTrace, ReplayRun, ReplayRunTrace
    from app.services.replay_runs import parse_summary

    now = datetime.now(timezone.utc)
    with session_local() as session:
        run = session.get(ReplayRun, ci_run_id)
        trace = session.get(GoldenTrace, golden_trace_id)
        _assert(run is not None, "CI gate replay run was not found.")
        _assert(trace is not None, "CI gate Golden trace was not found.")

        summary = parse_summary(run.summary_json)
        summary.update(
            {
                "source_kind": "issue_ci_gate",
                "source_issue_id": issue_id,
                "source_call_id": CALL_ID,
                "source_issue_failure_code": "TOOL_NOT_CALLED",
                "source_issue_severity": "critical",
                "source_context": {
                    "kind": "issue_ci_gate",
                    "id": issue_id,
                    "issue_id": issue_id,
                    "call_id": CALL_ID,
                    "title": "Refund status tool skipped",
                    "reason": f"Regression: {EXPECTED_TOOL} was not called.",
                    "failure_code": "TOOL_NOT_CALLED",
                    "severity": "critical",
                    "affected_agent": "refund-support-agent",
                    "affected_workflow": "refund-status",
                    "occurrence_count": 1,
                    "last_seen_at": now.isoformat(),
                    "origin": "ci_gate",
                },
                "golden_trace_id": golden_trace_id,
                "requested_replay_mode": "mocked-tool",
                "replay_mode": "mocked-tool",
                "verified_fix": False,
                "verification_status": "regression_failed",
                "trace_count_executed": 1,
                "pass_count": 0,
                "fail_count": 1,
                "error_count": 0,
                "blocked": True,
                "block_reason": "Blocking Golden failed for PR #42.",
                "tool_behavior_diff": {
                    "expected_tool": EXPECTED_TOOL,
                    "candidate_tool_calls": [],
                    "required_tool_called": False,
                },
            }
        )
        run.status = "fail"
        run.started_at = run.started_at or now
        run.completed_at = now
        run.summary_json = json.dumps(summary, separators=(",", ":"), default=str)
        session.add(run)
        session.add(
            ReplayRunTrace(
                id=str(uuid4()),
                replay_run_id=run.id,
                golden_trace_id=trace.id,
                project_id=PROJECT_ID,
                call_id_replayed=CALL_ID,
                status="fail",
                output_text=BROKEN_PR_OUTPUT,
                judge_scores_json=json.dumps(
                    {"tool_behavior": 0.0, "required_tool_called": False, "blocks_ci": True},
                    separators=(",", ":"),
                ),
                diff_metric=1.0,
                created_at=now,
                completed_at=now,
            )
        )
        session.commit()


def _prove_issue_workflow(
    client: Any,
    session_local: Any,
    api_headers: dict[str, str],
    enqueued: list[tuple[str, str]],
) -> dict[str, str]:
    issue_id = _create_issue(session_local)
    _assert_failure_inbox_contains_issue(client, api_headers, issue_id)

    issue = _assert_response(
        client.get(f"/v1/issues/{issue_id}", headers=api_headers),
        200,
        "get issue before replay",
    )
    _assert(issue["sample_call_id"] == CALL_ID, "Issue did not link to the sample call.")
    _assert(issue["replay_coverage_status"] == "not_covered", "Fresh issue should start uncovered.")

    verified_run_id = _create_verified_issue_replay(session_local, issue_id)

    issue_after_replay = _assert_response(
        client.get(f"/v1/issues/{issue_id}", headers=api_headers),
        200,
        "get issue after trusted replay",
    )
    _assert(
        issue_after_replay["replay_coverage_status"] == "verified_fix",
        f"Issue was not marked verified after replay: {issue_after_replay['replay_coverage_status']}",
    )

    promoted = _assert_response(
        client.post(
            f"/v1/issues/{issue_id}/promote-golden",
            headers=api_headers,
            json={
                "expected_output_text": FIXED_OUTPUT,
                "blocks_ci": True,
            },
        ),
        201,
        "promote issue to Golden",
    )
    golden_set_id = str(promoted["golden"]["golden_set_id"])
    golden_trace_id = str(promoted["golden"]["golden_trace_id"])
    _assert(promoted["golden"]["status"] == "active", "Promoted Golden trace is not active.")
    _assert(promoted["golden"]["blocks_ci"] is True, "Promoted Golden set does not block CI.")

    promoted_replay_run_id = _create_trusted_replay_for_promoted_trace(
        session_local,
        issue_id=issue_id,
        golden_set_id=golden_set_id,
        golden_trace_id=golden_trace_id,
    )

    triage = _assert_response(
        client.patch(
            f"/v1/issues/{issue_id}/triage",
            headers=api_headers,
            json={"deploy_pr_url": "https://github.com/acme/refund-agent/pull/42"},
        ),
        200,
        "link deploy PR",
    )
    _assert(triage["deploy_pr_url"].endswith("/pull/42"), "Deploy PR URL was not saved.")

    ci = _assert_response(
        client.post(
            f"/v1/issues/{issue_id}/ci-gate",
            headers=api_headers,
            json={
                "git_sha": "money-path-demo-sha",
                "branch_name": "fix/refund-tool-call",
                "pr_number": 42,
                "commit_message": "Require refund status tool call",
                "replay_mode": "stub",
            },
        ),
        202,
        "dispatch issue CI gate",
    )
    ci_run_id = str(ci["ci_gate"]["run_id"])
    _assert(ci["ci_gate"]["status"] == "pending", "CI gate run did not dispatch as pending.")
    _assert(enqueued == [(ci_run_id, PROJECT_ID)], f"Replay worker enqueue mismatch: {enqueued!r}")
    _mark_ci_gate_failed(
        session_local,
        ci_run_id=ci_run_id,
        golden_trace_id=golden_trace_id,
        issue_id=issue_id,
    )

    blocked_issue = _assert_response(
        client.get(f"/v1/issues/{issue_id}", headers=api_headers),
        200,
        "get issue after failed CI gate",
    )
    _assert(
        blocked_issue["proof"]["golden"]["blocks_ci"] is True,
        "Promoted Golden is not marked as CI-blocking.",
    )
    _assert(
        blocked_issue["proof"]["ci_gate"]["run_id"] == ci_run_id,
        "Issue proof did not point at the CI gate run.",
    )
    _assert(
        blocked_issue["proof"]["ci_gate"]["status"] == "fail",
        "Failed blocking Golden did not mark the CI gate as failed.",
    )

    return {
        "issue_id": issue_id,
        "replay_run_id": verified_run_id,
        "promoted_replay_run_id": promoted_replay_run_id,
        "golden_set_id": golden_set_id,
        "golden_trace_id": golden_trace_id,
        "ci_run_id": ci_run_id,
    }


def _run_flow(client: Any, session_local: Any, enqueued: list[tuple[str, str]]) -> dict[str, str]:
    _seed_project_and_plan(session_local)
    api_key, api_key_id, api_key_prefix = _create_api_key(client)
    api_headers = {"x-api-key": api_key}
    provider_key_id = _store_provider_key(client, api_headers)
    _ingest_sdk_call(client, api_headers)
    issue_state = _prove_issue_workflow(client, session_local, api_headers, enqueued)
    return {
        "project_id": PROJECT_ID,
        "api_key_id": api_key_id,
        "api_key_prefix": api_key_prefix,
        "provider_key_id": provider_key_id,
        "call_id": CALL_ID,
        **issue_state,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="zroky-money-path-") as temp_dir:
        db_path = Path(temp_dir) / "money_path_demo.db"
        _configure_env(db_path)
        logging.disable(logging.CRITICAL)
        sys.path.insert(0, str(BACKEND_DIR))
        sys.path.insert(0, str(SDK_DIR))

        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.core.config import get_settings
        from app.db.base import Base
        from app.db.session import get_db_session, get_db_session_read
        from app.main import app
        from app.services.entitlements_resolver import invalidate_all

        get_settings.cache_clear()
        invalidate_all()

        engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        session_local = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            future=True,
        )
        Base.metadata.create_all(bind=engine)

        def override_get_db_session() -> Any:
            session = session_local()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db_session] = override_get_db_session
        app.dependency_overrides[get_db_session_read] = override_get_db_session
        enqueued = _install_background_task_stubs()

        try:
            client = TestClient(app)
            try:
                result = _run_flow(client, session_local, enqueued)
            finally:
                client.close()
        finally:
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)
            engine.dispose()
            invalidate_all()
            get_settings.cache_clear()

    print(f"project_id={result['project_id']}")
    print(f"api_key_id={result['api_key_id']}")
    print(f"api_key_prefix={result['api_key_prefix']}")
    print(f"provider_key_id={result['provider_key_id']}")
    print(f"call_id={result['call_id']}")
    print(f"issue_id={result['issue_id']}")
    print(f"replay_run_id={result['replay_run_id']}")
    print(f"golden_set_id={result['golden_set_id']}")
    print(f"golden_trace_id={result['golden_trace_id']}")
    print(f"ci_run_id={result['ci_run_id']}")
    print("[money-path] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
