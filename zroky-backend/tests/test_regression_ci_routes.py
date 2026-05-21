"""Tests for `app.api.routes.regression_ci`.

  - POST /v1/regression-ci/run → 202, row created, background task queued.
  - GET  /v1/regression-ci/runs/{id} → 200 status + report.
  - Tenant isolation → 404 on cross-project access.
  - Missing git_sha → 422.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Call, Project, ReplayRun
from app.db.session import get_db_session, get_db_session_read
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_regression_ci_routes.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db_session] = override
    app.dependency_overrides[get_db_session_read] = override
    with TestClient(app) as tc:
        tc._session_factory = factory  # type: ignore[attr-defined]
        yield tc
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _grant_pilot_tier(monkeypatch):
    from app.services import entitlements_resolver
    from app.services.billing_plans import PLAN_ENTITLEMENTS
    pro = dict(PLAN_ENTITLEMENTS["pro"])
    monkeypatch.setattr(entitlements_resolver, "has", lambda db, org_id, key: True)
    monkeypatch.setattr(entitlements_resolver, "get", lambda db, org_id, key, default=None: pro.get(key, default))
    monkeypatch.setattr(entitlements_resolver, "resolve_all", lambda db, org_id: dict(pro))
    monkeypatch.setattr(entitlements_resolver, "get_plan_code", lambda db, org_id: "pro")


@pytest.fixture(autouse=True)
def _stub_background_task(monkeypatch):
    captured: list = []
    def _stub_add_task(self, func, *args, **kwargs):
        captured.append((func.__name__, args, kwargs))
    monkeypatch.setattr("fastapi.background.BackgroundTasks.add_task", _stub_add_task)
    return captured


def _seed_project_and_calls(session, project_id: str, n: int = 5):
    session.add(Project(id=project_id, name="Test"))
    for i in range(n):
        payload = {"messages": [{"role": "user", "content": f"q{i}"}], "model": "gpt-4o-mini", "response": f"a{i}"}
        session.add(Call(
            id=str(uuid4()), project_id=project_id, event_id=str(uuid4()),
            created_at=datetime.now(timezone.utc), agent_name="a", provider="openai",
            model="gpt-4o-mini", status="success", is_production=True,
            payload_json=json.dumps(payload),
        ))
    session.commit()


class TestPostRun:
    def test_returns_202_and_creates_run(self, client, _stub_background_task):
        sf = client._session_factory
        with sf() as s:
            _seed_project_and_calls(s, "proj-post")
        resp = client.post(
            "/v1/regression-ci/run",
            headers={"X-Project-Id": "proj-post"},
            json={"git_sha": "abc123", "changed_files": [{"path": "p.md"}]},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        assert data["run_id"]
        assert data["summary_url"].endswith(data["run_id"])
        assert len(_stub_background_task) == 1

    def test_git_sha_required(self, client):
        resp = client.post(
            "/v1/regression-ci/run",
            headers={"X-Project-Id": "proj-sha"},
            json={},
        )
        assert resp.status_code == 422

    def test_invalid_override_category(self, client):
        resp = client.post(
            "/v1/regression-ci/run",
            headers={"X-Project-Id": "proj-ov"},
            json={
                "git_sha": "abc",
                "operator_override": {"category": "not_real"},
            },
        )
        assert resp.status_code == 422


class TestGetRun:
    def test_returns_terminal_report(self, client):
        sf = client._session_factory
        with sf() as s:
            _seed_project_and_calls(s, "proj-get", n=3)
            run = ReplayRun(
                id=str(uuid4()), project_id="proj-get",
                golden_set_id="regression-ci:proj-get",
                trigger="github", git_sha="abc", status="pass",
                created_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                summary_json=json.dumps({
                    "schema_version": "v1", "run_id": "x",
                    "project_id": "proj-get", "git_sha": "abc",
                    "blast_radius": {"category": "system_prompt", "source": "declared", "files": [], "target": None, "confidence": 1.0},
                    "sample_spec": {"target_total": 10, "stratification": {"pass_history": 1.0, "fail_history": 0.0, "rare_cluster": 0.0, "recent_24h": 0.0}, "blast_radius": {"category": "system_prompt", "source": "declared", "files": [], "target": None, "confidence": 1.0}},
                    "stratification_realised": {"pass_history": 3, "fail_history": 0, "rare_cluster": 0, "recent_24h": 0, "realised_total": 3},
                    "trace_count": 3, "regressed_count": 0,
                    "regression_rate": 0.0, "threshold": 0.02,
                    "verdict": "pass", "error_count": 0,
                    "error_rate": 0.0, "judge_used_count": 0,
                    "cost_usd": 0.0, "duration_seconds": 5,
                    "clusters": [], "notes": [],
                }),
            )
            s.add(run)
            s.commit()
            rid = run.id

        resp = client.get(
            f"/v1/regression-ci/runs/{rid}",
            headers={"X-Project-Id": "proj-get"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pass"
        assert data["report"]["verdict"] == "pass"
        assert "## ✅ Replay CI passed" in (data["pr_comment_markdown"] or "")

    def test_cross_tenant_404(self, client):
        sf = client._session_factory
        with sf() as s:
            run = ReplayRun(
                id=str(uuid4()), project_id="proj-a",
                golden_set_id="regression-ci:proj-a",
                trigger="github", status="pass",
                created_at=datetime.now(timezone.utc),
            )
            s.add(run)
            s.commit()
            rid = run.id

        resp = client.get(
            f"/v1/regression-ci/runs/{rid}",
            headers={"X-Project-Id": "proj-b"},
        )
        assert resp.status_code == 404
