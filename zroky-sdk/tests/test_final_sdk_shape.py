from __future__ import annotations

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_final_python_sdk_shape_exists() -> None:
    for path in (
        "zroky/client.py",
        "zroky/intent.py",
        "zroky/policy.py",
        "zroky/observe.py",
        "zroky/verify.py",
        "zroky/executor.py",
        "zroky/evidence.py",
    ):
        assert (ROOT / path).exists(), path


def test_final_python_sdk_modules_import() -> None:
    for module_name in (
        "zroky.client",
        "zroky.intent",
        "zroky.policy",
        "zroky.observe",
        "zroky.verify",
        "zroky.executor",
        "zroky.evidence",
    ):
        importlib.import_module(module_name)
