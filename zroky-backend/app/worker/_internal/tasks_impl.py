"""Compatibility aggregator for Celery tasks.

The task source is split into semantic files for maintenance, but executed in
this module namespace so existing tests and integrations that patch
``app.worker.tasks`` globals keep working. Explicit Celery task names remain
``app.worker.tasks.*``.
"""

from __future__ import annotations

from pathlib import Path


_PARTS = (
    "tasks_common.py",
    "tasks_utils.py",
    "tasks_loop_detection.py",
    "tasks_diagnosis.py",
    "tasks_maintenance.py",
    "tasks_digest.py",
    "tasks_integrations.py",
    "tasks_replay.py",
    "tasks_billing.py",
    "tasks_drift.py",
)


def _exec_part(filename: str) -> None:
    path = Path(__file__).with_name(filename)
    source_lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("from app.worker._internal.tasks_"):
            continue
        if line.startswith("__all__ = "):
            continue
        source_lines.append(line)
    source = "\n".join(source_lines) + "\n"
    exec(compile(source, str(path), "exec"), globals())


for _part in _PARTS:
    _exec_part(_part)


__all__ = [name for name in globals() if not name.startswith("__")]
