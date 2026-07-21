from __future__ import annotations

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_final_backend_shape_exists() -> None:
    for path in (
        "app/api/v1/intents.py",
        "app/api/v1/policy.py",
        "app/api/v1/approvals.py",
        "app/api/v1/runs.py",
        "app/api/v1/observations.py",
        "app/api/v1/outcome_graphs.py",
        "app/api/v1/incidents.py",
        "app/api/v1/recovery.py",
        "app/api/v1/evidence.py",
        "app/api/v1/connectors.py",
        "app/api/v1/systems.py",
        "app/api/v1/admin.py",
        "app/infrastructure/db/__init__.py",
        "app/infrastructure/outbox/__init__.py",
        "app/infrastructure/signing/__init__.py",
        "app/infrastructure/object_storage/__init__.py",
        "app/infrastructure/secrets/__init__.py",
        "app/infrastructure/telemetry/__init__.py",
        "app/infrastructure/relay_protocol/__init__.py",
        "app/worker/observation_jobs.py",
        "app/worker/verification_jobs.py",
        "app/worker/recovery_jobs.py",
        "app/worker/evidence_jobs.py",
    ):
        assert (ROOT / path).exists(), path


def test_final_api_v1_modules_export_routers() -> None:
    for module_name in (
        "app.api.v1.intents",
        "app.api.v1.policy",
        "app.api.v1.approvals",
        "app.api.v1.runs",
        "app.api.v1.observations",
        "app.api.v1.outcome_graphs",
        "app.api.v1.incidents",
        "app.api.v1.recovery",
        "app.api.v1.evidence",
        "app.api.v1.connectors",
        "app.api.v1.systems",
        "app.api.v1.actions",
        "app.api.v1.events",
        "app.api.v1.assurance_packs",
        "app.api.v1.relay_protocol",
    ):
        assert hasattr(importlib.import_module(module_name), "router"), module_name


def test_router_uses_final_api_v1_boundaries() -> None:
    source = (ROOT / "app/api/router.py").read_text(encoding="utf-8")

    assert "from app.api.v1.intents import router as intents_router" in source
    assert "from app.api.v1.policy import router as policy_router" in source
    assert "from app.api.v1.recovery import router as recovery_router" in source
    assert "from app.api.v1.evidence import router as evidence_router" in source
    assert "from app.api.v1.systems import (" in source

