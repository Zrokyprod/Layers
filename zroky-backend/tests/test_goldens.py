"""Tests for the Pilot-tier goldens service + /v1/goldens route surface.

Module 4.1 coverage:
  - Service: CRUD for golden sets, uniqueness constraint, partial update,
    cascade delete of traces, cross-tenant guard, trace add/remove,
    call_id ownership check.
  - Route: 7 endpoints (list/create/get/patch/delete + traces list/add/remove)
    with happy path, 404, 409 conflict on duplicate name, 422 on invalid
    inputs, 204 on delete, tenant isolation.
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
from app.db.models import Call, GoldenSet, GoldenTrace
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.goldens import (
    ACTIVE_GOLDEN_REQUIRES_EXPECTED_BEHAVIOR,
    GOLDEN_TRACE_STATUS_ACTIVE,
    GOLDEN_TRACE_STATUS_DRAFT,
    GoldenSetNameConflict,
    VALID_GOLDEN_TRACE_STATUSES,
    add_trace,
    count_traces,
    create_golden_set,
    delete_golden_set,
    get_golden_set,
    list_golden_sets,
    list_traces,
    remove_trace,
    update_golden_set,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_goldens_svc.db"
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
    db_path = tmp_path / "test_goldens_route.db"
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


# Module 6 added a router-level plan-gate on /v1/goldens/* that 402s when
# `pilot.autopilot_enabled` is false. Bypass for this file (the gate is
# tested separately in tests/test_plan_gates.py).
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


def _create_golden_via_factory(session_factory, *, project_id: str, name: str) -> GoldenSet:
    session = session_factory()
    try:
        gs = create_golden_set(session, project_id=project_id, name=name)
        # detach so the test can use it freely
        return session.get(GoldenSet, gs.id)  # type: ignore[return-value]
    finally:
        session.close()


# ── service: golden set CRUD ────────────────────────────────────────────────


class TestCreateGoldenSet:
    def test_create_returns_row_with_id(self, db_session) -> None:
        gs = create_golden_set(
            db_session,
            project_id="proj-1",
            name="canonical",
            description="desc",
            judge_config_json='{"k":"v"}',
        )
        assert gs.id
        assert gs.project_id == "proj-1"
        assert gs.name == "canonical"
        assert gs.description == "desc"
        assert gs.judge_config_json == '{"k":"v"}'
        assert gs.is_flaky is False
        assert gs.blocks_ci is False

    def test_empty_name_rejected(self, db_session) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            create_golden_set(db_session, project_id="proj-1", name="   ")

    def test_duplicate_name_raises_conflict(self, db_session) -> None:
        create_golden_set(db_session, project_id="proj-1", name="dup")
        with pytest.raises(GoldenSetNameConflict):
            create_golden_set(db_session, project_id="proj-1", name="dup")

    def test_same_name_different_tenant_allowed(self, db_session) -> None:
        a = create_golden_set(db_session, project_id="proj-A", name="shared")
        b = create_golden_set(db_session, project_id="proj-B", name="shared")
        assert a.id != b.id


class TestGetAndList:
    def test_get_returns_none_for_missing(self, db_session) -> None:
        assert get_golden_set(
            db_session, project_id="proj-1", golden_set_id="missing"
        ) is None

    def test_get_cross_tenant_returns_none(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-A", name="x")
        assert get_golden_set(
            db_session, project_id="proj-B", golden_set_id=gs.id
        ) is None

    def test_list_returns_newest_first(self, db_session) -> None:
        rows = []
        for n in range(3):
            rows.append(create_golden_set(
                db_session, project_id="proj-list", name=f"set-{n}"
            ))
        listed = list_golden_sets(db_session, project_id="proj-list", limit=10)
        assert len(listed) == 3
        # newest-first by created_at desc; since they share microsecond ties
        # the secondary ordering on id keeps the result stable
        ids_listed = [g.id for g in listed]
        ids_in_creation_order = [g.id for g in rows]
        assert set(ids_listed) == set(ids_in_creation_order)

    def test_list_tenant_isolation(self, db_session) -> None:
        create_golden_set(db_session, project_id="proj-A", name="a")
        create_golden_set(db_session, project_id="proj-B", name="b")
        listed = list_golden_sets(db_session, project_id="proj-A", limit=10)
        assert len(listed) == 1
        assert listed[0].project_id == "proj-A"


class TestUpdateGoldenSet:
    def test_update_partial_fields(self, db_session) -> None:
        gs = create_golden_set(
            db_session, project_id="proj-1", name="orig", description="d"
        )
        updated = update_golden_set(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            name="renamed",
        )
        assert updated is not None
        assert updated.name == "renamed"
        assert updated.description == "d"  # unchanged

    def test_update_flaky_and_blocking_flags(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="flags")
        updated = update_golden_set(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            is_flaky=True,
            blocks_ci=True,
        )
        assert updated is not None
        assert updated.is_flaky is True
        assert updated.blocks_ci is True

    def test_clear_optional_fields(self, db_session) -> None:
        gs = create_golden_set(
            db_session,
            project_id="proj-1",
            name="x",
            description="d",
            judge_config_json="{}",
        )
        updated = update_golden_set(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            clear_description=True,
            clear_judge_config=True,
        )
        assert updated is not None
        assert updated.description is None
        assert updated.judge_config_json is None

    def test_update_missing_returns_none(self, db_session) -> None:
        assert update_golden_set(
            db_session,
            project_id="proj-1",
            golden_set_id="missing",
            name="x",
        ) is None

    def test_update_to_duplicate_name_raises_conflict(self, db_session) -> None:
        create_golden_set(db_session, project_id="proj-1", name="taken")
        gs = create_golden_set(db_session, project_id="proj-1", name="renamable")
        with pytest.raises(GoldenSetNameConflict):
            update_golden_set(
                db_session,
                project_id="proj-1",
                golden_set_id=gs.id,
                name="taken",
            )


class TestDeleteGoldenSet:
    def test_delete_returns_true(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        assert delete_golden_set(
            db_session, project_id="proj-1", golden_set_id=gs.id
        ) is True
        assert get_golden_set(
            db_session, project_id="proj-1", golden_set_id=gs.id
        ) is None

    def test_delete_missing_returns_false(self, db_session) -> None:
        assert delete_golden_set(
            db_session, project_id="proj-1", golden_set_id="missing"
        ) is False

    def test_delete_cross_tenant_returns_false(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-A", name="x")
        assert delete_golden_set(
            db_session, project_id="proj-B", golden_set_id=gs.id
        ) is False
        # Original still present
        assert get_golden_set(
            db_session, project_id="proj-A", golden_set_id=gs.id
        ) is not None

    def test_delete_cascades_to_traces(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        add_trace(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            expected_output_text="hello",
            weight=1.0,
        )
        add_trace(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            expected_output_text="world",
            weight=1.0,
        )
        assert count_traces(
            db_session, project_id="proj-1", golden_set_id=gs.id
        ) == 2

        delete_golden_set(db_session, project_id="proj-1", golden_set_id=gs.id)

        remaining = db_session.execute(
            select(GoldenTrace).where(GoldenTrace.golden_set_id == gs.id)
        ).scalars().all()
        assert remaining == []


# ── service: golden trace CRUD ───────────────────────────────────────────────


class TestAddTrace:
    def test_add_trace_returns_row(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        trace = add_trace(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            expected_output_text="hello",
            expected_tokens=42,
            expected_cost_usd=0.001,
            expected_latency_ms=120,
            weight=2.5,
        )
        assert trace is not None
        assert trace.project_id == "proj-1"
        assert trace.golden_set_id == gs.id
        assert trace.status == GOLDEN_TRACE_STATUS_ACTIVE
        assert trace.expected_output_text == "hello"
        assert trace.expected_tokens == 42
        assert float(trace.weight) == 2.5

    def test_add_trace_to_missing_set_returns_none(self, db_session) -> None:
        assert add_trace(
            db_session,
            project_id="proj-1",
            golden_set_id="missing",
            expected_output_text="hello",
        ) is None

    def test_add_trace_to_cross_tenant_set_returns_none(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-A", name="x")
        assert add_trace(
            db_session,
            project_id="proj-B",
            golden_set_id=gs.id,
            expected_output_text="hello",
        ) is None

    def test_add_trace_with_zero_weight_rejected(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        with pytest.raises(ValueError, match="weight"):
            add_trace(
                db_session,
                project_id="proj-1",
                golden_set_id=gs.id,
                weight=0,
            )

    def test_add_trace_with_unknown_call_id_rejected(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        with pytest.raises(ValueError, match="call_id"):
            add_trace(
                db_session,
                project_id="proj-1",
                golden_set_id=gs.id,
                call_id="not-a-real-call",
            )

    def test_add_trace_with_valid_call_id(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        call = Call(
            id="call-1",
            project_id="proj-1",
            event_id="evt-1",
            status="failed",
            error_code="OUTPUT_MISMATCH",
            payload_json=json.dumps({"response": "bad original output"}),
        )
        db_session.add(call)
        db_session.commit()
        trace = add_trace(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            call_id="call-1",
        )
        assert trace is not None
        assert trace.call_id == "call-1"
        assert trace.status == GOLDEN_TRACE_STATUS_DRAFT
        assert trace.expected_output_text is None
        assert trace.source_output_text == "bad original output"
        evidence = json.loads(trace.source_evidence_json)
        assert evidence["call_id"] == "call-1"
        assert evidence["status"] == "failed"

    def test_add_trace_active_without_expected_behavior_rejected(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        with pytest.raises(
            ValueError, match=ACTIVE_GOLDEN_REQUIRES_EXPECTED_BEHAVIOR
        ):
            add_trace(
                db_session,
                project_id="proj-1",
                golden_set_id=gs.id,
                status=GOLDEN_TRACE_STATUS_ACTIVE,
            )

    def test_add_trace_with_source_evidence_defaults_to_draft(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        trace = add_trace(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            source_output_text="observed but not approved",
            source_evidence_json=json.dumps({"source": "test"}),
        )
        assert trace is not None
        assert trace.status == GOLDEN_TRACE_STATUS_DRAFT
        assert trace.expected_output_text is None
        assert trace.source_output_text == "observed but not approved"

    def test_add_trace_with_cross_tenant_call_id_rejected(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-A", name="x")
        # Call belongs to proj-B
        call = Call(
            id="call-x",
            project_id="proj-B",
            event_id="evt-x",
            status="ok",
        )
        db_session.add(call)
        db_session.commit()
        with pytest.raises(ValueError, match="not found for project"):
            add_trace(
                db_session,
                project_id="proj-A",
                golden_set_id=gs.id,
                call_id="call-x",
            )


class TestRemoveTrace:
    def test_remove_returns_true(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        trace = add_trace(
            db_session, project_id="proj-1", golden_set_id=gs.id, expected_output_text="hi"
        )
        assert trace is not None
        assert remove_trace(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            trace_id=trace.id,
        ) is True
        assert count_traces(
            db_session, project_id="proj-1", golden_set_id=gs.id
        ) == 0

    def test_remove_missing_returns_false(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        assert remove_trace(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
            trace_id="missing",
        ) is False

    def test_remove_cross_tenant_returns_false(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-A", name="x")
        trace = add_trace(
            db_session, project_id="proj-A", golden_set_id=gs.id, expected_output_text="hi"
        )
        assert trace is not None
        assert remove_trace(
            db_session,
            project_id="proj-B",
            golden_set_id=gs.id,
            trace_id=trace.id,
        ) is False


class TestListTraces:
    def test_list_returns_none_for_missing_set(self, db_session) -> None:
        assert list_traces(
            db_session, project_id="proj-1", golden_set_id="missing"
        ) is None

    def test_list_returns_traces_in_creation_order(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="x")
        for n in range(3):
            add_trace(
                db_session,
                project_id="proj-1",
                golden_set_id=gs.id,
                expected_output_text=f"out-{n}",
            )
        traces = list_traces(
            db_session, project_id="proj-1", golden_set_id=gs.id
        )
        assert traces is not None
        assert len(traces) == 3
        outputs = [t.expected_output_text for t in traces]
        assert outputs == ["out-0", "out-1", "out-2"]


# ── routes ───────────────────────────────────────────────────────────────────


class TestListRoute:
    def test_empty_list(self, client: TestClient) -> None:
        response = client.get(
            "/v1/goldens", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["next_cursor"] is None
        assert body["total_in_page"] == 0

    def test_list_includes_trace_count(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-1", name="x")
        # add 2 traces
        with factory() as session:
            for n in range(2):
                add_trace(
                    session,
                    project_id="proj-1",
                    golden_set_id=gs.id,
                    expected_output_text=f"out-{n}",
                )

        response = client.get(
            "/v1/goldens", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["trace_count"] == 2

    def test_list_pagination(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        # Create 5 sets in sequence with explicit time spacing so the cursor
        # ordering is deterministic.
        with factory() as session:
            now = datetime.now(timezone.utc)
            for n in range(5):
                gs = create_golden_set(
                    session, project_id="proj-page", name=f"set-{n}"
                )
                # back-date for deterministic ordering
                gs.created_at = now - timedelta(seconds=10 * (5 - n))
                session.add(gs)
            session.commit()

        first = client.get(
            "/v1/goldens?limit=2",
            headers={PROJECT_HEADER: "proj-page"},
        ).json()
        assert len(first["items"]) == 2
        assert first["next_cursor"] is not None

        second = client.get(
            f"/v1/goldens?limit=2&cursor={first['next_cursor']}",
            headers={PROJECT_HEADER: "proj-page"},
        ).json()
        assert len(second["items"]) == 2
        assert second["next_cursor"] is not None

        third = client.get(
            f"/v1/goldens?limit=2&cursor={second['next_cursor']}",
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

    def test_list_invalid_cursor(self, client: TestClient) -> None:
        response = client.get(
            "/v1/goldens?cursor=not-base64",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_list_tenant_isolation(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        _create_golden_via_factory(factory, project_id="proj-A", name="a")
        _create_golden_via_factory(factory, project_id="proj-B", name="b")
        response = client.get(
            "/v1/goldens", headers={PROJECT_HEADER: "proj-A"}
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert {i["project_id"] for i in items} == {"proj-A"}


class TestCreateRoute:
    def test_create_201(self, client: TestClient) -> None:
        response = client.post(
            "/v1/goldens",
            headers={PROJECT_HEADER: "proj-1"},
            json={"name": "canonical", "description": "d"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "canonical"
        assert body["description"] == "d"
        assert body["trace_count"] == 0
        assert body["project_id"] == "proj-1"
        assert body["is_flaky"] is False
        assert body["blocks_ci"] is False

    def test_duplicate_name_409(self, client: TestClient) -> None:
        client.post(
            "/v1/goldens",
            headers={PROJECT_HEADER: "proj-1"},
            json={"name": "dup"},
        )
        response = client.post(
            "/v1/goldens",
            headers={PROJECT_HEADER: "proj-1"},
            json={"name": "dup"},
        )
        assert response.status_code == 409

    def test_empty_name_422(self, client: TestClient) -> None:
        response = client.post(
            "/v1/goldens",
            headers={PROJECT_HEADER: "proj-1"},
            json={"name": ""},
        )
        assert response.status_code == 422

    def test_missing_tenant_header_401(self, client: TestClient) -> None:
        response = client.post("/v1/goldens", json={"name": "x"})
        assert response.status_code == 401


class TestGetRoute:
    def test_404_for_missing(self, client: TestClient) -> None:
        response = client.get(
            "/v1/goldens/missing-id",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 404

    def test_returns_seeded_row(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-1", name="x")
        response = client.get(
            f"/v1/goldens/{gs.id}",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == gs.id

    def test_cross_tenant_404(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-A", name="x")
        response = client.get(
            f"/v1/goldens/{gs.id}",
            headers={PROJECT_HEADER: "proj-B"},
        )
        assert response.status_code == 404


class TestPatchRoute:
    def test_rename(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-1", name="orig")
        response = client.patch(
            f"/v1/goldens/{gs.id}",
            headers={PROJECT_HEADER: "proj-1"},
            json={"name": "renamed"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "renamed"

    def test_clear_description(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            gs = create_golden_set(
                session, project_id="proj-1", name="x", description="d"
            )

        response = client.patch(
            f"/v1/goldens/{gs.id}",
            headers={PROJECT_HEADER: "proj-1"},
            json={"clear_description": True},
        )
        assert response.status_code == 200
        assert response.json()["description"] is None

    def test_patch_flaky_and_blocking_flags_persist(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-1", name="flags")
        response = client.patch(
            f"/v1/goldens/{gs.id}",
            headers={PROJECT_HEADER: "proj-1"},
            json={"is_flaky": True, "blocks_ci": True},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["is_flaky"] is True
        assert body["blocks_ci"] is True

        detail = client.get(
            f"/v1/goldens/{gs.id}",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert detail.status_code == 200
        assert detail.json()["is_flaky"] is True
        assert detail.json()["blocks_ci"] is True

    def test_rename_conflict_409(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        _create_golden_via_factory(factory, project_id="proj-1", name="taken")
        gs = _create_golden_via_factory(factory, project_id="proj-1", name="renamable")
        response = client.patch(
            f"/v1/goldens/{gs.id}",
            headers={PROJECT_HEADER: "proj-1"},
            json={"name": "taken"},
        )
        assert response.status_code == 409

    def test_patch_missing_404(self, client: TestClient) -> None:
        response = client.patch(
            "/v1/goldens/missing-id",
            headers={PROJECT_HEADER: "proj-1"},
            json={"name": "x"},
        )
        assert response.status_code == 404


class TestDeleteRoute:
    def test_delete_204(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-1", name="x")
        response = client.delete(
            f"/v1/goldens/{gs.id}", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 204
        # second delete returns 404
        again = client.delete(
            f"/v1/goldens/{gs.id}", headers={PROJECT_HEADER: "proj-1"}
        )
        assert again.status_code == 404

    def test_delete_cross_tenant_404(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-A", name="x")
        response = client.delete(
            f"/v1/goldens/{gs.id}", headers={PROJECT_HEADER: "proj-B"}
        )
        assert response.status_code == 404


class TestTraceRoutes:
    def test_list_traces_404_for_missing_set(self, client: TestClient) -> None:
        response = client.get(
            "/v1/goldens/missing/traces",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 404

    def test_add_trace_201(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-1", name="x")
        response = client.post(
            f"/v1/goldens/{gs.id}/traces",
            headers={PROJECT_HEADER: "proj-1"},
            json={"expected_output_text": "hi", "weight": 2.0},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == GOLDEN_TRACE_STATUS_ACTIVE
        assert body["expected_output_text"] == "hi"
        assert body["source_output_text"] is None
        assert body["source_evidence_json"] is None
        assert body["weight"] == 2.0
        assert body["golden_set_id"] == gs.id

    def test_add_trace_active_without_expected_behavior_422(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-1", name="x")
        response = client.post(
            f"/v1/goldens/{gs.id}/traces",
            headers={PROJECT_HEADER: "proj-1"},
            json={"status": "active"},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == ACTIVE_GOLDEN_REQUIRES_EXPECTED_BEHAVIOR

    def test_add_trace_draft_with_source_evidence(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-1", name="x")
        response = client.post(
            f"/v1/goldens/{gs.id}/traces",
            headers={PROJECT_HEADER: "proj-1"},
            json={
                "source_output_text": "observed failed output",
                "source_evidence_json": json.dumps({"source": "route-test"}),
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == GOLDEN_TRACE_STATUS_DRAFT
        assert body["expected_output_text"] is None
        assert body["source_output_text"] == "observed failed output"
        assert json.loads(body["source_evidence_json"])["source"] == "route-test"

    def test_add_trace_404_for_missing_set(self, client: TestClient) -> None:
        response = client.post(
            "/v1/goldens/missing/traces",
            headers={PROJECT_HEADER: "proj-1"},
            json={"expected_output_text": "hi"},
        )
        assert response.status_code == 404

    def test_add_trace_zero_weight_422(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-1", name="x")
        response = client.post(
            f"/v1/goldens/{gs.id}/traces",
            headers={PROJECT_HEADER: "proj-1"},
            json={"weight": 0},
        )
        assert response.status_code == 422

    def test_list_then_remove_traces(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-1", name="x")
        # Add 3 traces via API
        for n in range(3):
            response = client.post(
                f"/v1/goldens/{gs.id}/traces",
                headers={PROJECT_HEADER: "proj-1"},
                json={"expected_output_text": f"out-{n}"},
            )
            assert response.status_code == 201

        listed = client.get(
            f"/v1/goldens/{gs.id}/traces",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        assert listed["total_in_page"] == 3

        first_trace_id = listed["items"][0]["id"]
        delete = client.delete(
            f"/v1/goldens/{gs.id}/traces/{first_trace_id}",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert delete.status_code == 204

        after = client.get(
            f"/v1/goldens/{gs.id}/traces",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        assert after["total_in_page"] == 2

    def test_remove_trace_404(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-1", name="x")
        response = client.delete(
            f"/v1/goldens/{gs.id}/traces/missing-trace-id",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 404

    def test_remove_trace_cross_tenant_404(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        gs = _create_golden_via_factory(factory, project_id="proj-A", name="x")
        with factory() as session:
            trace = add_trace(
                session,
                project_id="proj-A",
                golden_set_id=gs.id,
                expected_output_text="hi",
            )
        response = client.delete(
            f"/v1/goldens/{gs.id}/traces/{trace.id}",
            headers={PROJECT_HEADER: "proj-B"},
        )
        assert response.status_code == 404


class TestInvariants:
    def test_valid_golden_trace_statuses_match_db_check(self) -> None:
        assert VALID_GOLDEN_TRACE_STATUSES == frozenset({"draft", "active"})

    def test_legacy_rows_without_expected_behavior_are_draft(self, db_session) -> None:
        gs = create_golden_set(db_session, project_id="proj-1", name="legacy")
        trace = add_trace(
            db_session,
            project_id="proj-1",
            golden_set_id=gs.id,
        )
        assert trace is not None
        assert trace.status == GOLDEN_TRACE_STATUS_DRAFT
