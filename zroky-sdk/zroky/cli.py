# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""``zroky`` command-line debugging tool.

Subcommands
-----------
- ``zroky doctor``               — validates SDK setup for first run.
- ``zroky init``                 — writes protected-action starter files.
- ``zroky health``               — pings the backend health endpoint.
- ``zroky config``               — prints the resolved SDK configuration.
- ``zroky ingest --test``        — sends one smoke event to the ingest endpoint.
- ``zroky buffer status``        — shows offline-buffer size & path.
- ``zroky buffer flush``         — replays buffered events to the backend.
- ``zroky buffer clear``         — empties the offline buffer (irreversible).
- ``zroky tail``                 — opens a WebSocket and prints realtime events.
- ``zroky replay <file>``        — replays a JSON / NDJSON file of events.

Designed to be useful both for SDK users debugging their integration and for
ZROKY engineers triaging incidents.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

import httpx

from zroky._internal.config import load_config
from zroky._internal.models import CallEvent
from zroky._internal.offline_buffer import OfflineBuffer
from zroky._runner import (
    RUNNER_CAPABILITY_VERSION,
    ProtectedActionRunner,
    ZrokyRunnerError,
    default_runner_metadata,
)

_HEALTH_PATH = "/health/live"
_INGEST_PATH = "/api/v1/ingest"

_ENV_EXAMPLE = """# Zroky SDK
# Create this key in the Zroky dashboard, then copy it into your real .env.
ZROKY_API_KEY=zk_live_your_key_here

# Optional if your API key is already scoped to one project.
ZROKY_PROJECT=your_project_id

ZROKY_ENVIRONMENT=production
"""

_QUICKSTART = '''"""Zroky protected-action quickstart.

Run:
  python zroky_quickstart.py

This submits an action intent to Zroky. Real production actions should be backed
by a registered runner and verifier in your dashboard.
"""
from __future__ import annotations

import os

import zroky


zroky.init(
    api_key=os.environ.get("ZROKY_API_KEY"),
    project=os.environ.get("ZROKY_PROJECT"),
)

result = zroky.protect(
    action="access.grant",
    operation_kind="UPDATE",
    params={
        "system": "github",
        "user_id": "user_123",
        "role": "admin",
    },
    resource={
        "type": "workspace_access",
        "id": "github:user_123",
    },
    purpose={
        "reason": "Grant temporary admin access after approval.",
    },
    verification_profile="github-role-match",
)

print(result)
'''


def _print_json(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _auth_headers(config: object, *, json_content: bool = False) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"} if json_content else {}
    api_key = getattr(config, "api_key", None)
    project = getattr(config, "project", None)
    if api_key:
        headers["x-api-key"] = api_key
    if project:
        headers["x-project-id"] = project
    return headers


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


# ------------------------------------------------------------------ commands

def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.path).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    files = {
        ".env.example": _ENV_EXAMPLE,
        "zroky_quickstart.py": _QUICKSTART,
    }
    written: list[str] = []
    skipped: list[str] = []

    for name, content in files.items():
        path = target / name
        if path.exists() and not args.force:
            skipped.append(str(path))
            continue
        path.write_text(content, encoding="utf-8")
        written.append(str(path))

    _print_json(
        {
            "ok": True,
            "path": str(target),
            "written": written,
            "skipped": skipped,
            "next": [
                "Set ZROKY_API_KEY in your environment.",
                "Run `zroky doctor`.",
                "Run `zroky ingest --test`.",
                "Use `zroky.protect(...)` around real-world agent actions.",
            ],
        }
    )
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    config = load_config()
    checks: list[dict[str, object]] = []

    checks.append(
        {
            "name": "api_key",
            "ok": bool(config.api_key),
            "message": "ZROKY_API_KEY is set" if config.api_key else "Set ZROKY_API_KEY",
        }
    )
    checks.append(
        {
            "name": "project",
            "ok": True,
            "message": (
                f"ZROKY_PROJECT={config.project}"
                if config.project
                else "ZROKY_PROJECT is optional when the API key carries project context"
            ),
        }
    )

    health_url = _url(config.ingest_url, _HEALTH_PATH)
    try:
        resp = httpx.get(health_url, headers=_auth_headers(config), timeout=8.0)
    except httpx.HTTPError as exc:
        checks.append({"name": "backend_health", "ok": False, "url": health_url, "error": str(exc)})
    else:
        checks.append(
            {
                "name": "backend_health",
                "ok": resp.status_code < 400,
                "url": health_url,
                "status": resp.status_code,
                "body_preview": resp.text[:200],
            }
        )

    ok = all(bool(check["ok"]) for check in checks)
    _print_json(
        {
            "ok": ok,
            "mode": config.mode,
            "ingest_url": config.ingest_url,
            "checks": checks,
            "next": "Run `zroky ingest --test` to send a smoke event." if ok else None,
        }
    )
    return 0 if ok else 1

def cmd_health(_args: argparse.Namespace) -> int:
    config = load_config()
    url = _url(config.ingest_url, _HEALTH_PATH)

    try:
        resp = httpx.get(url, headers=_auth_headers(config), timeout=8.0)
    except httpx.HTTPError as exc:
        _print_json({"status": "error", "url": url, "error": str(exc)})
        return 1

    _print_json({"status": resp.status_code, "url": url, "body": resp.text})
    return 0 if resp.status_code < 400 else 1


def cmd_config(_args: argparse.Namespace) -> int:
    config = load_config()
    redacted = {
        "api_key": "set" if config.api_key else None,
        "project": config.project,
        "mode": config.mode,
        "ingest_url": config.ingest_url,
        "mask_pii": config.mask_pii,
        "default_agent": config.default_agent,
        "verbose": config.verbose,
        "batch_size": config.batch_size,
        "flush_interval_seconds": config.flush_interval_seconds,
        "max_queue_size": config.max_queue_size,
        "validate_preflight": config.validate_preflight,
        "validate_preflight_sample_rate": config.validate_preflight_sample_rate,
        "enable_offline_buffer": config.enable_offline_buffer,
    }
    _print_json(redacted)
    return 0


def _test_ingest_payload() -> dict[str, object]:
    event = CallEvent(
        provider="zroky",
        model="ingest-test",
        messages=[
            {
                "role": "user",
                "content": "Zroky SDK ingest smoke test",
            }
        ],
        status="success",
        output_content="Zroky ingest smoke test accepted.",
        latency_ms=1.0,
        metadata={
            "source": "zroky_cli",
            "command": "zroky ingest --test",
            "created_at_ms": int(time.time() * 1000),
        },
    )
    return event.to_ingest_payload()


def cmd_ingest(args: argparse.Namespace) -> int:
    if not args.test:
        print("Nothing to ingest. Use: zroky ingest --test", file=sys.stderr)
        return 2

    config = load_config()
    if not config.api_key:
        _print_json(
            {
                "ok": False,
                "error": "ZROKY_API_KEY is not set",
                "hint": "Set ZROKY_API_KEY, then run `zroky ingest --test` again.",
            }
        )
        return 1

    payload = _test_ingest_payload()
    body = {"events": [payload]}
    url = _url(config.ingest_url, _INGEST_PATH)
    try:
        resp = httpx.post(
            url,
            content=json.dumps(body, default=str),
            headers=_auth_headers(config, json_content=True),
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        _print_json({"ok": False, "url": url, "error": str(exc)})
        return 1

    ok = resp.status_code < 400
    _print_json(
        {
            "ok": ok,
            "url": url,
            "status": resp.status_code,
            "event_id": payload.get("event_id"),
            "call_id": payload.get("call_id"),
            "body_preview": resp.text[:300],
            "next": "Open the dashboard and look for the `zroky ingest --test` event."
            if ok
            else None,
        }
    )
    return 0 if ok else 1


def cmd_buffer_status(_args: argparse.Namespace) -> int:
    buf = OfflineBuffer()
    _print_json(
        {
            "path": str(buf.path),
            "size_bytes": buf.size_bytes(),
            "is_empty": buf.is_empty(),
        }
    )
    return 0


def cmd_buffer_clear(_args: argparse.Namespace) -> int:
    OfflineBuffer().clear()
    _print_json({"cleared": True})
    return 0


def cmd_buffer_flush(_args: argparse.Namespace) -> int:
    config = load_config()
    buf = OfflineBuffer()
    payloads = buf.drain()
    if not payloads:
        _print_json({"flushed": 0, "message": "buffer was empty"})
        return 0

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if config.api_key:
        headers["x-api-key"] = config.api_key
    if config.project:
        headers["x-project-id"] = config.project

    url = _url(config.ingest_url, _INGEST_PATH)
    try:
        resp = httpx.post(
            url,
            content=json.dumps({"events": payloads}, default=str),
            headers=headers,
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        # Restore on failure so we don't lose data.
        buf.append(payloads)
        _print_json({"flushed": 0, "error": str(exc)})
        return 1

    if resp.status_code >= 400:
        buf.append(payloads)
        _print_json({"flushed": 0, "status": resp.status_code, "body": resp.text})
        return 1

    _print_json({"flushed": len(payloads), "status": resp.status_code})
    return 0


def cmd_tail(args: argparse.Namespace) -> int:
    config = load_config()
    base = config.ingest_url.replace("http://", "ws://").replace("https://", "wss://")
    suffix = "/api/v1/realtime"
    if args.topics:
        suffix += f"?topics={args.topics}"

    try:
        import websockets  # type: ignore[import-not-found]
    except ImportError:
        print(
            "`zroky tail` requires the `websockets` package. "
            "Install with: pip install websockets",
            file=sys.stderr,
        )
        return 2

    headers: dict[str, str] = {}
    if config.api_key:
        headers["x-api-key"] = config.api_key

    async def runner() -> None:
        url = base + suffix
        async with websockets.connect(url, additional_headers=headers) as ws:
            print(f"connected to {url}", file=sys.stderr)
            async for msg in ws:
                try:
                    print(json.dumps(json.loads(msg), indent=2, default=str))
                except (TypeError, ValueError):
                    print(msg)

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"tail failed: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    config = load_config()
    src = Path(args.file)
    if not src.exists():
        print(f"file not found: {src}", file=sys.stderr)
        return 2

    text = src.read_text(encoding="utf-8")
    payloads: list[dict] = []
    text = text.strip()
    if text.startswith("["):
        payloads = json.loads(text)
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payloads.append(json.loads(line))
            except (TypeError, ValueError):
                continue

    if not payloads:
        _print_json({"replayed": 0, "message": "no payloads parsed"})
        return 0

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if config.api_key:
        headers["x-api-key"] = config.api_key
    if config.project:
        headers["x-project-id"] = config.project

    url = _url(config.ingest_url, _INGEST_PATH)
    try:
        resp = httpx.post(
            url,
            content=json.dumps({"events": payloads}, default=str),
            headers=headers,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        _print_json({"replayed": 0, "error": str(exc)})
        return 1

    _print_json(
        {
            "replayed": len(payloads),
            "status": resp.status_code,
            "body_preview": resp.text[:200],
        }
    )
    return 0 if resp.status_code < 400 else 1


def cmd_runner_once(args: argparse.Namespace) -> int:
    runner_id = args.runner_id or os.environ.get("ZROKY_RUNNER_ID")
    if not runner_id:
        print("runner id required: pass --runner-id or set ZROKY_RUNNER_ID", file=sys.stderr)
        return 2
    metadata = default_runner_metadata(args.runner_instance_id)
    try:
        runner = ProtectedActionRunner(runner_id=runner_id)
        result = runner.run_once(runner_metadata=metadata)
    except ZrokyRunnerError as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 1
    _print_json(result)
    return 0 if result.get("status") in {"idle", "succeeded"} else 1


def cmd_runner_daemon(args: argparse.Namespace) -> int:
    runner_id = args.runner_id or os.environ.get("ZROKY_RUNNER_ID")
    if not runner_id:
        print("runner id required: pass --runner-id or set ZROKY_RUNNER_ID", file=sys.stderr)
        return 2

    stop_event = threading.Event()

    def _request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM) if hasattr(signal, "SIGTERM") else None
    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _request_stop)

    metadata = default_runner_metadata(args.runner_instance_id)
    try:
        runner = ProtectedActionRunner(runner_id=runner_id)
        result = runner.run_daemon(
            runner_metadata=metadata,
            supported_operation_kinds=args.supported_operation_kind or None,
            capability_version=RUNNER_CAPABILITY_VERSION,
            poll_interval_seconds=args.poll_interval_seconds,
            idle_backoff_max_seconds=args.idle_backoff_max_seconds,
            heartbeat_interval_seconds=args.heartbeat_interval_seconds,
            max_iterations=args.max_iterations,
            stop_event=stop_event,
            send_offline_heartbeat=not args.no_offline_heartbeat,
        )
    except ZrokyRunnerError as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 1
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        if hasattr(signal, "SIGTERM") and original_sigterm is not None:
            signal.signal(signal.SIGTERM, original_sigterm)

    _print_json(result)
    return 0 if result.get("status") == "stopped" and result.get("claim_errors", 0) == 0 else 1


# ------------------------------------------------------------------ argparse

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zroky", description="ZROKY SDK debugging CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="write protected-action starter files")
    init_parser.add_argument(
        "--path",
        default=".",
        help="directory where starter files should be written",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing starter files",
    )
    init_parser.set_defaults(func=cmd_init)

    sub.add_parser("doctor", help="validate SDK setup").set_defaults(func=cmd_doctor)
    sub.add_parser("health", help="ping the ingest backend").set_defaults(func=cmd_health)
    sub.add_parser("config", help="print resolved SDK configuration").set_defaults(func=cmd_config)

    ingest_parser = sub.add_parser("ingest", help="send a test event to the ingest backend")
    ingest_parser.add_argument(
        "--test",
        action="store_true",
        help="send one synthetic SDK smoke event",
    )
    ingest_parser.set_defaults(func=cmd_ingest)

    buf_parser = sub.add_parser("buffer", help="manage the offline buffer")
    buf_sub = buf_parser.add_subparsers(dest="buffer_command", required=True)
    buf_sub.add_parser("status", help="show offline-buffer state").set_defaults(
        func=cmd_buffer_status
    )
    buf_sub.add_parser("flush", help="replay buffered events to the backend").set_defaults(
        func=cmd_buffer_flush
    )
    buf_sub.add_parser("clear", help="delete buffered events (irreversible)").set_defaults(
        func=cmd_buffer_clear
    )

    tail_parser = sub.add_parser("tail", help="stream live events over websocket")
    tail_parser.add_argument("--topics", default=None, help="comma-separated topic filter")
    tail_parser.set_defaults(func=cmd_tail)

    replay_parser = sub.add_parser("replay", help="replay events from a JSON / NDJSON file")
    replay_parser.add_argument("file", help="path to file containing events")
    replay_parser.set_defaults(func=cmd_replay)

    runner_parser = sub.add_parser("runner", help="run customer-hosted protected action jobs")
    runner_sub = runner_parser.add_subparsers(dest="runner_command", required=True)
    once_parser = runner_sub.add_parser(
        "once",
        help="claim and execute at most one protected action",
    )
    once_parser.add_argument("--runner-id", default=None, help="registered Zroky action runner id")
    once_parser.add_argument(
        "--runner-instance-id",
        default=None,
        help="stable id for this local runner process",
    )
    once_parser.set_defaults(func=cmd_runner_once)

    daemon_parser = runner_sub.add_parser(
        "daemon",
        help="run the protected action runner continuously",
    )
    daemon_parser.add_argument(
        "--runner-id",
        default=None,
        help="registered Zroky action runner id",
    )
    daemon_parser.add_argument(
        "--runner-instance-id",
        default=None,
        help="stable id for this runner process",
    )
    daemon_parser.add_argument(
        "--supported-operation-kind",
        action="append",
        default=[],
        choices=["TRANSFER", "UPDATE", "SEND", "EXECUTE"],
        help="operation kind this runner can execute; repeat for multiple kinds",
    )
    daemon_parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    daemon_parser.add_argument("--idle-backoff-max-seconds", type=float, default=30.0)
    daemon_parser.add_argument("--heartbeat-interval-seconds", type=float, default=30.0)
    daemon_parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="optional bounded loop count for smoke tests and one-off probes",
    )
    daemon_parser.add_argument(
        "--no-offline-heartbeat",
        action="store_true",
        help="skip the final offline heartbeat on shutdown",
    )
    daemon_parser.set_defaults(func=cmd_runner_daemon)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
