from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GO_CACHE = ROOT / ".data" / f"go-cache-capture-e2e-{os.getpid()}"


def project_python() -> str:
    names = ("python.exe",) if os.name == "nt" else ("python", "python3")
    for base in (ROOT / "zroky-backend" / ".venv" / "Scripts", ROOT / ".venv" / "Scripts"):
        for name in names:
            candidate = base / name
            if candidate.exists():
                return str(candidate)
    for base in (ROOT / "zroky-backend" / ".venv" / "bin", ROOT / ".venv" / "bin"):
        for name in names:
            candidate = base / name
            if candidate.exists():
                return str(candidate)
    return sys.executable


PYTHON = project_python()


def merged_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if overrides:
        env.update(overrides)
    return env


def resolve_command(command: list[str]) -> list[str]:
    resolved = list(command)
    executable = resolved[0]

    if os.name == "nt" and not Path(executable).suffix:
        cmd_executable = shutil.which(f"{executable}.cmd")
        if cmd_executable:
            resolved[0] = cmd_executable
            return resolved

    found = shutil.which(executable)
    if found:
        resolved[0] = found
    return resolved


Step = tuple[str, list[str], Path, dict[str, str] | None, int]


STEPS: list[Step] = [
    (
        "Gateway Go contract tests",
        ["go", "test", "./..."],
        ROOT / "zroky-gateway",
        {"GOCACHE": str(GO_CACHE)},
        90,
    ),
    (
        "Python SDK capture context tests",
        [
            PYTHON,
            "-m",
            "pytest",
            "-q",
            "tests/test_sdk.py::test_init_reads_capture_context_fields",
            "tests/test_sdk.py::test_python_sdk_payload_uses_ingest_event_v2_context",
            "tests/test_sdk.py::test_python_sdk_captures_retrieval_and_memory_spans",
        ],
        ROOT / "zroky-sdk",
        None,
        90,
    ),
    (
        "Backend capture ingest tests",
        [
            PYTHON,
            "-m",
            "pytest",
            "-q",
            "tests/test_capture_health.py",
            "tests/test_gateway_stream_consumer.py",
            "tests/test_js_sdk_ingest_contract.py",
        ],
        ROOT / "zroky-backend",
        {
            "TESTING": "true",
            "DATABASE_URL": "sqlite:///./.data/test_shared.db",
        },
        120,
    ),
    (
        "JS SDK capture tests",
        ["npm", "test"],
        ROOT / "zroky-sdk-js",
        None,
        120,
    ),
    (
        "JS SDK build",
        ["npm", "run", "build"],
        ROOT / "zroky-sdk-js",
        None,
        90,
    ),
    (
        "JS SDK size gate",
        ["npm", "run", "size"],
        ROOT / "zroky-sdk-js",
        None,
        60,
    ),
    (
        "Dashboard capture lint",
        [
            "npm",
            "run",
            "lint",
            "--",
            "src/app/(dashboard)/home/page.tsx",
            "src/components/capture-connect-panel.tsx",
            "src/lib/api.ts",
            "src/lib/types.ts",
        ],
        ROOT / "zroky-dashboard",
        None,
        120,
    ),
    (
        "Live no-Docker capture smoke",
        [PYTHON, "scripts/run_capture_smoke_no_docker.py"],
        ROOT,
        None,
        180,
    ),
]


def run_step(name: str, command: list[str], cwd: Path, env: dict[str, str] | None, timeout_seconds: int) -> None:
    command = resolve_command(command)
    print(f"\n[capture-e2e] {name}", flush=True)
    print(f"[capture-e2e] cwd: {cwd}", flush=True)
    print(f"[capture-e2e] cmd: {' '.join(command)}", flush=True)
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=cwd, env=merged_env(env), check=False, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        print(f"[capture-e2e] TIMEOUT: {name} after {elapsed:.1f}s (limit {timeout_seconds}s)", flush=True)
        raise SystemExit(124) from exc
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        print(f"[capture-e2e] FAILED: {name} ({elapsed:.1f}s)", flush=True)
        raise SystemExit(result.returncode)
    print(f"[capture-e2e] passed: {name} ({elapsed:.1f}s)", flush=True)


def main() -> None:
    print("[capture-e2e] Running local capture verification without Docker.", flush=True)
    GO_CACHE.mkdir(parents=True, exist_ok=True)
    for name, command, cwd, env, timeout_seconds in STEPS:
        run_step(name, command, cwd, env, timeout_seconds)
    print("\n[capture-e2e] All local capture checks passed.", flush=True)


if __name__ == "__main__":
    main()
