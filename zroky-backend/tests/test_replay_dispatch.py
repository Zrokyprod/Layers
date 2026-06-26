"""Tests for Module 9 â€” GitHub-Action-friendly replay dispatch surface.

Covers:
  * Service-level idempotency on `(project_id, golden_set_id, git_sha)`
    in `app.services.replay_runs.dispatch_replay_run`.
  * Persistence of new optional metadata (branch_name / pr_number /
    commit_message) into `summary_json`.
  * `build_summary_url` honoring the `FRONTEND_URL` setting.
  * `delete_golden_set` clearing any dangling
    `Project.default_golden_set_id` (Module-9 cascade).
  * Route-level `POST /v1/replay/dispatch` covering: explicit set,
    default-set resolution, missing-default 422, idempotent reply,
    cross-tenant 404, invalid trigger 422.
  * Backward-compat smoke for `POST /v1/goldens/{id}/run` which now
    returns the new `summary_url` + `idempotent` fields.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Project, ReplayRun
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.goldens import (
    create_golden_set,
    delete_golden_set,
    add_trace,
)
from app.services.replay_runs import (
    IDEMPOTENCY_TERMINAL_HORIZON_MINUTES,
    build_summary_url,
    dispatch_replay_run,
    get_replay_run,
    parse_summary,
)


# â”€â”€ fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_replay_dispatch_svc.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_replay_dispatch_route.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def override_get_db_session():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session

    with TestClient(app) as test_client:
        test_client._session_factory = factory  # type: ignore[attr-defined]
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


PROJECT_HEADER = "X-Project-Id"


# Module 6 plan-gate bypass â€” same shape as test_replay_runs.py.
@pytest.fixture(autouse=True)
def _grant_pilot_tier(monkeypatch):
    from app.services import entitlements_resolver
    from app.services.billing_plans import PLAN_ENTITLEMENTS

    pro = dict(PLAN_ENTITLEMENTS["pro"])
    monkeypatch.setattr(
        entitlements_resolver, "has", lambda db, org_id, key: True
    )
    monkeypatch.setattr(
        entitlements_resolver,
        "get",
        lambda db, org_id, key, default=None: pro.get(key, default),
    )
    monkeypatch.setattr(
        entitlements_resolver, "resolve_all", lambda db, org_id: dict(pro)
    )
    monkeypatch.setattr(
        entitlements_resolver, "get_plan_code", lambda db, org_id: "pro"
    )


# Module 9: silence Celery enqueue side-effect inside the dispatch
# routes. Worker is exercised separately in test_replay_executor.py.
@pytest.fixture(autouse=True)
def _stub_process_replay_run(monkeypatch):
    from app.worker import tasks

    calls: list[tuple] = []

    class _AsyncResult:
        id = "stub"

    def _apply_async(*args, **kwargs):
        calls.append((args, kwargs))
        return _AsyncResult()

    monkeypatch.setattr(tasks.process_replay_run, "apply_async", _apply_async)
    return calls


# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _seed_project(session, project_id: str, *, default_set: str | None = None):
    proj = Project(
        id=project_id,
        name=f"Project {project_id}",
        is_active=True,
        default_golden_set_id=default_set,
    )
    session.add(proj)
    session.commit()
    return proj


def _seed_set_with_traces(
    session, *, project_id: str, name: str, n_traces: int = 2
):
    gs = create_golden_set(session, project_id=project_id, name=name)
    for i in range(n_traces):
        add_trace(
            session,
            project_id=project_id,
            golden_set_id=gs.id,
            expected_output_text=f"out-{i}",
        )
    return gs


# â”€â”€ service: metadata persistence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestDispatchMetadataFields:
    def test_persists_branch_pr_and_commit_message(self, db_session) -> None:
        gs = _seed_set_with_traces(
            db_session, project_id="proj-1", name="x"
        )
        run = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            trigger="github",
            git_sha="sha-aaa",
            branch_name="feature/foo",
            pr_number=42,
            commit_message="fix: typo\n\nlong body",
        )
        assert run is not None
        summary = parse_summary(run.summary_json)
        assert summary["branch_name"] == "feature/foo"
        assert summary["pr_number"] == 42
        # commit_message stores first line only.
        assert summary["commit_message"] == "fix: typo"

    def test_omits_unset_metadata_fields(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        run = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
        )
        assert run is not None
        summary = parse_summary(run.summary_json)
        assert "branch_name" not in summary
        assert "pr_number" not in summary
        assert "commit_message" not in summary

    def test_invalid_pr_number_dropped_silently(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        # Pydantic would reject this at the route, but the service should
        # be defensive too (other call sites may pass arbitrary values).
        run = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            pr_number="not-a-number",  # type: ignore[arg-type]
        )
        assert run is not None
        summary = parse_summary(run.summary_json)
        assert "pr_number" not in summary

    def test_branch_name_and_commit_message_truncated(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        run = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            branch_name="b" * 500,
            commit_message="m" * 500,
        )
        assert run is not None
        summary = parse_summary(run.summary_json)
        assert len(summary["branch_name"]) == 255
        assert len(summary["commit_message"]) == 200


# â”€â”€ service: idempotency â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestDispatchIdempotency:
    def test_same_sha_returns_existing_pending_run(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        first = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            git_sha="sha-aaa",
        )
        second = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            git_sha="sha-aaa",
        )
        assert first is not None and second is not None
        assert first.id == second.id

    def test_different_sha_creates_new_run(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        first = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            git_sha="sha-aaa",
        )
        second = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            git_sha="sha-bbb",
        )
        assert first is not None and second is not None
        assert first.id != second.id

    def test_manual_trigger_no_sha_never_dedups(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        first = dispatch_replay_run(
            db_session, project_id="proj-1", golden_set_id=gs.id
        )
        second = dispatch_replay_run(
            db_session, project_id="proj-1", golden_set_id=gs.id
        )
        assert first is not None and second is not None
        assert first.id != second.id

    def test_whitespace_sha_treated_as_none(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        first = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            git_sha="   ",
        )
        second = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            git_sha="   ",
        )
        # Both should create new rows (whitespace normalized to None).
        assert first is not None and second is not None
        assert first.id != second.id
        assert first.git_sha is None and second.git_sha is None

    def test_terminal_run_within_horizon_returns_existing(
        self, db_session
    ) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        first = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            git_sha="sha-aaa",
        )
        assert first is not None
        # Promote to terminal status with completed_at = now.
        first.status = "pass"
        first.completed_at = datetime.now(timezone.utc)
        db_session.add(first)
        db_session.commit()

        second = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            git_sha="sha-aaa",
        )
        assert second is not None
        assert second.id == first.id

    def test_terminal_run_outside_horizon_creates_new(
        self, db_session
    ) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        first = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            git_sha="sha-aaa",
        )
        assert first is not None
        # Backdate completed_at past the horizon.
        stale = datetime.now(timezone.utc) - timedelta(
            minutes=IDEMPOTENCY_TERMINAL_HORIZON_MINUTES + 5
        )
        first.status = "fail"
        first.completed_at = stale
        first.created_at = stale
        db_session.add(first)
        db_session.commit()

        second = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            git_sha="sha-aaa",
        )
        assert second is not None
        assert second.id != first.id

    def test_different_golden_set_creates_new_run(self, db_session) -> None:
        gs1 = _seed_set_with_traces(db_session, project_id="proj-1", name="a")
        gs2 = _seed_set_with_traces(db_session, project_id="proj-1", name="b")
        first = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs1.id,
            git_sha="sha-aaa",
        )
        second = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs2.id,
            git_sha="sha-aaa",
        )
        assert first is not None and second is not None
        assert first.id != second.id

    def test_cross_tenant_isolation(self, db_session) -> None:
        gs_a = _seed_set_with_traces(
            db_session, project_id="proj-A", name="x"
        )
        gs_b = _seed_set_with_traces(
            db_session, project_id="proj-B", name="x"
        )
        run_a = dispatch_replay_run(
            db_session,
            project_id="proj-A",
            golden_set_id=gs_a.id,
            git_sha="sha-aaa",
        )
        run_b = dispatch_replay_run(
            db_session,
            project_id="proj-B",
            golden_set_id=gs_b.id,
            git_sha="sha-aaa",
        )
        assert run_a is not None and run_b is not None
        assert run_a.id != run_b.id


# â”€â”€ service: build_summary_url â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestBuildSummaryUrl:
    def test_uses_frontend_url_setting(self, db_session, monkeypatch) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        run = dispatch_replay_run(
            db_session, project_id="proj-1", golden_set_id=gs.id
        )
        assert run is not None
        s = get_settings()
        monkeypatch.setattr(s, "FRONTEND_URL", "https://app.example.com")
        url = build_summary_url(run)
        assert url == f"https://app.example.com/evidence?replay_run_id={run.id}"

    def test_strips_trailing_slash(self, db_session, monkeypatch) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        run = dispatch_replay_run(
            db_session, project_id="proj-1", golden_set_id=gs.id
        )
        assert run is not None
        s = get_settings()
        monkeypatch.setattr(s, "FRONTEND_URL", "https://app.example.com/")
        assert build_summary_url(run).startswith("https://app.example.com/evidence?replay_run_id=")
        assert "//replay" not in build_summary_url(run)


# â”€â”€ service: delete_golden_set cascade â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestDeleteGoldenSetClearsDefault:
    def test_clears_project_default_pointer(self, db_session) -> None:
        proj = _seed_project(db_session, "proj-1")
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        proj.default_golden_set_id = gs.id
        db_session.add(proj)
        db_session.commit()

        deleted = delete_golden_set(
            db_session, project_id="proj-1", golden_set_id=gs.id
        )
        assert deleted is True
        db_session.refresh(proj)
        assert proj.default_golden_set_id is None

    def test_other_project_default_untouched(self, db_session) -> None:
        # Two projects, each with their own default. Deleting proj-A's
        # set must not touch proj-B's pointer (even on the same
        # in-memory session).
        proj_a = _seed_project(db_session, "proj-A")
        proj_b = _seed_project(db_session, "proj-B")
        gs_a = _seed_set_with_traces(
            db_session, project_id="proj-A", name="x"
        )
        gs_b = _seed_set_with_traces(
            db_session, project_id="proj-B", name="x"
        )
        proj_a.default_golden_set_id = gs_a.id
        proj_b.default_golden_set_id = gs_b.id
        db_session.commit()

        delete_golden_set(
            db_session, project_id="proj-A", golden_set_id=gs_a.id
        )
        db_session.refresh(proj_b)
        assert proj_b.default_golden_set_id == gs_b.id


# â”€â”€ Option A: route-level override gating â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestReplayDispatchOverrideGating:
    def test_dispatch_route_rejects_override_when_flag_disabled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x")
            gs_id = gs.id

        s = get_settings()
        monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", False)
        response = client.post(
            "/v1/replay/dispatch",
            headers={PROJECT_HEADER: "proj-1"},
            json={
                "golden_set_id": gs_id,
                "git_sha": "sha-aaa",
                "candidate_prompt_override": "new prompt",
            },
        )
        assert response.status_code == 422
        assert "REPLAY_REAL_LLM_ENABLED" in response.json()["detail"]

    def test_dispatch_route_accepts_override_when_flag_enabled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x")
            gs_id = gs.id

        s = get_settings()
        monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", True)
        response = client.post(
            "/v1/replay/dispatch",
            headers={PROJECT_HEADER: "proj-1"},
            json={
                "golden_set_id": gs_id,
                "git_sha": "sha-aaa",
                "candidate_prompt_override": "new prompt",
                "candidate_model_override": "claude-3-haiku",
            },
        )
        assert response.status_code == 202
        body = response.json()
        run_id = body["id"]

        with factory() as session:
            run = get_replay_run(session, project_id="proj-1", run_id=run_id)
            assert run is not None
            summary = parse_summary(run.summary_json)
            assert summary["replay_mode"] == "real_llm"
            assert summary["candidate_prompt_override"] == "new prompt"
            assert summary["candidate_model_override"] == "claude-3-haiku"

    def test_goldens_run_route_rejects_override_when_flag_disabled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x")
            gs_id = gs.id

        s = get_settings()
        monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", False)
        response = client.post(
            f"/v1/goldens/{gs_id}/run",
            headers={PROJECT_HEADER: "proj-1"},
            json={"candidate_model_override": "gpt-4"},
        )
        assert response.status_code == 422
        assert "REPLAY_REAL_LLM_ENABLED" in response.json()["detail"]

    def test_goldens_run_route_accepts_override_when_flag_enabled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x")
            gs_id = gs.id

        s = get_settings()
        monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", True)
        response = client.post(
            f"/v1/goldens/{gs_id}/run",
            headers={PROJECT_HEADER: "proj-1"},
            json={
                "candidate_prompt_override": "override prompt",
                "candidate_model_override": "gpt-4o",
            },
        )
        assert response.status_code == 202
        body = response.json()
        run_id = body["id"]

        with factory() as session:
            run = get_replay_run(session, project_id="proj-1", run_id=run_id)
            assert run is not None
            summary = parse_summary(run.summary_json)
            assert summary["replay_mode"] == "real_llm"
            assert summary["candidate_prompt_override"] == "override prompt"
            assert summary["candidate_model_override"] == "gpt-4o"


# â”€â”€ route: POST /v1/replay/dispatch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestReplayDispatchRoute:
    def test_explicit_set_returns_202_with_summary_url(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")
            gs = _seed_set_with_traces(
                session, project_id="proj-1", name="x"
            )
            gs_id = gs.id

        response = client.post(
            "/v1/replay/dispatch",
            headers={PROJECT_HEADER: "proj-1"},
            json={"golden_set_id": gs_id, "git_sha": "sha-aaa"},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["golden_set_id"] == gs_id
        assert body["status"] == "pending"
        assert body["trigger"] == "github"  # default for this surface
        assert body["git_sha"] == "sha-aaa"
        assert body["idempotent"] is False
        assert body["summary_url"].endswith(f"/evidence?replay_run_id={body['id']}")

    def test_resolves_default_golden_set(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            proj = _seed_project(session, "proj-1")
            gs = _seed_set_with_traces(
                session, project_id="proj-1", name="default"
            )
            proj.default_golden_set_id = gs.id
            session.commit()
            expected_set_id = gs.id

        response = client.post(
            "/v1/replay/dispatch",
            headers={PROJECT_HEADER: "proj-1"},
            json={"git_sha": "sha-aaa"},
        )
        assert response.status_code == 202
        assert response.json()["golden_set_id"] == expected_set_id

    def test_no_set_no_default_returns_422(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")  # default left NULL

        response = client.post(
            "/v1/replay/dispatch",
            headers={PROJECT_HEADER: "proj-1"},
            json={"git_sha": "sha-aaa"},
        )
        assert response.status_code == 422
        assert "default_golden_set_id" in response.json()["detail"]

    def test_dangling_default_returns_422(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            proj = _seed_project(session, "proj-1")
            # Point at a set ID that does not exist (simulates a stale
            # default pointer that escaped the cascade â€” defense in
            # depth).
            proj.default_golden_set_id = "nonexistent-set"
            session.commit()

        response = client.post(
            "/v1/replay/dispatch",
            headers={PROJECT_HEADER: "proj-1"},
            json={"git_sha": "sha-aaa"},
        )
        # Service returns None for missing set â†’ route maps to 422
        # with diagnostic message about updating the default pointer.
        assert response.status_code == 422
        assert "default_golden_set_id" in response.json()["detail"]

    def test_idempotent_replay_skips_enqueue(
        self, client: TestClient, _stub_process_replay_run
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")
            gs = _seed_set_with_traces(
                session, project_id="proj-1", name="x"
            )
            gs_id = gs.id

        first = client.post(
            "/v1/replay/dispatch",
            headers={PROJECT_HEADER: "proj-1"},
            json={"golden_set_id": gs_id, "git_sha": "sha-aaa"},
        )
        assert first.status_code == 202
        first_body = first.json()
        assert first_body["idempotent"] is False

        # Mark the run terminal so the idempotency search hits the
        # "terminal within horizon" branch, then retry.
        with factory() as session:
            run = get_replay_run(
                session, project_id="proj-1", run_id=first_body["id"]
            )
            assert run is not None
            run.status = "pass"
            run.completed_at = datetime.now(timezone.utc)
            session.add(run)
            session.commit()

        # Reset stub call counter to verify second dispatch does NOT
        # enqueue a second worker task.
        _stub_process_replay_run.clear()

        second = client.post(
            "/v1/replay/dispatch",
            headers={PROJECT_HEADER: "proj-1"},
            json={"golden_set_id": gs_id, "git_sha": "sha-aaa"},
        )
        assert second.status_code == 202
        second_body = second.json()
        assert second_body["id"] == first_body["id"]
        assert second_body["idempotent"] is True
        assert second_body["status"] == "pass"
        assert _stub_process_replay_run == []  # no second enqueue

    def test_cross_tenant_explicit_set_returns_404(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-A")
            _seed_project(session, "proj-B")
            gs = _seed_set_with_traces(
                session, project_id="proj-A", name="x"
            )
            gs_id = gs.id

        response = client.post(
            "/v1/replay/dispatch",
            headers={PROJECT_HEADER: "proj-B"},
            json={"golden_set_id": gs_id, "git_sha": "sha-aaa"},
        )
        assert response.status_code == 404

    def test_invalid_trigger_returns_422(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")
            gs = _seed_set_with_traces(
                session, project_id="proj-1", name="x"
            )
            gs_id = gs.id

        response = client.post(
            "/v1/replay/dispatch",
            headers={PROJECT_HEADER: "proj-1"},
            json={"golden_set_id": gs_id, "trigger": "bogus"},
        )
        assert response.status_code == 422

    def test_metadata_persisted_to_summary_json(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")
            gs = _seed_set_with_traces(
                session, project_id="proj-1", name="x"
            )
            gs_id = gs.id

        response = client.post(
            "/v1/replay/dispatch",
            headers={PROJECT_HEADER: "proj-1"},
            json={
                "golden_set_id": gs_id,
                "git_sha": "sha-aaa",
                "branch_name": "feature/foo",
                "pr_number": 42,
                "commit_message": "fix: typo",
            },
        )
        assert response.status_code == 202
        run_id = response.json()["id"]

        with factory() as session:
            run = get_replay_run(
                session, project_id="proj-1", run_id=run_id
            )
            assert run is not None
            summary = parse_summary(run.summary_json)
            assert summary["branch_name"] == "feature/foo"
            assert summary["pr_number"] == 42
            assert summary["commit_message"] == "fix: typo"

    def test_other_tenant_default_does_not_leak(
        self, client: TestClient
    ) -> None:
        # proj-A has a default. proj-B does NOT. Dispatching as proj-B
        # without a body must NOT silently use proj-A's default.
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            proj_a = _seed_project(session, "proj-A")
            _seed_project(session, "proj-B")
            gs_a = _seed_set_with_traces(
                session, project_id="proj-A", name="x"
            )
            proj_a.default_golden_set_id = gs_a.id
            session.commit()

        response = client.post(
            "/v1/replay/dispatch",
            headers={PROJECT_HEADER: "proj-B"},
            json={"git_sha": "sha-aaa"},
        )
        assert response.status_code == 422


# â”€â”€ route: POST /v1/goldens/{id}/run backward-compat with new fields â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestGoldensRunBackwardCompat:
    def test_response_includes_summary_url_and_idempotent_flag(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")
            gs = _seed_set_with_traces(
                session, project_id="proj-1", name="x"
            )
            gs_id = gs.id

        response = client.post(
            f"/v1/goldens/{gs_id}/run",
            headers={PROJECT_HEADER: "proj-1"},
            json={"trigger": "manual"},
        )
        assert response.status_code == 202
        body = response.json()
        assert "summary_url" in body
        assert body["summary_url"].endswith(f"/evidence?replay_run_id={body['id']}")
        assert body["idempotent"] is False

    def test_idempotent_dispatch_via_legacy_endpoint(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")
            gs = _seed_set_with_traces(
                session, project_id="proj-1", name="x"
            )
            gs_id = gs.id

        first = client.post(
            f"/v1/goldens/{gs_id}/run",
            headers={PROJECT_HEADER: "proj-1"},
            json={"trigger": "github", "git_sha": "sha-aaa"},
        )
        second = client.post(
            f"/v1/goldens/{gs_id}/run",
            headers={PROJECT_HEADER: "proj-1"},
            json={"trigger": "github", "git_sha": "sha-aaa"},
        )
        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json()["id"] == second.json()["id"]
        # First call inserts â†’ idempotent False; second call hits the
        # non-terminal branch (run still pending because the worker is
        # stubbed) â†’ idempotent True.
        assert first.json()["idempotent"] is False
        assert second.json()["idempotent"] is True


# -- Quota enforcement ---------------------------------------------------------


class TestQuotaEnforcement:
    """Tests for replay.monthly_runs quota checks on the dispatch route."""

    def test_dispatch_blocked_at_plan_limit(
        self, client: TestClient, monkeypatch
    ) -> None:
        """POST /v1/replay/dispatch ? 402 when monthly limit is exhausted."""
        from app.services import entitlements_resolver
        from app.services.billing_plans import PLAN_ENTITLEMENTS

        limited = dict(PLAN_ENTITLEMENTS["pro"])
        limited["replay.monthly_runs"] = 2
        monkeypatch.setattr(
            entitlements_resolver,
            "get",
            lambda db, org_id, key, default=None: limited.get(key, default),
        )
        monkeypatch.setattr(
            entitlements_resolver, "get_plan_code", lambda db, org_id: "pro"
        )

        project_id = "quota-block-1"
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            for _ in range(2):
                session.add(
                    ReplayRun(
                        id=str(uuid4()),
                        project_id=project_id,
                        golden_set_id="gs-x",
                        status="pass",
                        trigger="manual",
                        created_at=datetime.now(timezone.utc),
                    )
                )
            session.commit()

        resp = client.post(
            "/v1/replay/dispatch",
            json={"golden_set_id": "gs-x"},
            headers={PROJECT_HEADER: project_id},
        )
        assert resp.status_code == 402
        body = resp.json()
        assert body["detail"]["required_entitlement"] == "replay.monthly_runs"
        assert body["detail"]["used"] == 2
        assert body["detail"]["limit"] == 2

    def test_dispatch_allowed_under_limit(
        self, client: TestClient, monkeypatch
    ) -> None:
        """Quota gate passes when under limit; request advances to set resolver.

        No golden set is configured on the project so the response is 422
        (set not found), which proves the request progressed past the quota gate.
        """
        from app.services import entitlements_resolver
        from app.services.billing_plans import PLAN_ENTITLEMENTS

        limited = dict(PLAN_ENTITLEMENTS["pro"])
        limited["replay.monthly_runs"] = 3
        monkeypatch.setattr(
            entitlements_resolver,
            "get",
            lambda db, org_id, key, default=None: limited.get(key, default),
        )
        monkeypatch.setattr(
            entitlements_resolver, "get_plan_code", lambda db, org_id: "pro"
        )

        project_id = "quota-allow-1"
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            for _ in range(2):  # 2 of 3 used — one slot remaining
                session.add(
                    ReplayRun(
                        id=str(uuid4()),
                        project_id=project_id,
                        golden_set_id="gs-y",
                        status="pass",
                        trigger="manual",
                        created_at=datetime.now(timezone.utc),
                    )
                )
            session.commit()

        # No default golden set ? 422 from set resolver, NOT 402 from quota gate.
        resp = client.post(
            "/v1/replay/dispatch",
            json={},
            headers={PROJECT_HEADER: project_id},
        )
        assert resp.status_code == 422
        assert "golden_set_id" in resp.json()["detail"].lower()

    def test_dispatch_enterprise_unlimited(
        self, client: TestClient, monkeypatch
    ) -> None:
        """Enterprise plan (limit=-1) is never quota-blocked."""
        from app.services import entitlements_resolver
        from app.services.billing_plans import PLAN_ENTITLEMENTS

        enterprise = dict(PLAN_ENTITLEMENTS["enterprise"])
        monkeypatch.setattr(
            entitlements_resolver,
            "get",
            lambda db, org_id, key, default=None: enterprise.get(key, default),
        )
        monkeypatch.setattr(
            entitlements_resolver, "get_plan_code", lambda db, org_id: "enterprise"
        )

        project_id = "quota-ent-1"
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            for _ in range(100):  # far beyond any numeric limit
                session.add(
                    ReplayRun(
                        id=str(uuid4()),
                        project_id=project_id,
                        golden_set_id="gs-ent",
                        status="pass",
                        trigger="manual",
                        created_at=datetime.now(timezone.utc),
                    )
                )
            session.commit()

        # No golden set ? 422 from set resolver, NOT 402, proving enterprise
        # is never quota-gated.
        resp = client.post(
            "/v1/replay/dispatch",
            json={},
            headers={PROJECT_HEADER: project_id},
        )
        assert resp.status_code == 422
