from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


DEFAULT_API_BASE_URL = "https://api.zroky.com"
DEFAULT_DASHBOARD_URL = "https://app.zroky.com"
DEFAULT_LANDING_URL = "https://zroky.com"


@dataclass
class HttpResult:
    status: int
    text: str
    body: Any
    headers: dict[str, str]
    set_cookies: list[str]
    final_url: str


class SmokeFailure(RuntimeError):
    pass


def _json_or_none(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> HttpResult:
    request_headers = dict(headers or {})
    data: bytes | None = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    attempts = 3 if method.upper() in {"GET", "HEAD"} else 1
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url=url, method=method, headers=request_headers, data=data)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
                return HttpResult(
                    status=response.status,
                    text=text,
                    body=_json_or_none(text),
                    headers={k.lower(): v for k, v in response.headers.items()},
                    set_cookies=response.headers.get_all("Set-Cookie") or [],
                    final_url=response.geturl(),
                )
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return HttpResult(
                status=exc.code,
                text=text,
                body=_json_or_none(text),
                headers={k.lower(): v for k, v in exc.headers.items()},
                set_cookies=exc.headers.get_all("Set-Cookie") or [],
                final_url=url,
            )
        except (http.client.IncompleteRead, urllib.error.URLError) as exc:
            if attempt >= attempts:
                reason = getattr(exc, "reason", None) or str(exc)
                raise SmokeFailure(f"{method} {url} failed: {reason}") from exc
            time.sleep(0.75 * attempt)

    raise SmokeFailure(f"{method} {url} failed after {attempts} attempts")


def _pass(label: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[PASS] {label}{suffix}")


def _fail(label: str, detail: str) -> None:
    raise SmokeFailure(f"{label}: {detail}")


def _expect_status(result: HttpResult, expected: int | set[int], label: str) -> None:
    expected_set = {expected} if isinstance(expected, int) else expected
    if result.status not in expected_set:
        _fail(label, f"expected HTTP {sorted(expected_set)}, got {result.status}: {result.text[:600]}")


def _require_json_object(result: HttpResult, label: str) -> dict[str, Any]:
    if not isinstance(result.body, dict):
        _fail(label, f"expected JSON object, got: {result.text[:600]}")
    return result.body


def _check_health(api_base_url: str, timeout: float) -> None:
    live = _request("GET", _url(api_base_url, "/health/live"), timeout=timeout)
    _expect_status(live, 200, "backend /health/live")
    live_body = _require_json_object(live, "backend /health/live")
    if live_body.get("status") != "ok":
        _fail("backend /health/live", f"status was {live_body.get('status')!r}")
    _pass("backend /health/live", "status=ok")

    ready = _request("GET", _url(api_base_url, "/health/ready"), timeout=timeout)
    _expect_status(ready, 200, "backend /health/ready")
    ready_body = _require_json_object(ready, "backend /health/ready")
    checks = ready_body.get("checks") if isinstance(ready_body.get("checks"), dict) else {}
    if ready_body.get("status") != "ok" or checks.get("database") != "ok" or checks.get("redis") != "ok":
        _fail("backend /health/ready", f"body={ready.text[:600]}")
    _pass("backend /health/ready", "database=ok redis=ok")


def _provision_project(
    api_base_url: str,
    *,
    provisioning_token: str,
    provisioning_header: str,
    timeout: float,
) -> tuple[str, str, str]:
    no_token = _request(
        "POST",
        _url(api_base_url, "/v1/projects"),
        payload={"name": f"DeploySmokeNoToken-{int(time.time())}"},
        timeout=timeout,
    )
    _expect_status(no_token, 401, "backend provisioning guard")
    _pass("backend provisioning guard", "missing token rejected with 401")

    stamp = int(time.time())
    project = _request(
        "POST",
        _url(api_base_url, "/v1/projects"),
        headers={provisioning_header: provisioning_token},
        payload={
            "name": f"DeploySmoke-{stamp}",
            "owner_ref": f"deploy-smoke-{stamp}@zroky.local",
        },
        timeout=timeout,
    )
    _expect_status(project, 201, "backend create smoke project")
    project_body = _require_json_object(project, "backend create smoke project")
    project_id = str(project_body.get("project_id") or "")
    if not project_id.startswith("proj_"):
        _fail("backend create smoke project", f"unexpected project_id={project_id!r}")
    _pass("backend create smoke project", f"project_id={project_id}")

    api_key_response = _request(
        "POST",
        _url(api_base_url, f"/v1/projects/{project_id}/api-keys"),
        headers={provisioning_header: provisioning_token},
        payload={"name": "deployment-smoke", "scopes": ["project:member"]},
        timeout=timeout,
    )
    _expect_status(api_key_response, 201, "backend create smoke API key")
    api_key_body = _require_json_object(api_key_response, "backend create smoke API key")
    api_key = str(api_key_body.get("api_key") or "")
    api_key_id = str(api_key_body.get("key_id") or "")
    if not api_key or not api_key_id:
        _fail("backend create smoke API key", "response did not include api_key/key_id")
    _pass("backend create smoke API key", f"api_key_id={api_key_id}")
    return project_id, api_key, api_key_id


def _create_project_api_key(
    api_base_url: str,
    *,
    project_id: str,
    provisioning_token: str,
    provisioning_header: str,
    name: str,
    timeout: float,
) -> tuple[str, str, str]:
    response = _request(
        "POST",
        _url(api_base_url, f"/v1/projects/{project_id}/api-keys"),
        headers={provisioning_header: provisioning_token},
        payload={"name": name, "scopes": ["project:member"], "expires_in_days": 30},
        timeout=timeout,
    )
    _expect_status(response, 201, "backend create lifecycle API key")
    body = _require_json_object(response, "backend create lifecycle API key")
    raw_key = str(body.get("api_key") or "")
    key_id = str(body.get("key_id") or "")
    key_prefix = str(body.get("key_prefix") or "")
    scopes = body.get("scopes")
    if not raw_key.startswith("zk_live_") or not key_id or not key_prefix or not raw_key.startswith(key_prefix):
        _fail("backend create lifecycle API key", "response did not include a valid one-time key/key_id/prefix")
    if scopes != ["project:member"]:
        _fail("backend create lifecycle API key", f"expected project:member scope, got {scopes!r}")
    _pass("backend create lifecycle API key", f"api_key_id={key_id} prefix={key_prefix}...")
    return raw_key, key_id, key_prefix


def _list_project_api_keys(
    api_base_url: str,
    *,
    project_id: str,
    provisioning_token: str,
    provisioning_header: str,
    timeout: float,
) -> list[dict[str, Any]]:
    response = _request(
        "GET",
        _url(api_base_url, f"/v1/projects/{project_id}/api-keys"),
        headers={provisioning_header: provisioning_token},
        timeout=timeout,
    )
    _expect_status(response, 200, "backend list API keys")
    if not isinstance(response.body, list):
        _fail("backend list API keys", f"expected JSON list, got: {response.text[:600]}")
    return [item for item in response.body if isinstance(item, dict)]


def _require_api_key_metadata(
    items: list[dict[str, Any]],
    *,
    key_id: str,
    raw_key: str,
    label: str,
    revoked: bool | None = None,
    last_used: bool | None = None,
) -> dict[str, Any]:
    serialized = json.dumps(items, separators=(",", ":"), sort_keys=True)
    if raw_key in serialized:
        _fail(label, "API key list leaked raw secret material")
    item = next((entry for entry in items if str(entry.get("key_id") or "") == key_id), None)
    if item is None:
        _fail(label, f"key_id={key_id} not found in key list")
    if "api_key" in item:
        _fail(label, "API key metadata response included api_key")
    if revoked is not None and bool(item.get("revoked")) is not revoked:
        _fail(label, f"expected revoked={revoked}, got {item.get('revoked')!r}")
    if last_used is not None:
        has_last_used = bool(item.get("last_used_at"))
        if has_last_used is not last_used:
            _fail(label, f"expected last_used={last_used}, got last_used_at={item.get('last_used_at')!r}")
    return item


def _ingest_lifecycle_call(api_base_url: str, *, api_key: str, label: str, timeout: float) -> str:
    call_id = f"call_deploy_key_{label}_{uuid4().hex[:14]}"
    trace_id = f"trace_deploy_key_{label}_{uuid4().hex[:14]}"
    event = {
        "schema_version": "v2",
        "call_id": call_id,
        "event_id": f"{call_id}:event",
        "trace_id": trace_id,
        "provider": "deployment-key-smoke",
        "model": "deployment-key-smoke-model",
        "call_type": "chat",
        "status": "failed",
        "latency_ms": 456,
        "prompt_tokens": 72,
        "completion_tokens": 18,
        "estimated_cost_usd": 0.001,
        "agent_name": "deployment-key-smoke-agent",
        "workflow_name": "deployment-key-smoke",
        "prompt_fingerprint": "fp-deployment-key-smoke",
        "prompt_version": "deploy-key-smoke-v1",
        "environment": "production",
        "is_production": True,
        "output_content": "{\"status\":\"failed\",\"reason\":\"deployment-key-smoke\"}",
        "error_message": "Synthetic deployment key lifecycle failure",
        "tool_calls": [{"name": "deployment_key_smoke_tool", "args": {"ok": False}}],
        "metadata": {"source": "deployment_key_lifecycle_smoke"},
    }
    ingest = _request(
        "POST",
        _url(api_base_url, "/v1/ingest"),
        headers={"x-api-key": api_key, "X-Idempotency-Key": f"{call_id}:idem"},
        payload={"events": [event]},
        timeout=timeout,
    )
    _expect_status(ingest, 202, f"backend API key ingest {label}")
    ingest_body = _require_json_object(ingest, f"backend API key ingest {label}")
    if ingest_body.get("accepted") != 1 or ingest_body.get("queued") != 1:
        _fail(f"backend API key ingest {label}", f"expected accepted=1 queued=1, got {ingest.text[:600]}")
    call = _request(
        "GET",
        _url(api_base_url, f"/v1/calls/{call_id}"),
        headers={"x-api-key": api_key},
        timeout=timeout,
    )
    _expect_status(call, 200, f"backend API key call detail {label}")
    call_body = _require_json_object(call, f"backend API key call detail {label}")
    call_payload = call_body.get("call") if isinstance(call_body.get("call"), dict) else call_body
    if call_payload.get("call_id") != call_id:
        _fail(f"backend API key call detail {label}", f"unexpected call detail body: {call.text[:600]}")
    _pass(f"backend API key lifecycle ingest {label}", f"call_id={call_id}")
    return call_id


def _check_api_key_lifecycle(
    api_base_url: str,
    *,
    project_id: str,
    provisioning_token: str,
    provisioning_header: str,
    timeout: float,
) -> dict[str, str]:
    raw_a, key_a_id, key_a_prefix = _create_project_api_key(
        api_base_url,
        project_id=project_id,
        provisioning_token=provisioning_token,
        provisioning_header=provisioning_header,
        name="deployment-key-lifecycle-a",
        timeout=timeout,
    )
    items = _list_project_api_keys(
        api_base_url,
        project_id=project_id,
        provisioning_token=provisioning_token,
        provisioning_header=provisioning_header,
        timeout=timeout,
    )
    _require_api_key_metadata(
        items,
        key_id=key_a_id,
        raw_key=raw_a,
        label="backend API key metadata before use",
        revoked=False,
        last_used=False,
    )
    call_a_id = _ingest_lifecycle_call(api_base_url, api_key=raw_a, label="a", timeout=timeout)

    items = _list_project_api_keys(
        api_base_url,
        project_id=project_id,
        provisioning_token=provisioning_token,
        provisioning_header=provisioning_header,
        timeout=timeout,
    )
    _require_api_key_metadata(
        items,
        key_id=key_a_id,
        raw_key=raw_a,
        label="backend API key metadata after use",
        revoked=False,
        last_used=True,
    )

    rotated = _request(
        "POST",
        _url(api_base_url, f"/v1/projects/{project_id}/api-keys/{key_a_id}/rotate"),
        headers={provisioning_header: provisioning_token},
        timeout=timeout,
    )
    _expect_status(rotated, 200, "backend rotate API key")
    rotated_body = _require_json_object(rotated, "backend rotate API key")
    raw_b = str(rotated_body.get("api_key") or "")
    key_b_id = str(rotated_body.get("key_id") or "")
    key_b_prefix = str(rotated_body.get("key_prefix") or "")
    if not raw_b.startswith("zk_live_") or not key_b_id or key_b_id == key_a_id:
        _fail("backend rotate API key", "replacement key material was invalid")
    if str(rotated_body.get("rotated_from_key_id") or "") != key_a_id:
        _fail("backend rotate API key", "replacement key did not link to rotated key")
    _pass("backend rotate API key", f"old_key_id={key_a_id} new_key_id={key_b_id}")

    old_reuse = _request(
        "GET",
        _url(api_base_url, f"/v1/calls/{call_a_id}"),
        headers={"x-api-key": raw_a},
        timeout=timeout,
    )
    _expect_status(old_reuse, 401, "backend rotated API key rejected")
    _pass("backend rotated API key rejected", f"key_id={key_a_id}")

    call_b_id = _ingest_lifecycle_call(api_base_url, api_key=raw_b, label="b", timeout=timeout)
    items = _list_project_api_keys(
        api_base_url,
        project_id=project_id,
        provisioning_token=provisioning_token,
        provisioning_header=provisioning_header,
        timeout=timeout,
    )
    _require_api_key_metadata(
        items,
        key_id=key_b_id,
        raw_key=raw_b,
        label="backend replacement API key metadata after use",
        revoked=False,
        last_used=True,
    )

    revoked = _request(
        "POST",
        _url(api_base_url, f"/v1/projects/{project_id}/api-keys/{key_b_id}/revoke"),
        headers={provisioning_header: provisioning_token},
        timeout=timeout,
    )
    _expect_status(revoked, 200, "backend revoke replacement API key")
    revoked_body = _require_json_object(revoked, "backend revoke replacement API key")
    if revoked_body.get("revoked") is not True:
        _fail("backend revoke replacement API key", f"expected revoked=true, got {revoked.text[:600]}")
    rejected = _request(
        "GET",
        _url(api_base_url, f"/v1/calls/{call_b_id}"),
        headers={"x-api-key": raw_b},
        timeout=timeout,
    )
    _expect_status(rejected, 401, "backend revoked API key rejected")
    _pass("backend revoked API key rejected", f"key_id={key_b_id}")

    return {
        "api_key_lifecycle_key_a_id": key_a_id,
        "api_key_lifecycle_key_a_prefix": f"{key_a_prefix}...",
        "api_key_lifecycle_key_b_id": key_b_id,
        "api_key_lifecycle_key_b_prefix": f"{key_b_prefix}...",
        "api_key_lifecycle_call_a_id": call_a_id,
        "api_key_lifecycle_call_b_id": call_b_id,
    }


def _run_railway_python(
    remote_code: str,
    *,
    env: dict[str, str],
    service: str,
    environment: str,
    timeout: float,
    label: str,
) -> str:
    railway_exe = shutil.which("railway.cmd") or shutil.which("railway") or "railway"
    remote_payload = base64.b64encode(remote_code.encode("utf-8")).decode("ascii")
    bootstrap = (
        "import base64;"
        f"exec(base64.b64decode('{remote_payload}').decode('utf-8'))"
    )
    remote_env = " ".join(f"{key}={shlex.quote(value)}" for key, value in env.items())
    remote_shell_command = f"{remote_env} python -c {shlex.quote(bootstrap)}".strip()
    command = [
        railway_exe,
        "ssh",
        "--service",
        service,
        "--environment",
        environment,
        remote_shell_command,
    ]
    completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
    if completed.returncode != 0:
        _fail(
            label,
            (completed.stderr or completed.stdout or f"exit={completed.returncode}")[:1200],
        )
    return completed.stdout.strip()


def _grant_pro_with_railway_ssh(project_id: str, *, service: str, environment: str, timeout: float) -> None:
    remote_code = r"""
import os
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select
from app.db.models import Subscription
from app.db.session import SessionLocal
from app.services.entitlements import seed_plan_entitlements
from app.services import entitlements_resolver

project_id = os.environ["PROJECT_ID"]
now = datetime.now(timezone.utc)
subscription_columns = set(Subscription.__mapper__.attrs.keys())


def subscription_values(**values):
    return {key: value for key, value in values.items() if key in subscription_columns}


with SessionLocal() as db:
    sub = db.execute(select(Subscription).where(Subscription.org_id == project_id)).scalar_one_or_none()
    if sub is None:
        sub = Subscription(**subscription_values(
            id=str(uuid4()),
            org_id=project_id,
            payment_customer_ref=None,
            payment_subscription_ref=None,
            plan_code="pro",
            status="active",
            seats=3,
            current_period_end=now + timedelta(days=30),
            trial_end=None,
            sla_tier="none",
            created_at=now,
            updated_at=now,
        ))
        db.add(sub)
    else:
        for key, value in subscription_values(
            plan_code="pro",
            status="active",
            current_period_end=now + timedelta(days=30),
            updated_at=now,
        ).items():
            setattr(sub, key, value)
        db.add(sub)
    seed_plan_entitlements(db, org_id=project_id, plan_code="pro", commit=False)
    db.commit()
entitlements_resolver.invalidate(project_id)
with SessionLocal() as db:
    sub = db.execute(select(Subscription).where(Subscription.org_id == project_id)).scalar_one()
    enabled = entitlements_resolver.has(db, project_id, "pilot.autopilot_enabled")
    print(f"granted_pro={project_id} plan={sub.plan_code} autopilot={enabled}")
"""
    detail = f"project_id={project_id}"
    output = _run_railway_python(
        remote_code,
        env={"PROJECT_ID": project_id},
        service=service,
        environment=environment,
        timeout=timeout,
        label="railway pro entitlement grant",
    )
    if output:
        detail = output.splitlines()[-1][:200]
    _pass("railway pro entitlement grant", detail)


def _check_billing_plan(api_base_url: str, *, api_key: str, expected_plan: str, timeout: float) -> None:
    billing = _request(
        "GET",
        _url(api_base_url, "/v1/billing/me"),
        headers={"x-api-key": api_key},
        timeout=timeout,
    )
    _expect_status(billing, 200, "backend billing plan")
    body = _require_json_object(billing, "backend billing plan")
    plan_code = str(body.get("plan_code") or "")
    template = body.get("plan_template") if isinstance(body.get("plan_template"), dict) else {}
    if plan_code != expected_plan or template.get("pilot.autopilot_enabled") is not True:
        _fail("backend billing plan", f"expected {expected_plan}/autopilot=true, got {billing.text[:600]}")
    _pass("backend billing plan", f"plan_code={plan_code} autopilot=true")


def _ingest_call(api_base_url: str, *, api_key: str, timeout: float) -> str:
    call_id = f"call_deploy_smoke_{uuid4().hex[:18]}"
    trace_id = f"trace_deploy_smoke_{uuid4().hex[:18]}"
    event = {
        "schema_version": "v2",
        "call_id": call_id,
        "event_id": f"{call_id}:event",
        "trace_id": trace_id,
        "provider": "fake-provider",
        "model": "deployment-smoke-model",
        "call_type": "chat",
        "status": "completed",
        "latency_ms": 321,
        "prompt_tokens": 84,
        "completion_tokens": 22,
        "estimated_cost_usd": 0.001,
        "agent_name": "deployment-smoke-agent",
        "workflow_name": "deployment-smoke",
        "prompt_fingerprint": "fp-deployment-smoke",
        "prompt_version": "deploy-smoke-v1",
        "environment": "production",
        "is_production": True,
        "output_content": "{\"status\":\"smoke-ok\"}",
        "tool_calls": [{"name": "deployment_smoke_tool", "args": {"ok": True}}],
        "metadata": {"source": "phase_8_deployment_smoke"},
    }
    ingest = _request(
        "POST",
        _url(api_base_url, "/v1/ingest"),
        headers={"x-api-key": api_key, "X-Idempotency-Key": f"{call_id}:idem"},
        payload={"events": [event]},
        timeout=timeout,
    )
    _expect_status(ingest, 202, "backend /v1/ingest")
    ingest_body = _require_json_object(ingest, "backend /v1/ingest")
    if ingest_body.get("accepted") != 1:
        _fail("backend /v1/ingest", f"expected accepted=1, got {ingest.text[:600]}")
    _pass("backend /v1/ingest", f"call_id={call_id}")

    call = _request("GET", _url(api_base_url, f"/v1/calls/{call_id}"), headers={"x-api-key": api_key}, timeout=timeout)
    _expect_status(call, 200, "backend ingested call detail")
    _pass("backend ingested call detail", f"call_id={call_id}")
    return call_id


def _seed_issue_with_railway_ssh(
    project_id: str,
    call_id: str,
    *,
    service: str,
    environment: str,
    timeout: float,
) -> str:
    remote_code = r"""
import os
from app.db.session import SessionLocal
from app.services.anomalies import upsert_anomaly

project_id = os.environ["PROJECT_ID"]
call_id = os.environ["CALL_ID"]
with SessionLocal() as db:
    anomaly = upsert_anomaly(
        db,
        project_id=project_id,
        detector="SCHEMA_VIOLATION",
        prompt_fingerprint="fp-deployment-smoke",
        agent_name="deployment-smoke-agent",
        call_id=call_id,
        evidence={
            "failure_code": "SCHEMA_VIOLATION",
            "prompt_fingerprint": "fp-deployment-smoke",
            "agent_name": "deployment-smoke-agent",
            "blast_radius_usd": 0.01,
            "legacy_issue": {
                "failure_code": "SCHEMA_VIOLATION",
                "prompt_fingerprint": "fp-deployment-smoke",
                "agent_name": "deployment-smoke-agent",
                "sample_call_id": call_id,
                "sample_diagnosis_id": f"diag-{call_id}",
                "blast_radius_usd": 0.01,
                "sample_evidence_json": "{\"source\":\"deployment-smoke\"}",
                "last_fix_id": None,
                "resolved_at": None,
                "resolution_source": None,
            },
        },
    )
    if anomaly is None:
        raise RuntimeError("anomaly upsert returned None")
    print(f"issue_id={anomaly.id}")
"""
    output = _run_railway_python(
        remote_code,
        env={"PROJECT_ID": project_id, "CALL_ID": call_id},
        service=service,
        environment=environment,
        timeout=timeout,
        label="railway issue seed",
    )
    issue_id = ""
    if output:
        last_line = output.splitlines()[-1].strip()
        if last_line.startswith("issue_id="):
            issue_id = last_line.split("=", 1)[1]
    if not issue_id:
        _fail("railway issue seed", f"missing issue_id in output: {output[:600]}")
    _pass("railway issue seed", f"issue_id={issue_id}")
    return issue_id


def _check_issues(api_base_url: str, *, api_key: str, expected_issue_id: str | None, timeout: float) -> None:
    issues = _request(
        "GET",
        _url(api_base_url, "/v1/issues?status=open&limit=10"),
        headers={"x-api-key": api_key},
        timeout=timeout,
    )
    _expect_status(issues, 200, "backend /v1/issues")
    body = _require_json_object(issues, "backend /v1/issues")
    if not isinstance(body.get("items"), list):
        _fail("backend /v1/issues", f"response missing items list: {issues.text[:600]}")
    if expected_issue_id is not None:
        if not any(isinstance(item, dict) and item.get("id") == expected_issue_id for item in body["items"]):
            _fail("backend /v1/issues", f"seeded issue_id={expected_issue_id} not visible: {issues.text[:600]}")
    _pass("backend /v1/issues", f"items={len(body['items'])}")


def _check_provider_vault(api_base_url: str, *, api_key: str, timeout: float) -> str:
    plaintext = f"sk-deployment-smoke-{uuid4().hex}"
    create = _request(
        "POST",
        _url(api_base_url, "/v1/providers/keys"),
        headers={"x-api-key": api_key},
        payload={"provider": "openai", "plaintext_key": plaintext, "label": "deployment-smoke"},
        timeout=timeout,
    )
    _expect_status(create, 201, "backend provider key create")
    body = _require_json_object(create, "backend provider key create")
    serialized = json.dumps(body, sort_keys=True)
    if plaintext in serialized or "plaintext_key" in body or "ciphertext" in body:
        _fail("backend provider key create", "provider key response leaked secret material")
    key_id = str(body.get("id") or "")
    if not key_id:
        _fail("backend provider key create", "missing provider key id")
    _pass("backend provider key create", f"provider_key_id={key_id}")

    listed = _request(
        "GET",
        _url(api_base_url, "/v1/providers/keys?provider=openai"),
        headers={"x-api-key": api_key},
        timeout=timeout,
    )
    _expect_status(listed, 200, "backend provider key list")
    list_body = _require_json_object(listed, "backend provider key list")
    items = list_body.get("items")
    if not isinstance(items, list) or not any(isinstance(item, dict) and item.get("id") == key_id for item in items):
        _fail("backend provider key list", f"created key not visible: {listed.text[:600]}")
    _pass("backend provider key list", f"total_in_page={list_body.get('total_in_page')}")

    detail = _request(
        "GET",
        _url(api_base_url, f"/v1/providers/keys/{key_id}"),
        headers={"x-api-key": api_key},
        timeout=timeout,
    )
    _expect_status(detail, 200, "backend provider key detail")
    _pass("backend provider key detail", "metadata only")

    revoked = _request(
        "DELETE",
        _url(api_base_url, f"/v1/providers/keys/{key_id}"),
        headers={"x-api-key": api_key},
        timeout=timeout,
    )
    _expect_status(revoked, 200, "backend provider key revoke")
    revoke_body = _require_json_object(revoked, "backend provider key revoke")
    if revoke_body.get("is_active") is not False:
        _fail("backend provider key revoke", f"expected is_active=false: {revoked.text[:600]}")
    _pass("backend provider key revoke", f"provider_key_id={key_id}")
    return key_id


def _check_replay_and_ci(
    api_base_url: str,
    *,
    api_key: str,
    call_id: str,
    expect_plan_gate: bool,
    timeout: float,
) -> dict[str, str | None]:
    ids: dict[str, str | None] = {
        "golden_set_id": None,
        "golden_trace_id": None,
        "replay_run_id": None,
        "golden_run_id": None,
        "ci_run_id": None,
    }

    if expect_plan_gate:
        replay = _request(
            "POST",
            _url(api_base_url, f"/v1/replay/runs/from-call/{call_id}"),
            headers={"x-api-key": api_key},
            payload={"replay_mode": "stub"},
            timeout=timeout,
        )
        _expect_status(replay, 402, "backend replay dispatch plan gate")
        _pass("backend replay dispatch plan gate", "free project returned 402")
        ci = _request(
            "POST",
            _url(api_base_url, "/v1/regression-ci/run"),
            headers={"x-api-key": api_key},
            payload={"git_sha": "deploy-smoke-gate", "changed_files": [{"path": "agents/smoke.py", "hunks": ""}]},
            timeout=timeout,
        )
        _expect_status(ci, 402, "backend regression CI plan gate")
        _pass("backend regression CI plan gate", "free project returned 402")
        return ids

    golden = _request(
        "POST",
        _url(api_base_url, "/v1/goldens"),
        headers={"x-api-key": api_key},
        payload={
            "name": f"Deployment smoke {uuid4().hex[:8]}",
            "description": "Synthetic Golden set created by Phase 8 deployment smoke.",
            "judge_config_json": json.dumps({"owner": "deployment-smoke"}, separators=(",", ":")),
        },
        timeout=timeout,
    )
    _expect_status(golden, 201, "backend Golden set create")
    golden_body = _require_json_object(golden, "backend Golden set create")
    golden_set_id = str(golden_body.get("id") or "")
    ids["golden_set_id"] = golden_set_id
    _pass("backend Golden set create", f"golden_set_id={golden_set_id}")

    patch = _request(
        "PATCH",
        _url(api_base_url, f"/v1/goldens/{golden_set_id}"),
        headers={"x-api-key": api_key},
        payload={"blocks_ci": True},
        timeout=timeout,
    )
    _expect_status(patch, 200, "backend Golden set blocking toggle")
    _pass("backend Golden set blocking toggle", "blocks_ci=true")

    trace = _request(
        "POST",
        _url(api_base_url, f"/v1/goldens/{golden_set_id}/traces"),
        headers={"x-api-key": api_key},
        payload={
            "call_id": call_id,
            "status": "active",
            "expected_output_text": "{\"status\":\"smoke-ok\"}",
            "source_output_text": "{\"status\":\"smoke-ok\"}",
            "source_evidence_json": json.dumps({"source": "deployment-smoke", "call_id": call_id}, separators=(",", ":")),
            "expected_tokens": 22,
            "expected_cost_usd": 0.001,
            "expected_latency_ms": 321,
            "criteria_json": json.dumps({"must_contain": "smoke-ok"}, separators=(",", ":")),
            "weight": 1.0,
        },
        timeout=timeout,
    )
    _expect_status(trace, 201, "backend Golden trace create")
    trace_body = _require_json_object(trace, "backend Golden trace create")
    golden_trace_id = str(trace_body.get("id") or "")
    ids["golden_trace_id"] = golden_trace_id
    _pass("backend Golden trace create", f"golden_trace_id={golden_trace_id}")

    replay = _request(
        "POST",
        _url(api_base_url, f"/v1/replay/runs/from-call/{call_id}"),
        headers={"x-api-key": api_key},
        payload={"replay_mode": "stub"},
        timeout=timeout,
    )
    _expect_status(replay, 202, "backend replay dispatch from call")
    replay_body = _require_json_object(replay, "backend replay dispatch from call")
    ids["replay_run_id"] = str(replay_body.get("id") or "")
    _pass("backend replay dispatch from call", f"replay_run_id={ids['replay_run_id']}")

    golden_run = _request(
        "POST",
        _url(api_base_url, f"/v1/goldens/{golden_set_id}/run"),
        headers={"x-api-key": api_key},
        payload={
            "trigger": "github",
            "git_sha": "deploy-smoke-golden",
            "branch_name": "deploy/smoke",
            "pr_number": 8,
            "commit_message": "Phase 8 deployment smoke",
            "replay_mode": "stub",
        },
        timeout=timeout,
    )
    _expect_status(golden_run, 202, "backend Golden CI dispatch")
    golden_run_body = _require_json_object(golden_run, "backend Golden CI dispatch")
    ids["golden_run_id"] = str(golden_run_body.get("id") or "")
    _pass("backend Golden CI dispatch", f"golden_run_id={ids['golden_run_id']}")

    ci = _request(
        "POST",
        _url(api_base_url, "/v1/regression-ci/run"),
        headers={"x-api-key": api_key},
        payload={
            "git_sha": "deploy-smoke-regression",
            "changed_files": [{"path": "agents/refund_support/prompt.md", "hunks": ""}],
            "operator_override": {"category": "system_prompt", "target": "deployment-smoke-agent"},
            "target_total_cap": 1,
        },
        timeout=timeout,
    )
    _expect_status(ci, 202, "backend regression CI dispatch")
    ci_body = _require_json_object(ci, "backend regression CI dispatch")
    ids["ci_run_id"] = str(ci_body.get("run_id") or "")
    _pass("backend regression CI dispatch", f"ci_run_id={ids['ci_run_id']}")

    return ids


def _check_dashboard(dashboard_url: str, timeout: float) -> None:
    login = _request("GET", _url(dashboard_url, "/login"), timeout=timeout)
    _expect_status(login, 200, "dashboard login page")
    login_markers = ("auth-shell", "auth-form-panel", "__next_f")
    missing_login_markers = [marker for marker in login_markers if marker not in login.text]
    if missing_login_markers:
        _fail("dashboard login page", f"missing render markers: {missing_login_markers}")
    _pass("dashboard login page", login.final_url)

    signup = _request("GET", _url(dashboard_url, "/signup"), timeout=timeout)
    _expect_status(signup, 200, "dashboard signup page")
    signup_markers = ("auth-shell", "auth-form-panel", "__next_f")
    missing_signup_markers = [marker for marker in signup_markers if marker not in signup.text]
    if missing_signup_markers:
        _fail("dashboard signup page", f"missing render markers: {missing_signup_markers}")
    _pass("dashboard signup page", signup.final_url)

    proxy = _request("GET", _url(dashboard_url, "/api/zroky/health/live"), timeout=timeout)
    _expect_status(proxy, 200, "dashboard API proxy")
    proxy_body = _require_json_object(proxy, "dashboard API proxy")
    if proxy_body.get("status") != "ok":
        _fail("dashboard API proxy", f"unexpected body: {proxy.text[:600]}")
    _pass("dashboard API proxy", "backend health proxied")

    session = _request(
        "POST",
        _url(dashboard_url, "/api/auth/set-session"),
        payload={
            "access_token": "deploy-smoke-access-token",
            "refresh_token": "deploy-smoke-refresh-token",
            "access_max_age_seconds": 60,
            "refresh_max_age_seconds": 120,
        },
        timeout=timeout,
    )
    _expect_status(session, 200, "dashboard session set")
    set_cookie = ",".join(session.set_cookies) or session.headers.get("set-cookie", "")
    if "zroky_access_token=" not in set_cookie or "HttpOnly" not in set_cookie or "Secure" not in set_cookie:
        _fail("dashboard session set", "expected secure HttpOnly access cookie")
    _pass("dashboard session set", "secure HttpOnly cookie emitted")

    clear = _request("POST", _url(dashboard_url, "/api/auth/clear-session"), timeout=timeout)
    _expect_status(clear, 200, "dashboard session clear")
    clear_cookie = ",".join(clear.set_cookies) or clear.headers.get("set-cookie", "")
    if "zroky_access_token=" not in clear_cookie or "Max-Age=0" not in clear_cookie:
        _fail("dashboard session clear", "expected expired access cookie")
    _pass("dashboard session clear", "expired cookies emitted")


def _check_landing(landing_url: str, dashboard_url: str, timeout: float) -> None:
    landing = _request("GET", _url(landing_url, "/"), timeout=timeout)
    _expect_status(landing, 200, "landing home")
    landing_text = landing.text + _collect_script_bundle_text(landing_url, landing.text, timeout)
    required = [
        "Fix failed agent runs before they ship again",
        "Trace captured",
        "Replay required",
        "Golden pending",
        "CI unprotected",
        "Privacy",
        "Security",
        "Contact",
        "2026 Zroky",
    ]
    missing = [text for text in required if text not in landing_text]
    if missing:
        _fail("landing home", f"missing copy: {missing}")
    _pass("landing home", landing.final_url)

    for path, dashboard_path, label in [
        ("/signup", "/signup", "landing signup redirect"),
        ("/login", "/login", "landing login redirect"),
    ]:
        page = _request("GET", _url(landing_url, path), timeout=timeout)
        _expect_status(page, 200, label)
        expected = _url(dashboard_url, dashboard_path)
        # The current public site is a static Vercel artifact. Auth entrypoints
        # are static redirect documents rather than server-side 30x responses.
        if not (
            page.final_url.rstrip("/").startswith(expected.rstrip("/"))
            or expected in page.text
        ):
            _fail(label, f"expected redirect page to include {expected}, got {page.final_url}")
        _pass(label, expected)

    dashboard_login = _request("GET", _url(dashboard_url, "/login"), timeout=timeout)
    _expect_status(dashboard_login, 200, "dashboard URL from landing context")
    _pass("dashboard URL from landing context", dashboard_login.final_url)


def _collect_script_bundle_text(base_url: str, html: str, timeout: float) -> str:
    texts: list[str] = []
    base = _url(base_url, "/")
    for match in re.finditer(r'<script[^>]+src="([^"]+\.js)"', html):
        src = match.group(1)
        if src.startswith("http") and not src.startswith(base.rstrip("/")):
            continue
        asset_url = urllib.parse.urljoin(base, src)
        asset = _request("GET", asset_url, timeout=timeout)
        if asset.status == 200 and asset.text:
            texts.append(asset.text[:5_000_000])
    return "\n".join(texts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 8 deployment smoke against real deployed Zroky URLs.")
    parser.add_argument("--api-base-url", default=os.getenv("ZROKY_DEPLOY_API_URL", DEFAULT_API_BASE_URL))
    parser.add_argument("--dashboard-url", default=os.getenv("ZROKY_DEPLOY_DASHBOARD_URL", DEFAULT_DASHBOARD_URL))
    parser.add_argument("--landing-url", default=os.getenv("ZROKY_DEPLOY_LANDING_URL", DEFAULT_LANDING_URL))
    parser.add_argument("--provisioning-token", default=os.getenv("ZROKY_PROVISIONING_TOKEN", ""))
    parser.add_argument(
        "--provisioning-header",
        default=os.getenv("ZROKY_PROVISIONING_TOKEN_HEADER", "X-Zroky-Admin-Token"),
    )
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="Run backend deploy smoke only; skip dashboard and landing checks.",
    )
    parser.add_argument(
        "--skip-dashboard",
        action="store_true",
        help="Skip dashboard page/proxy/session checks.",
    )
    parser.add_argument(
        "--skip-landing",
        action="store_true",
        help="Skip landing page and dashboard redirect checks.",
    )
    parser.add_argument(
        "--grant-pro-via-railway-ssh",
        action="store_true",
        help="Grant the synthetic smoke project Pro entitlements through Railway SSH before replay/CI dispatch.",
    )
    parser.add_argument("--railway-service", default="zroky-api")
    parser.add_argument("--railway-environment", default="production")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.provisioning_token:
        print("[ERROR] ZROKY_PROVISIONING_TOKEN or --provisioning-token is required for deployed money-path smoke.")
        return 2

    result_ids: dict[str, str | None] = {}
    try:
        _check_health(args.api_base_url, args.timeout_seconds)
        project_id, api_key, api_key_id = _provision_project(
            args.api_base_url,
            provisioning_token=args.provisioning_token,
            provisioning_header=args.provisioning_header,
            timeout=args.timeout_seconds,
        )
        result_ids.update({"project_id": project_id, "api_key_id": api_key_id})
        result_ids.update(
            _check_api_key_lifecycle(
                args.api_base_url,
                project_id=project_id,
                provisioning_token=args.provisioning_token,
                provisioning_header=args.provisioning_header,
                timeout=args.timeout_seconds,
            )
        )

        if args.grant_pro_via_railway_ssh:
            _grant_pro_with_railway_ssh(
                project_id,
                service=args.railway_service,
                environment=args.railway_environment,
                timeout=max(60.0, args.timeout_seconds * 3),
            )
            _check_billing_plan(
                args.api_base_url,
                api_key=api_key,
                expected_plan="pro",
                timeout=args.timeout_seconds,
            )

        call_id = _ingest_call(args.api_base_url, api_key=api_key, timeout=args.timeout_seconds)
        result_ids["call_id"] = call_id
        expected_issue_id: str | None = None
        if args.grant_pro_via_railway_ssh:
            expected_issue_id = _seed_issue_with_railway_ssh(
                project_id,
                call_id,
                service=args.railway_service,
                environment=args.railway_environment,
                timeout=max(60.0, args.timeout_seconds * 3),
            )
            result_ids["issue_id"] = expected_issue_id
        _check_issues(
            args.api_base_url,
            api_key=api_key,
            expected_issue_id=expected_issue_id,
            timeout=args.timeout_seconds,
        )
        provider_key_id = _check_provider_vault(args.api_base_url, api_key=api_key, timeout=args.timeout_seconds)
        result_ids["provider_key_id"] = provider_key_id

        replay_ids = _check_replay_and_ci(
            args.api_base_url,
            api_key=api_key,
            call_id=call_id,
            expect_plan_gate=not args.grant_pro_via_railway_ssh,
            timeout=args.timeout_seconds,
        )
        result_ids.update(replay_ids)

        if args.backend_only or args.skip_dashboard:
            print("[SKIP] dashboard smoke skipped")
        else:
            _check_dashboard(args.dashboard_url, args.timeout_seconds)

        if args.backend_only or args.skip_landing:
            print("[SKIP] landing smoke skipped")
        else:
            _check_landing(args.landing_url, args.dashboard_url, args.timeout_seconds)
    except SmokeFailure as exc:
        print(f"[FAIL] {exc}")
        if result_ids:
            print("ids=" + json.dumps(result_ids, separators=(",", ":"), sort_keys=True))
        return 1

    print("ids=" + json.dumps(result_ids, separators=(",", ":"), sort_keys=True))
    print("[deployment-smoke] passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
