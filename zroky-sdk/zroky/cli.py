"""``zroky`` command-line debugging tool.

Subcommands
-----------
- ``zroky health``               — pings the ingest endpoint.
- ``zroky config``               — prints the resolved SDK configuration.
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
import sys
from pathlib import Path

import httpx

from zroky._internal.config import load_config
from zroky._internal.offline_buffer import OfflineBuffer


def _print_json(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


# ------------------------------------------------------------------ commands

def cmd_health(_args: argparse.Namespace) -> int:
    config = load_config()
    url = f"{config.ingest_url}/api/v1/healthz"
    headers: dict[str, str] = {}
    if config.api_key:
        headers["x-api-key"] = config.api_key
    if config.project:
        headers["x-project-id"] = config.project

    try:
        resp = httpx.get(url, headers=headers, timeout=8.0)
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

    url = f"{config.ingest_url}/api/v1/ingest"
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
        print("`zroky tail` requires the `websockets` package. Install with: pip install websockets", file=sys.stderr)
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

    url = f"{config.ingest_url}/api/v1/ingest"
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


# ------------------------------------------------------------------ argparse

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zroky", description="ZROKY SDK debugging CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="ping the ingest backend").set_defaults(func=cmd_health)
    sub.add_parser("config", help="print resolved SDK configuration").set_defaults(func=cmd_config)

    buf_parser = sub.add_parser("buffer", help="manage the offline buffer")
    buf_sub = buf_parser.add_subparsers(dest="buffer_command", required=True)
    buf_sub.add_parser("status", help="show offline-buffer state").set_defaults(func=cmd_buffer_status)
    buf_sub.add_parser("flush", help="replay buffered events to the backend").set_defaults(func=cmd_buffer_flush)
    buf_sub.add_parser("clear", help="delete buffered events (irreversible)").set_defaults(func=cmd_buffer_clear)

    tail_parser = sub.add_parser("tail", help="stream live events over websocket")
    tail_parser.add_argument("--topics", default=None, help="comma-separated topic filter")
    tail_parser.set_defaults(func=cmd_tail)

    replay_parser = sub.add_parser("replay", help="replay events from a JSON / NDJSON file")
    replay_parser.add_argument("file", help="path to file containing events")
    replay_parser.set_defaults(func=cmd_replay)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
