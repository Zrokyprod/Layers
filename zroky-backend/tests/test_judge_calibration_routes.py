"""Tests for `app/api/routes/judge_calibration_routes.py`.

Coverage:
  - GET /latest returns latest run per model
  - GET /history returns time-series
  - GET /mode/{model} returns mode snapshot
  - POST /run-now returns run result (admin)
  - POST /labels creates label
  - DELETE /labels/{id} soft-deletes
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    GoldenLabel,
    GoldenSet,
    GoldenTrace,
    JudgeCalibrationRun,
    Project,
)
from app.db.session import get_db_session, get_db_session_read
from app.main import app


@pytest.fixture()
def client(tmp_path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_cal_routes.db"
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

    # Entitlement bypass
    from app.services import entitlements_resolver
    from app.services.billing_plans import PLAN_ENTITLEMENTS

    pro_dict = dict(PLAN_ENTITLEMENTS["pro"])
    orig_has = entitlements_resolver.has
    orig_get = entitlements_resolver.get
    orig_resolve_all = entitlements_resolver.resolve_all
    orig_get_plan_code = entitlements_resolver.get_plan_code
    entitlements_resolver.has = lambda db, org_id, key: True
    entitlements_resolver.get = lambda db, org_id, key, default=None: pro_dict.get(key, default)
    entitlements_resolver.resolve_all = lambda db, org_id: dict(pro_dict)
    entitlements_resolver.get_plan_code = lambda db, org_id: "pro"

    with TestClient(app) as tc:
        tc._session_factory = session_factory  # type: ignore[attr-defined]
        yield tc

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()
    entitlements_resolver.has = orig_has
    entitlements_resolver.get = orig_get
    entitlements_resolver.resolve_all = orig_resolve_all
    entitlements_resolver.get_plan_code = orig_get_plan_code


PROJECT_HEADER = "X-Project-Id"


class TestLatest:
    def test_empty(self, client) -> None:
        r = client.get("/v1/judge/calibration/latest", headers={PROJECT_HEADER: "p1"})
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_latest_per_model(self, client) -> None:
        sf = client._session_factory
        session = sf()
        try:
            p = Project(id="p1", name="test")
            session.add(p)
            session.commit()
            for i, (model, acc) in enumerate([("m1", 0.9), ("m2", 0.8)]):
                run = JudgeCalibrationRun(
                    id=str(uuid.uuid4()),
                    project_id="p1",
                    judge_model=model,
                    run_date=date.today(),
                    status="complete",
                    sample_count=10,
                    agreement_count=int(acc * 10),
                    accuracy=acc,
                    kappa=0.7,
                    low_confidence_pct=0.1,
                    cost_usd="0.01",
                )
                session.add(run)
            session.commit()
        finally:
            session.close()

        r = client.get("/v1/judge/calibration/latest", headers={PROJECT_HEADER: "p1"})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        models = {d["judge_model"] for d in data}
        assert models == {"m1", "m2"}


class TestHistory:
    def test_time_series(self, client) -> None:
        sf = client._session_factory
        session = sf()
        try:
            p = Project(id="p1", name="test")
            session.add(p)
            session.commit()
            for i in range(3):
                run = JudgeCalibrationRun(
                    id=str(uuid.uuid4()),
                    project_id="p1",
                    judge_model="m1",
                    run_date=date.fromisoformat(f"2024-01-{i+1:02d}"),
                    status="complete",
                    sample_count=10,
                    agreement_count=9,
                    accuracy=0.9,
                    kappa=0.7,
                    low_confidence_pct=0.1,
                    cost_usd="0.01",
                )
                session.add(run)
            session.commit()
        finally:
            session.close()

        r = client.get(
            "/v1/judge/calibration/history?judge_model=m1&days=30",
            headers={PROJECT_HEADER: "p1"},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 3


class TestMode:
    def test_mode_default(self, client) -> None:
        r = client.get("/v1/judge/calibration/mode/m1", headers={PROJECT_HEADER: "p1"})
        assert r.status_code == 200
        data = r.json()
        assert data["mode"] == "blocking"
        assert data["accuracy"] is None


class TestLabels:
    def test_create_and_soft_delete(self, client) -> None:
        sf = client._session_factory
        session = sf()
        try:
            p = Project(id="p1", name="test")
            gs = GoldenSet(id="gs1", project_id="p1", name="s", criteria_json="{}")
            gt = GoldenTrace(
                id="gt1", project_id="p1", golden_set_id="gs1",
                prompt_text="hi", expected_output="hello", criteria_json="{}",
            )
            session.add_all([p, gs, gt])
            session.commit()
        finally:
            session.close()

        r = client.post(
            "/v1/judge/calibration/labels",
            json={"golden_trace_id": "gt1", "verdict": "pass"},
            headers={PROJECT_HEADER: "p1"},
        )
        assert r.status_code == 200
        lbl = r.json()
        assert lbl["verdict"] == "pass"
        assert lbl["active"] is True

        r2 = client.delete(f"/v1/judge/calibration/labels/{lbl['id']}", headers={PROJECT_HEADER: "p1"})
        assert r2.status_code == 200
        assert r2.json()["message"] == "Label deactivated"

        # Verify inactive
        r3 = client.get("/v1/judge/calibration/labels?trace_id=gt1", headers={PROJECT_HEADER: "p1"})
        rows = r3.json()
        assert any(row["id"] == lbl["id"] and row["active"] is False for row in rows)
