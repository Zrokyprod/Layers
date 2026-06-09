from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.discovery.runtime import DiscoveryRuntimeResult
from app.worker import tasks as worker_tasks


def _settings(*, enabled: bool) -> Settings:
    return Settings(
        DISCOVERY_ENABLED=enabled,
        DISCOVERY_PROJECT_LIMIT=10,
        DISCOVERY_SCAN_LIMIT=100,
    )


def test_discovery_tasks_disabled_short_circuit_before_db(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unexpected_session():
        raise AssertionError("disabled Discovery task must not open a DB session")

    monkeypatch.setattr(worker_tasks, "get_settings", lambda: _settings(enabled=False))
    monkeypatch.setattr(worker_tasks, "SessionLocal", _unexpected_session)

    refresh = worker_tasks.refresh_discovery_baselines.run()
    scan = worker_tasks.scan_discovery_anomalies.run()

    assert refresh["status"] == "disabled"
    assert refresh["reason"] == "DISCOVERY_ENABLED=false"
    assert refresh["projects_processed"] == 0
    assert scan["status"] == "disabled"
    assert scan["reason"] == "DISCOVERY_ENABLED=false"
    assert scan["projects_processed"] == 0


def test_refresh_discovery_baselines_task_invokes_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession()
    tenant_contexts: list[str] = []
    runtime_calls: list[str] = []

    def _refresh_baselines(db, *, project_id, settings):
        assert db is session
        assert settings.DISCOVERY_ENABLED is True
        runtime_calls.append(project_id)
        return DiscoveryRuntimeResult(
            enabled=True,
            calls_loaded=24,
            baselines_written=1,
        )

    monkeypatch.setattr(worker_tasks, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        worker_tasks,
        "set_db_tenant_context",
        lambda db, tenant_id: tenant_contexts.append(tenant_id),
    )
    monkeypatch.setattr(worker_tasks, "refresh_baselines", _refresh_baselines)

    result = worker_tasks.refresh_discovery_baselines.run(project_id="project-1")

    assert result["status"] == "ok"
    assert result["projects_seen"] == 1
    assert result["projects_processed"] == 1
    assert result["failed_projects"] == 0
    assert runtime_calls == ["project-1"]
    assert tenant_contexts == ["project-1"]
    assert result["results"][0]["calls_loaded"] == 24
    assert result["results"][0]["baselines_written"] == 1
    assert session.closed is True


def test_scan_discovery_anomalies_task_invokes_watermarked_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession()
    tenant_contexts: list[str] = []
    runtime_calls: list[str] = []

    def _scan_and_surface(db, *, project_id, settings):
        assert db is session
        assert settings.DISCOVERY_ENABLED is True
        runtime_calls.append(project_id)
        return DiscoveryRuntimeResult(
            enabled=True,
            calls_loaded=3,
            traces_scored=3,
            candidates_found=3,
            anomalies_written=1,
            watermark_advanced=True,
        )

    monkeypatch.setattr(worker_tasks, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        worker_tasks,
        "set_db_tenant_context",
        lambda db, tenant_id: tenant_contexts.append(tenant_id),
    )
    monkeypatch.setattr(worker_tasks, "scan_and_surface", _scan_and_surface)

    result = worker_tasks.scan_discovery_anomalies.run(project_id="project-1")

    assert result["status"] == "ok"
    assert result["projects_seen"] == 1
    assert result["projects_processed"] == 1
    assert result["failed_projects"] == 0
    assert runtime_calls == ["project-1"]
    assert tenant_contexts == ["project-1"]
    assert result["results"][0]["traces_scored"] == 3
    assert result["results"][0]["anomalies_written"] == 1
    assert result["results"][0]["watermark_advanced"] is True
    assert session.closed is True


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False
        self.rolled_back = False

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True
