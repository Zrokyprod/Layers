"""Tests for the Pilot-tier replay-runs service + 4 new endpoints
(Module 4.2):

  - POST /v1/goldens/{id}/run                  → dispatch
  - GET  /v1/replay/runs                       → list (filters + pagination)
  - GET  /v1/replay/runs/{id}                  → detail w/ embedded traces
  - POST /v1/calls/{id}/mark-golden            → snapshot a Call into a set

Service-level coverage: dispatch validation, summary snapshot, list filters,
list_run_traces, mark_call_as_golden tenant guards.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Anomaly, Call, GoldenSet, GoldenTrace, ReplayRun, ReplayRunTrace
from app.services.anomalies import compute_fingerprint
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.goldens import (
    ACTIVE_GOLDEN_REQUIRES_EXPECTED_BEHAVIOR,
    GOLDEN_TRACE_STATUS_ACTIVE,
    GOLDEN_TRACE_STATUS_DRAFT,
    add_trace,
    create_golden_set,
)
from app.services.replay_runs import (
    REPLAY_MODE_MOCKED_TOOL,
    REPLAY_MODE_REAL_LLM,
    REPLAY_MODE_STUB,
    VALID_RUN_STATUSES,
    VALID_TRIGGERS,
    _STUB_MODE_WARNING,
    _resolve_replay_mode,
    create_replay_from_call,
    dispatch_replay_run,
    get_replay_run,
    list_replay_runs,
    list_run_traces,
    mark_call_as_golden,
    parse_summary,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_replay_runs_svc.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_replay_runs_route.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def override_get_db_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session

    with TestClient(app) as test_client:
        test_client._session_factory = session_factory  # type: ignore[attr-defined]
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


PROJECT_HEADER = "X-Project-Id"


# Module 6 added router-level plan-gates on /v1/replay/runs/* and
# /v1/goldens/{id}/run plus an endpoint-level gate on
# /v1/calls/{id}/mark-golden — all keyed on `pilot.autopilot_enabled`.
# Bypass for this file (the gate is tested separately in
# tests/test_plan_gates.py).
@pytest.fixture(autouse=True)
def _grant_pilot_tier(monkeypatch):
    from app.services import entitlements_resolver
    from app.services.billing_plans import PLAN_ENTITLEMENTS

    pro_dict = dict(PLAN_ENTITLEMENTS["pro"])
    monkeypatch.setattr(
        entitlements_resolver, "has", lambda db, org_id, key: True
    )
    monkeypatch.setattr(
        entitlements_resolver,
        "get",
        lambda db, org_id, key, default=None: pro_dict.get(key, default),
    )
    monkeypatch.setattr(
        entitlements_resolver, "resolve_all", lambda db, org_id: dict(pro_dict)
    )
    monkeypatch.setattr(
        entitlements_resolver, "get_plan_code", lambda db, org_id: "pro"
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _seed_call(session, *, project_id: str, call_id: str, **overrides) -> Call:
    base = {
        "id": call_id,
        "project_id": project_id,
        "event_id": f"evt-{call_id}",
        "status": "ok",
        "input_tokens": 10,
        "output_tokens": 20,
        "total_tokens": 30,
        "cost_total": 0.0042,
        "latency_ms": 150,
    }
    base.update(overrides)
    call = Call(**base)
    session.add(call)
    session.commit()
    return call


def _seed_set_with_traces(session, *, project_id: str, name: str, n_traces: int = 0) -> GoldenSet:
    gs = create_golden_set(session, project_id=project_id, name=name)
    for i in range(n_traces):
        add_trace(
            session,
            project_id=project_id,
            golden_set_id=gs.id,
            expected_output_text=f"out-{i}",
        )
    return gs


# ── service: dispatch_replay_run ─────────────────────────────────────────────


# ── Option A: _resolve_replay_mode ─────────────────────────────────────────


class TestResolveReplayMode:
    def test_no_override_returns_stub(self) -> None:
        mode, warning = _resolve_replay_mode(
            candidate_prompt_override=None,
            candidate_model_override=None,
        )
        assert mode == REPLAY_MODE_STUB
        assert warning == _STUB_MODE_WARNING

    def test_whitespace_only_override_treated_as_none(self) -> None:
        mode, warning = _resolve_replay_mode(
            candidate_prompt_override="   ",
            candidate_model_override="\t\n",
        )
        assert mode == REPLAY_MODE_STUB
        assert warning == _STUB_MODE_WARNING

    def test_override_without_flag_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = get_settings()
        monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", False)
        with pytest.raises(ValueError, match="REPLAY_REAL_LLM_ENABLED"):
            _resolve_replay_mode(
                candidate_prompt_override="new prompt",
                candidate_model_override=None,
            )

    def test_override_with_flag_returns_real_llm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        s = get_settings()
        monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", True)
        mode, warning = _resolve_replay_mode(
            candidate_prompt_override="new prompt",
            candidate_model_override="claude-3-haiku",
        )
        assert mode == REPLAY_MODE_REAL_LLM
        assert warning is None


# ── service: dispatch_replay_run ─────────────────────────────────────────────


class TestDispatchReplayRun:
    def test_dispatch_creates_pending_run(self, db_session) -> None:
        gs = _seed_set_with_traces(
            db_session, project_id="proj-1", name="x", n_traces=3
        )
        run = dispatch_replay_run(
            db_session, project_id="proj-1", golden_set_id=gs.id
        )
        assert run is not None
        assert run.project_id == "proj-1"
        assert run.golden_set_id == gs.id
        assert run.status == "pending"
        assert run.trigger == "manual"
        assert run.git_sha is None
        summary = parse_summary(run.summary_json)
        assert summary["trace_count_at_dispatch"] == 3

    def test_dispatch_with_git_trigger_and_sha(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        run = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            trigger="github",
            git_sha="abc123def",
        )
        assert run is not None
        assert run.trigger == "github"
        assert run.git_sha == "abc123def"

    def test_invalid_trigger_raises(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        with pytest.raises(ValueError, match="trigger"):
            dispatch_replay_run(
                db_session,
                project_id="proj-1",
                golden_set_id=gs.id,
                trigger="bogus",
            )

    def test_missing_golden_set_returns_none(self, db_session) -> None:
        run = dispatch_replay_run(
            db_session, project_id="proj-1", golden_set_id="missing"
        )
        assert run is None

    def test_cross_tenant_golden_set_returns_none(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-A", name="x")
        run = dispatch_replay_run(
            db_session, project_id="proj-B", golden_set_id=gs.id
        )
        assert run is None

    def test_rejects_override_when_real_llm_disabled(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        s = get_settings()
        monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", False)
        with pytest.raises(ValueError, match="REPLAY_REAL_LLM_ENABLED"):
            dispatch_replay_run(
                db_session,
                project_id="proj-1",
                golden_set_id=gs.id,
                candidate_prompt_override="new prompt",
            )

    def test_stamps_replay_mode_stub(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        run = dispatch_replay_run(db_session, project_id="proj-1", golden_set_id=gs.id)
        assert run is not None
        summary = parse_summary(run.summary_json)
        assert summary["replay_mode"] == REPLAY_MODE_STUB
        assert summary["replay_mode_warning"] == _STUB_MODE_WARNING
        assert "candidate_prompt_override" not in summary
        assert "candidate_model_override" not in summary

    def test_stamps_replay_mode_real_llm_with_overrides(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        s = get_settings()
        monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", True)
        run = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            candidate_prompt_override="new prompt",
            candidate_model_override="claude-3-haiku",
        )
        assert run is not None
        summary = parse_summary(run.summary_json)
        assert summary["replay_mode"] == REPLAY_MODE_REAL_LLM
        assert "replay_mode_warning" not in summary
        assert summary["candidate_prompt_override"] == "new prompt"
        assert summary["candidate_model_override"] == "claude-3-haiku"

    def test_stamps_requested_mode_with_executor_compatibility(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        s = get_settings()
        monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", True)
        run = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            replay_mode=REPLAY_MODE_MOCKED_TOOL,
        )
        assert run is not None
        summary = parse_summary(run.summary_json)
        assert summary["requested_replay_mode"] == REPLAY_MODE_MOCKED_TOOL
        assert summary["replay_mode"] == REPLAY_MODE_REAL_LLM
        assert summary["verification_status"] == "pending_real_comparison"

    def test_create_replay_from_call_creates_one_click_run(self, db_session) -> None:
        _seed_call(
            db_session,
            project_id="proj-1",
            call_id="call-1",
            payload_json=json.dumps({"response": "ok"}),
        )
        run = create_replay_from_call(
            db_session,
            project_id="proj-1",
            call_id="call-1",
        )
        assert run is not None
        summary = parse_summary(run.summary_json)
        assert summary["source_kind"] == "call"
        assert summary["source_call_id"] == "call-1"
        assert summary["trace_count_at_dispatch"] == 1
        trace = db_session.execute(
            select(GoldenTrace).where(GoldenTrace.golden_set_id == run.golden_set_id)
        ).scalar_one()
        assert trace.call_id == "call-1"
        assert trace.status == GOLDEN_TRACE_STATUS_ACTIVE
        assert trace.expected_output_text == "ok"
        assert trace.source_output_text == "ok"

    def test_override_bypasses_idempotency(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        s = get_settings()
        monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", True)
        first = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            git_sha="sha-aaa",
            candidate_prompt_override="prompt A",
        )
        second = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            git_sha="sha-aaa",
            candidate_prompt_override="prompt B",
        )
        assert first is not None and second is not None
        assert first.id != second.id

    def test_prompt_override_truncated(self, db_session, monkeypatch: pytest.MonkeyPatch) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        s = get_settings()
        monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", True)
        long_prompt = "x" * 5000
        run = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            candidate_prompt_override=long_prompt,
        )
        assert run is not None
        summary = parse_summary(run.summary_json)
        stored = summary["candidate_prompt_override"]
        assert len(stored) == 4000
        assert stored == "x" * 4000

    def test_model_override_stripped(self, db_session, monkeypatch: pytest.MonkeyPatch) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        s = get_settings()
        monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", True)
        run = dispatch_replay_run(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            candidate_model_override="  claude-3-haiku  ",
        )
        assert run is not None
        summary = parse_summary(run.summary_json)
        assert summary["candidate_model_override"] == "claude-3-haiku"


# ── service: read paths ──────────────────────────────────────────────────────


class TestReadReplayRuns:
    def test_get_returns_none_for_missing(self, db_session) -> None:
        assert get_replay_run(
            db_session, project_id="proj-1", run_id="missing"
        ) is None

    def test_get_cross_tenant_returns_none(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-A", name="x")
        run = dispatch_replay_run(
            db_session, project_id="proj-A", golden_set_id=gs.id
        )
        assert run is not None
        assert get_replay_run(
            db_session, project_id="proj-B", run_id=run.id
        ) is None

    def test_list_tenant_isolation(self, db_session) -> None:
        gs_a = _seed_set_with_traces(db_session, project_id="proj-A", name="a")
        gs_b = _seed_set_with_traces(db_session, project_id="proj-B", name="b")
        dispatch_replay_run(db_session, project_id="proj-A", golden_set_id=gs_a.id)
        dispatch_replay_run(db_session, project_id="proj-B", golden_set_id=gs_b.id)

        rows = list_replay_runs(db_session, project_id="proj-A", limit=10)
        assert len(rows) == 1
        assert rows[0].project_id == "proj-A"

    def test_list_filter_by_golden_set(self, db_session) -> None:
        gs1 = _seed_set_with_traces(db_session, project_id="proj-1", name="set-1")
        gs2 = _seed_set_with_traces(db_session, project_id="proj-1", name="set-2")
        dispatch_replay_run(db_session, project_id="proj-1", golden_set_id=gs1.id)
        dispatch_replay_run(db_session, project_id="proj-1", golden_set_id=gs2.id)

        only_set1 = list_replay_runs(
            db_session, project_id="proj-1", golden_set_id=gs1.id, limit=10
        )
        assert len(only_set1) == 1
        assert only_set1[0].golden_set_id == gs1.id

    def test_list_filter_by_status(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        run1 = dispatch_replay_run(
            db_session, project_id="proj-1", golden_set_id=gs.id
        )
        run2 = dispatch_replay_run(
            db_session, project_id="proj-1", golden_set_id=gs.id
        )
        # promote run2 to running
        run2.status = "running"
        db_session.add(run2)
        db_session.commit()

        pending = list_replay_runs(
            db_session, project_id="proj-1", status="pending", limit=10
        )
        running = list_replay_runs(
            db_session, project_id="proj-1", status="running", limit=10
        )
        assert {r.id for r in pending} == {run1.id}
        assert {r.id for r in running} == {run2.id}

    def test_list_invalid_status_raises(self, db_session) -> None:
        with pytest.raises(ValueError, match="status"):
            list_replay_runs(
                db_session, project_id="proj-1", status="bogus"
            )

    def test_list_run_traces_missing_returns_none(self, db_session) -> None:
        assert list_run_traces(
            db_session, project_id="proj-1", run_id="missing"
        ) is None

    def test_list_run_traces_returns_ordered_rows(self, db_session) -> None:
        gs = _seed_set_with_traces(db_session, project_id="proj-1", name="x")
        run = dispatch_replay_run(
            db_session, project_id="proj-1", golden_set_id=gs.id
        )
        # Manually seed 3 ReplayRunTrace rows
        for n in range(3):
            db_session.add(ReplayRunTrace(
                replay_run_id=run.id,
                project_id="proj-1",
                status="pass" if n % 2 == 0 else "fail",
            ))
        db_session.commit()

        traces = list_run_traces(db_session, project_id="proj-1", run_id=run.id)
        assert traces is not None
        assert len(traces) == 3


# ── service: mark_call_as_golden ─────────────────────────────────────────────


class TestMarkCallAsGolden:
    def test_snapshot_call_baselines(self, db_session) -> None:
        _seed_call(
            db_session,
            project_id="proj-1",
            call_id="call-1",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost_total=0.0123,
            latency_ms=275.5,
            status="failed",
            error_code="OUTPUT_MISMATCH",
            payload_json=json.dumps({"response": "bad original output"}),
        )
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        trace = mark_call_as_golden(
            db_session,
            project_id="proj-1",
            call_id="call-1",
            golden_set_id=gs.id,
        )
        assert trace is not None
        assert trace.call_id == "call-1"
        assert trace.status == GOLDEN_TRACE_STATUS_DRAFT
        assert trace.expected_output_text is None
        assert trace.source_output_text == "bad original output"
        evidence = json.loads(trace.source_evidence_json)
        assert evidence["call_id"] == "call-1"
        assert evidence["status"] == "failed"
        assert trace.expected_tokens == 150
        assert float(trace.expected_cost_usd) == pytest.approx(0.0123)
        assert trace.expected_latency_ms == 275

    def test_with_explicit_output_and_criteria(self, db_session) -> None:
        _seed_call(db_session, project_id="proj-1", call_id="call-2")
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        trace = mark_call_as_golden(
            db_session,
            project_id="proj-1",
            call_id="call-2",
            golden_set_id=gs.id,
            expected_output_text="hello world",
            criteria_json='{"contains":"hello"}',
            weight=2.5,
        )
        assert trace is not None
        assert trace.status == GOLDEN_TRACE_STATUS_ACTIVE
        assert trace.expected_output_text == "hello world"
        assert trace.criteria_json == '{"contains":"hello"}'
        assert float(trace.weight) == 2.5

    def test_active_without_expected_behavior_rejected(self, db_session) -> None:
        _seed_call(db_session, project_id="proj-1", call_id="call-active")
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        with pytest.raises(
            ValueError, match=ACTIVE_GOLDEN_REQUIRES_EXPECTED_BEHAVIOR
        ):
            mark_call_as_golden(
                db_session,
                project_id="proj-1",
                call_id="call-active",
                golden_set_id=gs.id,
                status=GOLDEN_TRACE_STATUS_ACTIVE,
            )

    def test_failed_call_with_explicit_output_can_create_active(self, db_session) -> None:
        _seed_call(
            db_session,
            project_id="proj-1",
            call_id="call-verified",
            status="failed",
            payload_json=json.dumps({"response": "source failure"}),
        )
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        trace = mark_call_as_golden(
            db_session,
            project_id="proj-1",
            call_id="call-verified",
            golden_set_id=gs.id,
            expected_output_text="verified expected behavior",
        )
        assert trace is not None
        assert trace.status == GOLDEN_TRACE_STATUS_ACTIVE
        assert trace.expected_output_text == "verified expected behavior"
        assert trace.source_output_text == "source failure"

    def test_missing_call_returns_none(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        result = mark_call_as_golden(
            db_session,
            project_id="proj-1",
            call_id="missing-call",
            golden_set_id=gs.id,
        )
        assert result is None

    def test_missing_golden_set_returns_none(self, db_session) -> None:
        _seed_call(db_session, project_id="proj-1", call_id="call-1")
        result = mark_call_as_golden(
            db_session,
            project_id="proj-1",
            call_id="call-1",
            golden_set_id="missing-set",
        )
        assert result is None

    def test_cross_tenant_call_returns_none(self, db_session) -> None:
        _seed_call(db_session, project_id="proj-A", call_id="call-x")
        gs = create_golden_set(db_session, project_id="proj-B", name="x")
        # tenant=proj-B trying to use proj-A's call
        result = mark_call_as_golden(
            db_session,
            project_id="proj-B",
            call_id="call-x",
            golden_set_id=gs.id,
        )
        assert result is None

    def test_invalid_weight_raises(self, db_session) -> None:
        _seed_call(db_session, project_id="proj-1", call_id="call-1")
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        with pytest.raises(ValueError, match="weight"):
            mark_call_as_golden(
                db_session,
                project_id="proj-1",
                call_id="call-1",
                golden_set_id=gs.id,
                weight=0,
            )


# ── route: POST /v1/goldens/{id}/run ─────────────────────────────────────────


class TestRunDispatchRoute:
    def test_dispatch_202(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x", n_traces=2)
            gs_id = gs.id

        response = client.post(
            f"/v1/goldens/{gs_id}/run",
            headers={PROJECT_HEADER: "proj-1"},
            json={"trigger": "manual"},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["golden_set_id"] == gs_id
        assert body["trigger"] == "manual"
        assert body["status"] == "pending"

    def test_dispatch_with_default_body(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x")
            gs_id = gs.id

        # No body — endpoint should default trigger=manual
        response = client.post(
            f"/v1/goldens/{gs_id}/run",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 202
        assert response.json()["trigger"] == "manual"

    def test_invalid_trigger_422(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x")
            gs_id = gs.id
        response = client.post(
            f"/v1/goldens/{gs_id}/run",
            headers={PROJECT_HEADER: "proj-1"},
            json={"trigger": "bogus"},
        )
        assert response.status_code == 422

    def test_missing_set_404(self, client: TestClient) -> None:
        response = client.post(
            "/v1/goldens/missing/run",
            headers={PROJECT_HEADER: "proj-1"},
            json={"trigger": "manual"},
        )
        assert response.status_code == 404

    def test_cross_tenant_404(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-A", name="x")
            gs_id = gs.id
        response = client.post(
            f"/v1/goldens/{gs_id}/run",
            headers={PROJECT_HEADER: "proj-B"},
            json={"trigger": "manual"},
        )
        assert response.status_code == 404


# ── route: GET /v1/replay/runs ───────────────────────────────────────────────


class TestListRunsRoute:
    def test_empty(self, client: TestClient) -> None:
        response = client.get(
            "/v1/replay/runs", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["next_cursor"] is None
        assert body["total_in_page"] == 0

    def test_list_includes_summary(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x", n_traces=4)
            dispatch_replay_run(session, project_id="proj-1", golden_set_id=gs.id)

        response = client.get(
            "/v1/replay/runs", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["summary"]["trace_count_at_dispatch"] == 4
        assert items[0]["summary"]["pass_count"] == 0

    def test_filter_by_golden_set(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs1 = _seed_set_with_traces(session, project_id="proj-1", name="set-1")
            gs2 = _seed_set_with_traces(session, project_id="proj-1", name="set-2")
            gs1_id = gs1.id
            gs2_id = gs2.id
            dispatch_replay_run(session, project_id="proj-1", golden_set_id=gs1_id)
            dispatch_replay_run(session, project_id="proj-1", golden_set_id=gs2_id)

        response = client.get(
            f"/v1/replay/runs?golden_set_id={gs1_id}",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["golden_set_id"] == gs1_id

    def test_filter_by_status(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x")
            dispatch_replay_run(session, project_id="proj-1", golden_set_id=gs.id)

        response = client.get(
            "/v1/replay/runs?status=pending",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

        empty = client.get(
            "/v1/replay/runs?status=running",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        assert empty["items"] == []

    def test_invalid_status_422(self, client: TestClient) -> None:
        response = client.get(
            "/v1/replay/runs?status=bogus",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_invalid_cursor_422(self, client: TestClient) -> None:
        response = client.get(
            "/v1/replay/runs?cursor=not-base64",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_pagination(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-page", name="x")
            base = datetime.now(timezone.utc)
            for n in range(5):
                run = dispatch_replay_run(
                    session, project_id="proj-page", golden_set_id=gs.id
                )
                # back-date for deterministic cursor ordering
                run.created_at = base - timedelta(seconds=10 * (5 - n))
                session.add(run)
            session.commit()

        first = client.get(
            "/v1/replay/runs?limit=2",
            headers={PROJECT_HEADER: "proj-page"},
        ).json()
        assert len(first["items"]) == 2
        assert first["next_cursor"] is not None

        second = client.get(
            f"/v1/replay/runs?limit=2&cursor={first['next_cursor']}",
            headers={PROJECT_HEADER: "proj-page"},
        ).json()
        assert len(second["items"]) == 2
        assert second["next_cursor"] is not None

        third = client.get(
            f"/v1/replay/runs?limit=2&cursor={second['next_cursor']}",
            headers={PROJECT_HEADER: "proj-page"},
        ).json()
        assert len(third["items"]) == 1
        assert third["next_cursor"] is None

        seen = (
            [i["id"] for i in first["items"]]
            + [i["id"] for i in second["items"]]
            + [i["id"] for i in third["items"]]
        )
        assert len(set(seen)) == 5

    def test_tenant_isolation(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs_a = _seed_set_with_traces(session, project_id="proj-A", name="a")
            gs_b = _seed_set_with_traces(session, project_id="proj-B", name="b")
            dispatch_replay_run(session, project_id="proj-A", golden_set_id=gs_a.id)
            dispatch_replay_run(session, project_id="proj-B", golden_set_id=gs_b.id)

        response = client.get(
            "/v1/replay/runs", headers={PROJECT_HEADER: "proj-A"}
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert {i["project_id"] for i in items} == {"proj-A"}


# ── route: GET /v1/replay/runs/{id} ──────────────────────────────────────────


class TestRunDetailRoute:
    def test_404_missing(self, client: TestClient) -> None:
        response = client.get(
            "/v1/replay/runs/missing",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 404

    def test_returns_run_with_traces(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x")
            run = dispatch_replay_run(
                session, project_id="proj-1", golden_set_id=gs.id
            )
            run_id = run.id
            for n in range(2):
                session.add(ReplayRunTrace(
                    replay_run_id=run_id,
                    project_id="proj-1",
                    status="pass" if n == 0 else "fail",
                    diff_metric=float(n),
                ))
            session.commit()

        response = client.get(
            f"/v1/replay/runs/{run_id}",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == run_id
        assert len(body["traces"]) == 2
        statuses = sorted(t["status"] for t in body["traces"])
        assert statuses == ["fail", "pass"]

    def test_cross_tenant_404(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-A", name="x")
            run = dispatch_replay_run(
                session, project_id="proj-A", golden_set_id=gs.id
            )
            run_id = run.id

        response = client.get(
            f"/v1/replay/runs/{run_id}",
            headers={PROJECT_HEADER: "proj-B"},
        )
        assert response.status_code == 404


# ── Option A: replay_mode + override exposure in GET responses ──────────────


class TestReplayModeInResponse:
    def test_list_includes_replay_mode_stub(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x")
            dispatch_replay_run(session, project_id="proj-1", golden_set_id=gs.id)

        response = client.get("/v1/replay/runs", headers={PROJECT_HEADER: "proj-1"})
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["replay_mode"] == "stub"
        assert _STUB_MODE_WARNING in item["replay_mode_warning"]
        assert item["candidate_prompt_override"] is None
        assert item["candidate_model_override"] is None

    def test_detail_includes_real_llm_overrides(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x")
            s = get_settings()
            monkeypatch.setattr(s, "REPLAY_REAL_LLM_ENABLED", True)
            run = dispatch_replay_run(
                session,
                project_id="proj-1",
                golden_set_id=gs.id,
                candidate_prompt_override="new prompt",
                candidate_model_override="claude-3-haiku",
            )
            run_id = run.id

        response = client.get(
            f"/v1/replay/runs/{run_id}", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["replay_mode"] == "real_llm"
        assert body["replay_mode_warning"] is None
        assert body["candidate_prompt_override"] == "new prompt"
        assert body["candidate_model_override"] == "claude-3-haiku"

    def test_backfills_warning_for_legacy_stub_rows(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x")
            run = dispatch_replay_run(session, project_id="proj-1", golden_set_id=gs.id)
            # Simulate a pre-Option-A row by stripping replay_mode from summary_json
            run.summary_json = json.dumps({"trace_count_at_dispatch": 1})
            session.add(run)
            session.commit()
            run_id = run.id

        response = client.get(
            f"/v1/replay/runs/{run_id}", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["replay_mode"] == "stub"
        assert _STUB_MODE_WARNING in body["replay_mode_warning"]

    def test_backfills_source_context_from_legacy_summary_keys(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = _seed_set_with_traces(session, project_id="proj-1", name="x")
            run = dispatch_replay_run(session, project_id="proj-1", golden_set_id=gs.id)
            run.summary_json = json.dumps(
                {
                    "trace_count_at_dispatch": 1,
                    "source_kind": "issue",
                    "source_id": "issue-legacy",
                    "source_issue_id": "issue-legacy",
                    "source_call_id": "call-legacy",
                    "source_issue_failure_code": "OUTPUT_MISMATCH",
                    "source_issue_severity": "high",
                },
                separators=(",", ":"),
            )
            session.add(run)
            session.commit()
            run_id = run.id

        response = client.get(
            f"/v1/replay/runs/{run_id}", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        context = response.json()["source_context"]
        assert context["kind"] == "issue"
        assert context["issue_id"] == "issue-legacy"
        assert context["call_id"] == "call-legacy"
        assert context["failure_code"] == "OUTPUT_MISMATCH"


# ── route: POST /v1/calls/{call_id}/mark-golden ──────────────────────────────



class TestCreateReplayFromIssueRoute:
    def test_creates_one_click_replay_from_issue(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.api.routes import replay_runs as replay_runs_routes

        enqueued: list[tuple[str, str]] = []
        monkeypatch.setattr(
            replay_runs_routes,
            "_enqueue_replay_run",
            lambda run_id, tenant_id: enqueued.append((run_id, tenant_id)),
        )

        now = datetime.now(timezone.utc)
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_call(
                session,
                project_id="proj-1",
                call_id="call-issue",
                payload_json=json.dumps({"response": "issue fixed"}),
            )
            issue = Anomaly(
                id="issue-1",
                project_id="proj-1",
                fingerprint=compute_fingerprint(
                    detector="UNKNOWN",
                    prompt_fingerprint="fp-issue",
                    agent_name="support-agent",
                ),
                detector="UNKNOWN",
                severity="high",
                status="open",
                occurrence_count=1,
                first_seen_at=now - timedelta(minutes=5),
                last_seen_at=now,
                sample_call_ids_json=json.dumps(["call-issue"]),
                evidence_json=json.dumps(
                    {
                        "failure_code": "OUTPUT_MISMATCH",
                        "prompt_fingerprint": "fp-issue",
                        "agent_name": "support-agent",
                        "root_cause": "Support agent returned the wrong refund status.",
                        "legacy_issue": {
                            "failure_code": "OUTPUT_MISMATCH",
                            "prompt_fingerprint": "fp-issue",
                            "agent_name": "support-agent",
                            "sample_call_id": "call-issue",
                        },
                    },
                    separators=(",", ":"),
                ),
            )
            session.add(issue)
            session.commit()

        response = client.post(
            "/v1/replay/runs/from-issue/issue-1",
            headers={PROJECT_HEADER: "proj-1"},
            json={"replay_mode": "stub"},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["replay_mode"] == "stub"
        assert body["summary_url"].endswith(f"/replay/{body['id']}")
        assert enqueued == [(body["id"], "proj-1")]

        with factory() as session:
            run = session.get(ReplayRun, body["id"])
            assert run is not None
            summary = parse_summary(run.summary_json)
            assert summary["source_kind"] == "issue"
            assert summary["source_issue_id"] == "issue-1"
            assert summary["source_call_id"] == "call-issue"
            assert summary["source_context"]["reason"] == "Support agent returned the wrong refund status."
            assert summary["source_context"]["issue_id"] == "issue-1"
            trace = session.execute(
                select(GoldenTrace).where(GoldenTrace.golden_set_id == run.golden_set_id)
            ).scalar_one()
            assert trace.call_id == "call-issue"
            assert trace.status == GOLDEN_TRACE_STATUS_ACTIVE
            assert trace.expected_output_text == "issue fixed"
            assert trace.source_output_text == "issue fixed"

        detail = client.get(
            f"/v1/replay/runs/{body['id']}",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert detail.status_code == 200
        context = detail.json()["source_context"]
        assert context["title"] == "support-agent - output mismatch"
        assert context["reason"] == "Support agent returned the wrong refund status."
        assert context["failure_code"] == "OUTPUT_MISMATCH"

    def test_discovery_issue_replay_maps_discovery_source_context(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.api.routes import replay_runs as replay_runs_routes

        monkeypatch.setattr(replay_runs_routes, "_enqueue_replay_run", lambda run_id, tenant_id: None)
        now = datetime.now(timezone.utc)
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_call(
                session,
                project_id="proj-1",
                call_id="call-discovery",
                payload_json=json.dumps({"response": "tool skipped"}),
            )
            issue = Anomaly(
                id="issue-discovery",
                project_id="proj-1",
                fingerprint=compute_fingerprint(
                    detector="UNKNOWN",
                    prompt_fingerprint=None,
                    agent_name=None,
                    extra="sig-refund-tool",
                ),
                detector="BEHAVIORAL_DRIFT",
                severity="high",
                status="open",
                occurrence_count=4,
                first_seen_at=now - timedelta(hours=1),
                last_seen_at=now,
                sample_call_ids_json=json.dumps(["call-discovery"]),
                evidence_json=json.dumps(
                    {
                        "source": "discovery",
                        "summary": "refund_agent skipped get_refund_status in 96% normal trace context",
                        "confidence": 0.91,
                        "discovery_signature": "sig-refund-tool",
                        "primary_dimension": "missing_critical_tool",
                        "workflow_name": "refund-resolution",
                    },
                    separators=(",", ":"),
                ),
            )
            session.add(issue)
            session.commit()

        response = client.post(
            "/v1/replay/runs/from-issue/issue-discovery",
            headers={PROJECT_HEADER: "proj-1"},
            json={"replay_mode": "stub"},
        )
        assert response.status_code == 202
        detail = client.get(
            f"/v1/replay/runs/{response.json()['id']}",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert detail.status_code == 200
        context = detail.json()["source_context"]
        assert context["origin"] == "discovery"
        assert context["reason"] == "refund_agent skipped get_refund_status in 96% normal trace context"
        assert context["confidence"] == pytest.approx(0.91)
        assert context["discovery_signature"] == "sig-refund-tool"

class TestMarkGoldenRoute:
    def test_201(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_call(
                session,
                project_id="proj-1",
                call_id="call-1",
                total_tokens=42,
                cost_total=0.05,
                latency_ms=200,
                status="failed",
                payload_json=json.dumps({"response": "bad original output"}),
            )
            gs = create_golden_set(session, project_id="proj-1", name="x")
            gs_id = gs.id

        response = client.post(
            "/v1/calls/call-1/mark-golden",
            headers={PROJECT_HEADER: "proj-1"},
            json={"golden_set_id": gs_id, "weight": 1.5},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["call_id"] == "call-1"
        assert body["golden_set_id"] == gs_id
        assert body["status"] == GOLDEN_TRACE_STATUS_DRAFT
        assert body["expected_output_text"] is None
        assert body["source_output_text"] == "bad original output"
        evidence = json.loads(body["source_evidence_json"])
        assert evidence["call_id"] == "call-1"
        assert body["expected_tokens"] == 42
        assert float(body["expected_cost_usd"]) == pytest.approx(0.05)
        assert body["expected_latency_ms"] == 200
        assert body["weight"] == 1.5

    def test_active_without_expected_behavior_422(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_call(session, project_id="proj-1", call_id="call-1")
            gs = create_golden_set(session, project_id="proj-1", name="x")
            gs_id = gs.id

        response = client.post(
            "/v1/calls/call-1/mark-golden",
            headers={PROJECT_HEADER: "proj-1"},
            json={"golden_set_id": gs_id, "status": "active"},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == ACTIVE_GOLDEN_REQUIRES_EXPECTED_BEHAVIOR

    def test_explicit_expected_output_returns_active(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_call(
                session,
                project_id="proj-1",
                call_id="call-1",
                status="failed",
                payload_json=json.dumps({"response": "source failure"}),
            )
            gs = create_golden_set(session, project_id="proj-1", name="x")
            gs_id = gs.id

        response = client.post(
            "/v1/calls/call-1/mark-golden",
            headers={PROJECT_HEADER: "proj-1"},
            json={
                "golden_set_id": gs_id,
                "expected_output_text": "verified expected behavior",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == GOLDEN_TRACE_STATUS_ACTIVE
        assert body["expected_output_text"] == "verified expected behavior"
        assert body["source_output_text"] == "source failure"

    def test_missing_call_404(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = create_golden_set(session, project_id="proj-1", name="x")
            gs_id = gs.id

        response = client.post(
            "/v1/calls/missing-call/mark-golden",
            headers={PROJECT_HEADER: "proj-1"},
            json={"golden_set_id": gs_id},
        )
        assert response.status_code == 404

    def test_missing_set_404(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_call(session, project_id="proj-1", call_id="call-1")
            session.commit()

        response = client.post(
            "/v1/calls/call-1/mark-golden",
            headers={PROJECT_HEADER: "proj-1"},
            json={"golden_set_id": "missing-set"},
        )
        assert response.status_code == 404

    def test_invalid_weight_422(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_call(session, project_id="proj-1", call_id="call-1")
            gs = create_golden_set(session, project_id="proj-1", name="x")
            gs_id = gs.id

        response = client.post(
            "/v1/calls/call-1/mark-golden",
            headers={PROJECT_HEADER: "proj-1"},
            json={"golden_set_id": gs_id, "weight": 0},
        )
        assert response.status_code == 422

    def test_cross_tenant_call_404(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_call(session, project_id="proj-A", call_id="call-x")
            gs = create_golden_set(session, project_id="proj-B", name="x")
            gs_id = gs.id

        # proj-B trying to mark proj-A's call → 404 (call lookup scoped to tenant)
        response = client.post(
            "/v1/calls/call-x/mark-golden",
            headers={PROJECT_HEADER: "proj-B"},
            json={"golden_set_id": gs_id},
        )
        assert response.status_code == 404


# ── invariants ───────────────────────────────────────────────────────────────


class TestInvariants:
    def test_valid_triggers_match_db_check(self) -> None:
        assert VALID_TRIGGERS == frozenset({"manual", "github", "schedule"})

    def test_valid_run_statuses_match_db_check(self) -> None:
        assert VALID_RUN_STATUSES == frozenset(
            {"pending", "running", "pass", "warn", "fail", "not_verified", "error"}
        )
