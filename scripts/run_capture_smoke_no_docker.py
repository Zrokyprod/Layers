from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "zroky-backend"
GATEWAY = ROOT / "zroky-gateway"
PROJECT_ID = "proj_capture_smoke"
CALL_ID = "call_capture_smoke"


class ManagedProcess:
    def __init__(self, name: str, command: list[str], cwd: Path, env: dict[str, str]) -> None:
        self.name = name
        self.lines: deque[str] = deque(maxlen=80)
        self.process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

    def _read_output(self) -> None:
        if self.process.stdout is None:
            return
        for line in self.process.stdout:
            self.lines.append(line.rstrip())

    def stop(self) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=8)

    def assert_running(self) -> None:
        code = self.process.poll()
        if code is not None:
            tail = "\n".join(self.lines)
            raise RuntimeError(f"{self.name} exited early with code {code}\n{tail}")


class MockOpenAIHandler(BaseHTTPRequestHandler):
    seen_headers: list[dict[str, str]] = []
    seen_paths: list[str] = []

    def do_POST(self) -> None:  # noqa: N802
        _ = self.rfile.read(int(self.headers.get("content-length") or "0"))
        self.__class__.seen_paths.append(self.path)
        self.__class__.seen_headers.append(dict(self.headers.items()))
        body = {
            "id": "chatcmpl_capture_smoke",
            "object": "chat.completion",
            "model": "gpt-4o-mini",
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 2,
                "total_tokens": 7,
            },
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "smoke-ok"},
                    "finish_reason": "stop",
                }
            ],
        }
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def merged_env(overrides: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(overrides)
    return env


def init_backend_db(env: dict[str, str]) -> None:
    db_path = BACKEND / ".data" / "capture_smoke.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    command = [
        sys.executable,
        "-c",
        (
            "from app.db.base import Base; "
            "import app.db.models; "
            "from app.db.session import engine; "
            "Base.metadata.create_all(bind=engine)"
        ),
    ]
    subprocess.run(command, cwd=BACKEND, env=env, check=True)


def build_gateway_binary() -> Path:
    exe_name = "capture-smoke-gateway.exe" if os.name == "nt" else "capture-smoke-gateway"
    out_path = ROOT / ".data" / exe_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    command = ["go", "build", "-o", str(out_path), "./cmd/gateway"]
    env = os.environ.copy()
    env.setdefault("GOCACHE", str(GATEWAY / ".gocache"))
    subprocess.run(command, cwd=GATEWAY, env=env, check=True)
    return out_path


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("accept", "application/json")
    if payload is not None:
        req.add_header("content-type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def wait_for_json(url: str, *, headers: dict[str, str] | None = None, processes: list[ManagedProcess]) -> dict[str, Any]:
    deadline = time.monotonic() + 45
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        for process in processes:
            process.assert_running()
        try:
            return request_json(url, headers=headers, timeout=2)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.5)
    tails = []
    for process in processes:
        tails.append(f"[{process.name}]\n" + "\n".join(process.lines))
    raise TimeoutError(f"timed out waiting for {url}: {last_error}\n" + "\n\n".join(tails))


def wait_for_capture(backend_url: str) -> dict[str, Any]:
    deadline = time.monotonic() + 45
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        health = request_json(
            f"{backend_url}/api/v1/capture/health",
            headers={"x-project-id": PROJECT_ID},
            timeout=3,
        )
        last = health
        if (
            health.get("status") == "connected"
            and health.get("last_call_id") == CALL_ID
            and health.get("last_source") == "gateway_http_direct"
            and int(health.get("gateway_events_24h") or 0) >= 1
        ):
            return health
        time.sleep(0.5)
    raise TimeoutError(f"capture health did not observe gateway event: {last}")


def main() -> None:
    print("[capture-smoke] Starting no-Docker live capture smoke.", flush=True)
    backend_port = free_port()
    gateway_port = free_port()
    upstream_port = free_port()
    backend_url = f"http://127.0.0.1:{backend_port}"
    gateway_url = f"http://127.0.0.1:{gateway_port}"
    upstream_url = f"http://127.0.0.1:{upstream_port}"

    backend_env = merged_env(
        {
            "APP_ENV": "development",
            "TESTING": "true",
            "DATABASE_URL": "sqlite:///./.data/capture_smoke.db",
            "AUTH_JWT_SECRET": "capture-smoke-secret-key",
            "ALLOW_PROJECT_HEADER_CONTEXT": "true",
            "REQUIRE_PROVISIONING_TOKEN": "false",
            "ENABLE_READY_REDIS_CHECK": "false",
            "CELERY_BROKER_URL": "memory://",
            "CELERY_RESULT_BACKEND": "cache+memory://",
            "GATEWAY_INGEST_STREAM_ENABLED": "false",
        }
    )
    init_backend_db(backend_env)
    gateway_binary = build_gateway_binary()

    mock_upstream = ThreadingHTTPServer(("127.0.0.1", upstream_port), MockOpenAIHandler)
    upstream_thread = threading.Thread(target=mock_upstream.serve_forever, daemon=True)
    upstream_thread.start()

    processes: list[ManagedProcess] = []
    try:
        backend = ManagedProcess(
            "backend",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(backend_port),
                "--log-level",
                "warning",
            ],
            BACKEND,
            backend_env,
        )
        processes.append(backend)

        gateway = ManagedProcess(
            "gateway",
            [str(gateway_binary)],
            GATEWAY,
            merged_env(
                {
                    "PORT": str(gateway_port),
                    "ZROKY_EMIT_MODE": "http",
                    "ZROKY_INGEST_URL": f"{backend_url}/api/v1/ingest",
                    "ZROKY_GATEWAY_API_KEY": "zk_capture_smoke",
                    "OPENAI_UPSTREAM_BASE_URL": upstream_url,
                    "LOG_LEVEL": "warn",
                    "PRETTY_LOGS": "false",
                    "MAX_BODY_BYTES": "1048576",
                }
            ),
        )
        processes.append(gateway)

        wait_for_json(f"{backend_url}/api/health/live", processes=processes)
        wait_for_json(f"{gateway_url}/health", processes=processes)

        response = request_json(
            f"{gateway_url}/v1/chat/completions",
            method="POST",
            payload={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "capture smoke"}],
            },
            headers={
                "authorization": "Bearer provider-key",
                "x-zroky-project-id": PROJECT_ID,
                "x-zroky-call-id": CALL_ID,
                    "x-zroky-agent-name": "smoke-agent",
                    "x-zroky-trace-id": "trace_capture_smoke",
                    "x-zroky-workflow-name": "capture-smoke",
                    "x-zroky-prompt-version": "smoke-v1",
                },
            timeout=10,
        )
        if response.get("id") != "chatcmpl_capture_smoke":
            raise AssertionError(f"unexpected gateway response: {response}")
        if not MockOpenAIHandler.seen_headers:
            raise AssertionError("mock upstream did not receive gateway request")
        upstream_headers = MockOpenAIHandler.seen_headers[-1]
        if any(key.lower().startswith("x-zroky-") for key in upstream_headers):
            raise AssertionError(f"zroky headers leaked upstream: {upstream_headers}")

        health = wait_for_capture(backend_url)
        print(
            "[capture-smoke] passed: "
            f"status={health['status']} source={health['last_source']} calls_24h={health['calls_24h']}",
            flush=True,
        )
    finally:
        for process in reversed(processes):
            process.stop()
        mock_upstream.shutdown()
        mock_upstream.server_close()


if __name__ == "__main__":
    main()
