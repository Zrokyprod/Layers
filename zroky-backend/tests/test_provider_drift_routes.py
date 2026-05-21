"""Tests for `app.api.routes.provider_drift`.

Public, anonymous endpoints:
  - GET /v1/drift/models
  - GET /v1/drift/status
  - GET /v1/drift/history/{model_id}
  - GET /v1/drift/rss
  - GET /v1/drift/atom
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    ProviderDriftAlert,
    ProviderDriftModel,
    ProviderDriftProbe,
    ProviderDriftRun,
)
from app.db.session import SessionLocal
from app.main import app


@pytest.fixture()
def db(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_provider_drift_routes.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    # Monkeypatch SessionLocal so routes use our test DB
    original = SessionLocal
    import app.api.routes.provider_drift as _pd_module
    import app.services.provider_drift.prompt_suite as _ps_module
    import app.services.provider_drift.registry as _reg_module
    import app.services.provider_drift.runner as _run_module

    _pd_module.SessionLocal = factory  # type: ignore[attr-defined]

    sess = factory()
    yield sess
    sess.close()

    _pd_module.SessionLocal = original  # type: ignore[attr-defined]
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


@pytest.fixture()
def client(db):
    with TestClient(app) as tc:
        yield tc


def _make_model(db, model_id="openai-gpt-4o") -> ProviderDriftModel:
    m = ProviderDriftModel(
        id=model_id,
        provider="openai",
        model_id="gpt-4o",
        display_name="GPT-4o",
        family="gpt",
        active=True,
    )
    db.add(m)
    db.commit()
    return m


def _make_run(db, model_id="openai-gpt-4o", run_date=None) -> ProviderDriftRun:
    r = ProviderDriftRun(
        id=f"run-{run_date or date.today()}",
        model_id=model_id,
        run_date=run_date or date.today(),
        status="complete",
        cost_usd=0.0,
    )
    db.add(r)
    db.commit()
    return r


def _make_probe(db, run_id, category="math", verdict=True, embedding=0.95, prompt_id="p1") -> ProviderDriftProbe:
    p = ProviderDriftProbe(
        id=f"probe-{run_id}-{category}-{prompt_id}",
        run_id=run_id,
        model_id="openai-gpt-4o",
        run_date=date.today(),
        prompt_id=prompt_id,
        category=category,
        output_text="4",
        output_embedding=str([embedding]),
        embedding_model="text-embedding-3-small",
        judge_pass=verdict,
        judge_score=1.0 if verdict else 0.0,
        latency_ms=100,
        cost_usd=0.0,
        outcome="ok",
    )
    db.add(p)
    db.commit()
    return p


def _make_alert(db, model_id="openai-gpt-4o", category="math", severity="warn", headline=None) -> ProviderDriftAlert:
    today = date.today()
    a = ProviderDriftAlert(
        id=f"alert-{model_id}-{category}",
        model_id=model_id,
        category=category,
        current_date=today,
        baseline_start=today,
        baseline_end=today,
        pass_rate_current=0.5,
        pass_rate_baseline=0.8,
        judge_z=2.5,
        embedding_z=1.0,
        delta_pp=0.3,
        severity=severity,
        headline=headline or f"{severity.title()} drift on {model_id}/{category}",
        evidence_json='{"z_judge": 2.5}',
    )
    db.add(a)
    db.commit()
    return a


# ── /models ───────────────────────────────────────────────────────────────────


def test_list_models_empty(client):
    resp = client.get("/v1/drift/models")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_models_returns_rows(client, db):
    _make_model(db)
    resp = client.get("/v1/drift/models")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "openai-gpt-4o"
    assert data[0]["provider"] == "openai"


# ── /status ───────────────────────────────────────────────────────────────────


def test_status_disabled_returns_empty(client, monkeypatch):
    monkeypatch.setenv("PROVIDER_DRIFT_WATCH_ENABLED", "false")
    get_settings.cache_clear()
    resp = client.get("/v1/drift/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_alerts"] == 0
    assert data["models"] == []


def test_status_with_data(client, db):
    _make_model(db)
    _make_alert(db)
    resp = client.get("/v1/drift/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_alerts"] == 1
    assert data["warn_count"] == 1
    assert data["critical_count"] == 0
    assert len(data["models"]) == 1
    assert data["alerts"][0]["severity"] == "warn"


# ── /history/{model_id} ────────────────────────────────────────────────────────


def test_history_missing_model(client):
    resp = client.get("/v1/drift/history/nonexistent")
    assert resp.status_code == 404


def test_history_returns_points(client, db):
    _make_model(db)
    run = _make_run(db)
    _make_probe(db, run.id, category="math", verdict=True, embedding=0.92, prompt_id="p1")
    _make_probe(db, run.id, category="math", verdict=False, embedding=0.70, prompt_id="p2")
    resp = client.get("/v1/drift/history/openai-gpt-4o")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["category"] == "math"
    assert data[0]["points"][0]["probe_count"] == 2
    assert data[0]["points"][0]["ok_count"] == 1
    assert data[0]["points"][0]["judge_pass_rate"] == 0.5
    # judge_score mean = (1.0 + 0.0) / 2 = 0.5
    assert data[0]["points"][0]["embedding_mean_cosine"] == pytest.approx(0.5, 0.01)


# ── /rss ──────────────────────────────────────────────────────────────────────


def test_rss_empty(client):
    resp = client.get("/v1/drift/rss")
    assert resp.status_code == 200
    assert "application/rss+xml" in resp.headers["content-type"]
    assert "<rss version=\"2.0\">" in resp.text


def test_rss_with_alert(client, db):
    _make_alert(db, headline="Drift detected")
    resp = client.get("/v1/drift/rss")
    assert resp.status_code == 200
    assert "Drift detected" in resp.text
    assert "<guid>" in resp.text


# ── /atom ───────────────────────────────────────────────────────────────────────


def test_atom_empty(client):
    resp = client.get("/v1/drift/atom")
    assert resp.status_code == 200
    assert "application/atom+xml" in resp.headers["content-type"]
    assert "<feed xmlns=\"http://www.w3.org/2005/Atom\">" in resp.text


def test_atom_with_alert(client, db):
    _make_alert(db, headline="Drift detected")
    resp = client.get("/v1/drift/atom")
    assert resp.status_code == 200
    assert "Drift detected" in resp.text
    assert "<entry>" in resp.text
