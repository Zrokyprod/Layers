"""Tests for `app.api.routes.regression_ci`.

  - POST /v1/regression-ci/run → 202, row created, Celery task queued.
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
from app.db.models import (
    Agent,
    AgentRelease,
    Call,
    Environment,
    GoldenSet,
    Project,
    RegressionContract,
    RegressionContractVersion,
    ReplayRun,
)
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
def _stub_regression_ci_task(monkeypatch):
    captured: list = []

    class _StubTask:
        @staticmethod
        def apply_async(args=None, kwargs=None, queue=None, **options):
            captured.append({"args": args or [], "kwargs": kwargs or {}, "queue": queue, "options": options})

    monkeypatch.setattr("app.worker._internal.tasks_impl.process_regression_ci_run", _StubTask)
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


def _seed_active_contract(session, project_id: str) -> str:
    env = Environment(id=str(uuid4()), project_id=project_id, name="production", type="production")
    agent = Agent(id=str(uuid4()), project_id=project_id, name="Refund Agent", slug="refund-agent")
    release = AgentRelease(
        id=str(uuid4()),
        project_id=project_id,
        agent_id=agent.id,
        environment_id=env.id,
        git_sha="broken-sha",
        prompt_version="refund-v1",
        tool_schema_hash="refund-tools-v1",
        release_fingerprint=uuid4().hex,
    )
    fixture = GoldenSet(id=str(uuid4()), project_id=project_id, name="Refund fixtures", blocks_ci=True)
    contract = RegressionContract(
        id=str(uuid4()),
        project_id=project_id,
        name="refund-status-required",
        severity="critical",
        status="active",
    )
    version = RegressionContractVersion(
        id=str(uuid4()),
        contract_id=contract.id,
        project_id=project_id,
        version_number=1,
        spec_json=json.dumps(
            {
                "schema": "regression_contract_v1",
                "assertions": [{"must_call": "get_refund_status"}],
                "proof": {
                    "baseline_reproduced": True,
                    "candidate_verified": True,
                    "required_trials": 10,
                    "critical_violations": 0,
                    "fixture_pinned": True,
                    "evaluator_bundle_pinned": True,
                    "candidate_sha": "fix-sha",
                },
            }
        ),
        fixture_set_id=fixture.id,
        baseline_release_id=release.id,
        trial_policy_json=json.dumps({"required_trials": 10, "critical_violation_tolerance": 0}),
        evaluator_bundle_version="default-v1",
    )
    contract.active_version_id = version.id
    session.add_all([env, agent, release, fixture, contract, version])
    session.commit()
    return version.id


class TestPostRun:
    def test_returns_202_creates_run_and_enqueues_celery(self, client, _stub_regression_ci_task):
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
        assert len(_stub_regression_ci_task) == 1
        task = _stub_regression_ci_task[0]
        assert task["queue"] == "diagnosis_pattern"
        assert task["args"][0] == "proj-post"
        assert task["args"][1] == data["run_id"]
        assert task["args"][2]["git_sha"] == "abc123"

    def test_active_contract_returns_repository_runner_fields_and_skips_celery(self, client, _stub_regression_ci_task):
        sf = client._session_factory
        with sf() as s:
            _seed_project_and_calls(s, "proj-runner")
            version_id = _seed_active_contract(s, "proj-runner")

        resp = client.post(
            "/v1/regression-ci/run",
            headers={"X-Project-Id": "proj-runner"},
            json={
                "head_sha": "head123",
                "repository": "acme/refunds",
                "pull_request_number": 42,
                "base_sha": "base123",
                "workflow_run_id": "987",
                "workflow_attempt": 2,
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["runner_required"] is True
        assert data["fixture_url"].endswith("/fixture")
        assert data["run_token"]
        assert data["contract_version_ids"] == [version_id]
        assert len(_stub_regression_ci_task) == 0

        with sf() as s:
            run = s.get(ReplayRun, data["run_id"])
            assert run.repository == "acme/refunds"
            assert run.pull_request_number == 42
            assert run.head_sha == "head123"
            assert run.base_sha == "base123"
            assert run.workflow_run_id == "987"
            assert run.workflow_attempt == 2
            assert run.runner_required is True

    def test_repository_runner_evidence_is_fail_closed_for_fewer_trials(self, client, _stub_regression_ci_task):
        sf = client._session_factory
        with sf() as s:
            _seed_project_and_calls(s, "proj-evidence")
            version_id = _seed_active_contract(s, "proj-evidence")

        run_resp = client.post(
            "/v1/regression-ci/run",
            headers={"X-Project-Id": "proj-evidence"},
            json={"head_sha": "fix-sha", "repository": "acme/refunds", "pull_request_number": 7},
        )
        assert run_resp.status_code == 202
        run = run_resp.json()

        fixture = client.get(
            run["fixture_url"],
            headers={
                "X-Project-Id": "proj-evidence",
                "X-Zroky-Run-Token": run["run_token"],
            },
        )
        assert fixture.status_code == 200
        assert fixture.json()["contract_version_ids"] == [version_id]

        evidence = client.post(
            f"/v1/regression-ci/runs/{run['run_id']}/evidence",
            headers={
                "X-Project-Id": "proj-evidence",
                "X-Zroky-Run-Token": run["run_token"],
            },
            json={
                "candidate_sha": "fix-sha",
                "agent_release": {
                    "agent_name": "Refund Agent",
                    "environment": "ci",
                    "model_provider": "openai",
                    "model_name": "gpt-4o",
                    "prompt_version": "refund-v2",
                    "tool_schema_hash": "refund-tools-v1",
                },
                "trials": [{"status": "pass"} for _ in range(9)],
                "trace": {"tool_calls": ["get_refund_status"]},
                "business_outcome": {"status": "ok"},
                "state_diff": {},
                "errors": [],
            },
        )
        assert evidence.status_code == 200
        body = evidence.json()
        assert body["status"] == "not_verified"
        assert body["required_trials"] == 10
        assert body["not_verified_reasons"] == ["required_trials_not_completed"]

        detail = client.get(
            f"/v1/regression-ci/runs/{run['run_id']}",
            headers={"X-Project-Id": "proj-evidence"},
        )
        assert detail.status_code == 200
        assert detail.json()["status"] == "not_verified"
        assert detail.json()["report"]["verdict"] == "not_verified"

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
