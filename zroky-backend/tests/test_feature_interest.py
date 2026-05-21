"""Tests for feature-interest voting (Module 9 smoke-test alternative):

  Customer surface:
    POST  /v1/feature-interest
    GET   /v1/feature-interest/me

  Admin surface (gated by require_provisioning_access):
    GET   /v1/admin/feature-interest
    GET   /v1/admin/feature-interest/{feature_key}
    GET   /v1/admin/feature-interest/{feature_key}/export.csv

  Service-level coverage:
    upsert_vote, get_user_vote, summarize_feature, summarize_all,
    list_recent_votes, mask_email, registry guards.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import FeatureInterestVote, Project, User
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.feature_interest_registry import COMING_SOON_FEATURES
from app.services.feature_interest_service import (
    InvalidVoteError,
    UnknownFeatureError,
    get_user_vote,
    list_recent_votes,
    mask_email,
    summarize_all,
    summarize_feature,
    upsert_vote,
)


FEATURE_KEY = "pilot.tier1_autonomy"


# ── service-level fixtures (no FastAPI) ─────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_fi_svc.db"
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


def _make_project(db, *, project_id: str = "proj_test_fi", name: str = "Acme") -> Project:
    row = Project(id=project_id, name=name, owner_ref="owner-1")
    db.add(row)
    db.commit()
    return row


def _make_user(
    db, *, subject: str, email: str = "dev@acme.com",
) -> User:
    row = User(subject=subject, email=email)
    db.add(row)
    db.commit()
    return row


# ── service: upsert_vote ────────────────────────────────────────────────────


def test_upsert_creates_new_vote(db_session) -> None:
    _make_project(db_session)
    row = upsert_vote(
        db_session,
        subject="user-alpha",
        project_id="proj_test_fi",
        feature_key=FEATURE_KEY,
        vote="interested",
        use_case="auto-revert model when accuracy drops",
    )
    assert row.id
    assert row.vote == "interested"
    assert row.use_case == "auto-revert model when accuracy drops"
    assert row.project_id == "proj_test_fi"


def test_upsert_changes_existing_vote(db_session) -> None:
    _make_project(db_session)
    first = upsert_vote(
        db_session,
        subject="user-alpha",
        project_id="proj_test_fi",
        feature_key=FEATURE_KEY,
        vote="interested",
    )
    second = upsert_vote(
        db_session,
        subject="user-alpha",
        project_id="proj_test_fi",
        feature_key=FEATURE_KEY,
        vote="not_interested",
        use_case="changed my mind",
    )
    assert first.id == second.id
    assert second.vote == "not_interested"
    assert second.use_case == "changed my mind"

    # Only one row exists
    count = db_session.execute(select(FeatureInterestVote)).all()
    assert len(count) == 1


def test_upsert_rejects_unknown_feature(db_session) -> None:
    _make_project(db_session)
    with pytest.raises(UnknownFeatureError):
        upsert_vote(
            db_session,
            subject="user-alpha",
            project_id="proj_test_fi",
            feature_key="not.a.real.feature",
            vote="interested",
        )


def test_upsert_rejects_invalid_vote_value(db_session) -> None:
    _make_project(db_session)
    with pytest.raises(InvalidVoteError):
        upsert_vote(
            db_session,
            subject="user-alpha",
            project_id="proj_test_fi",
            feature_key=FEATURE_KEY,
            vote="maybe",
        )


def test_upsert_normalizes_empty_use_case_to_none(db_session) -> None:
    _make_project(db_session)
    row = upsert_vote(
        db_session,
        subject="user-alpha",
        project_id="proj_test_fi",
        feature_key=FEATURE_KEY,
        vote="interested",
        use_case="   ",
    )
    assert row.use_case is None


# ── service: get_user_vote ──────────────────────────────────────────────────


def test_get_user_vote_returns_none_when_absent(db_session) -> None:
    _make_project(db_session)
    assert get_user_vote(
        db_session, subject="user-alpha", feature_key=FEATURE_KEY
    ) is None


def test_get_user_vote_returns_existing(db_session) -> None:
    _make_project(db_session)
    upsert_vote(
        db_session,
        subject="user-alpha",
        project_id="proj_test_fi",
        feature_key=FEATURE_KEY,
        vote="interested",
    )
    row = get_user_vote(
        db_session, subject="user-alpha", feature_key=FEATURE_KEY
    )
    assert row is not None
    assert row.vote == "interested"


# ── service: summarize ──────────────────────────────────────────────────────


def test_summarize_with_zero_votes(db_session) -> None:
    summary = summarize_feature(db_session, feature_key=FEATURE_KEY)
    assert summary["total"] == 0
    assert summary["interested"] == 0
    assert summary["status"] == "no_votes"
    assert summary["interested_pct"] == 0.0


def test_summarize_with_mixed_votes(db_session) -> None:
    _make_project(db_session)
    for i in range(7):
        upsert_vote(
            db_session,
            subject=f"user-{i}",
            project_id="proj_test_fi",
            feature_key=FEATURE_KEY,
            vote="interested",
        )
    for i in range(3):
        upsert_vote(
            db_session,
            subject=f"nuser-{i}",
            project_id="proj_test_fi",
            feature_key=FEATURE_KEY,
            vote="not_interested",
        )

    summary = summarize_feature(db_session, feature_key=FEATURE_KEY)
    assert summary["total"] == 10
    assert summary["interested"] == 7
    assert summary["not_interested"] == 3
    assert summary["interested_pct"] == 0.7
    assert summary["status"] == "above_threshold"  # 70% > 30%


def test_summarize_below_threshold(db_session) -> None:
    _make_project(db_session)
    upsert_vote(
        db_session,
        subject="u1",
        project_id="proj_test_fi",
        feature_key=FEATURE_KEY,
        vote="interested",
    )
    for i in range(5):
        upsert_vote(
            db_session,
            subject=f"nu{i}",
            project_id="proj_test_fi",
            feature_key=FEATURE_KEY,
            vote="not_interested",
        )
    summary = summarize_feature(db_session, feature_key=FEATURE_KEY)
    assert summary["interested_pct"] == pytest.approx(1 / 6, abs=0.001)
    assert summary["status"] == "below_threshold"


def test_summarize_all_returns_one_per_registered_feature(db_session) -> None:
    summaries = summarize_all(db_session)
    keys = [s["feature_key"] for s in summaries]
    assert set(keys) == set(COMING_SOON_FEATURES.keys())


# ── service: list_recent_votes ──────────────────────────────────────────────


def test_list_recent_includes_email_masked_and_project_name(db_session) -> None:
    _make_project(db_session, project_id="proj_test_fi", name="Acme")
    _make_user(db_session, subject="user-alpha", email="dev@acme.com")
    upsert_vote(
        db_session,
        subject="user-alpha",
        project_id="proj_test_fi",
        feature_key=FEATURE_KEY,
        vote="interested",
        use_case="rollback when accuracy drops",
    )
    rows = list_recent_votes(db_session, feature_key=FEATURE_KEY)
    assert len(rows) == 1
    row = rows[0]
    assert row["user_email_masked"] == "d***@acme.com"
    assert row["project_name"] == "Acme"
    assert row["use_case"] == "rollback when accuracy drops"


def test_list_recent_filters_by_vote(db_session) -> None:
    _make_project(db_session)
    upsert_vote(
        db_session, subject="a", project_id="proj_test_fi",
        feature_key=FEATURE_KEY, vote="interested",
    )
    upsert_vote(
        db_session, subject="b", project_id="proj_test_fi",
        feature_key=FEATURE_KEY, vote="not_interested",
    )
    interested_only = list_recent_votes(
        db_session, feature_key=FEATURE_KEY, vote_filter="interested"
    )
    assert len(interested_only) == 1
    assert interested_only[0]["vote"] == "interested"


def test_list_recent_rejects_invalid_filter(db_session) -> None:
    with pytest.raises(InvalidVoteError):
        list_recent_votes(
            db_session, feature_key=FEATURE_KEY, vote_filter="bogus"
        )


def test_list_recent_orders_newest_first(db_session) -> None:
    _make_project(db_session)
    upsert_vote(
        db_session, subject="a", project_id="proj_test_fi",
        feature_key=FEATURE_KEY, vote="interested",
    )
    upsert_vote(
        db_session, subject="b", project_id="proj_test_fi",
        feature_key=FEATURE_KEY, vote="interested",
    )
    rows = list_recent_votes(db_session, feature_key=FEATURE_KEY)
    assert len(rows) == 2
    assert rows[0]["created_at"] >= rows[1]["created_at"]


# ── service: mask_email ─────────────────────────────────────────────────────


def test_mask_email_basic() -> None:
    assert mask_email("dev@acme.com") == "d***@acme.com"


def test_mask_email_short_local() -> None:
    assert mask_email("a@b.io") == "*@b.io"


def test_mask_email_none() -> None:
    assert mask_email(None) is None


def test_mask_email_invalid_safe_fallback() -> None:
    assert mask_email("not-an-email") == "***"


# ── HTTP fixtures ───────────────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    get_settings.cache_clear()
    db_path = tmp_path / "test_fi_route.db"
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

    # Seed a project so FK constraint is satisfied for votes
    with session_factory() as seed_session:
        seed_session.add(Project(id="proj_test_fi", name="Acme", owner_ref="o-1"))
        seed_session.add(User(subject="user-alpha", email="dev@acme.com"))
        seed_session.commit()

    with TestClient(app) as test_client:
        test_client._session_factory = session_factory  # type: ignore[attr-defined]
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _override_tenant(subject: str | None = "user-alpha", project_id: str = "proj_test_fi") -> None:
    """Inject a TenantContext into the customer router for testing."""
    def _fake() -> TenantContext:
        return TenantContext(tenant_id=project_id, role="member", subject=subject)
    app.dependency_overrides[require_tenant_context] = _fake


# ── HTTP: POST /v1/feature-interest ─────────────────────────────────────────


def test_post_vote_creates_row(client: TestClient) -> None:
    _override_tenant()
    resp = client.post(
        "/v1/feature-interest",
        json={
            "feature_key": FEATURE_KEY,
            "vote": "interested",
            "use_case": "rollback on drop",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["feature_key"] == FEATURE_KEY
    assert body["vote"] == "interested"
    assert body["use_case"] == "rollback on drop"


def test_post_vote_upserts_on_repeat(client: TestClient) -> None:
    _override_tenant()
    client.post(
        "/v1/feature-interest",
        json={"feature_key": FEATURE_KEY, "vote": "interested"},
    )
    resp = client.post(
        "/v1/feature-interest",
        json={"feature_key": FEATURE_KEY, "vote": "not_interested"},
    )
    assert resp.status_code == 200
    assert resp.json()["vote"] == "not_interested"


def test_post_vote_rejects_unknown_feature(client: TestClient) -> None:
    _override_tenant()
    resp = client.post(
        "/v1/feature-interest",
        json={"feature_key": "bogus.feature", "vote": "interested"},
    )
    assert resp.status_code == 400


def test_post_vote_rejects_invalid_vote_value(client: TestClient) -> None:
    _override_tenant()
    resp = client.post(
        "/v1/feature-interest",
        json={"feature_key": FEATURE_KEY, "vote": "maybe"},
    )
    # Caught by Pydantic Literal validation → 422
    assert resp.status_code == 422


def test_post_vote_rejects_api_key_auth(client: TestClient) -> None:
    """No subject -> 401: machine identities cannot vote."""
    _override_tenant(subject=None)
    resp = client.post(
        "/v1/feature-interest",
        json={"feature_key": FEATURE_KEY, "vote": "interested"},
    )
    assert resp.status_code == 401


# ── HTTP: GET /v1/feature-interest/me ───────────────────────────────────────


def test_get_my_vote_404_when_not_voted(client: TestClient) -> None:
    _override_tenant()
    resp = client.get(
        "/v1/feature-interest/me",
        params={"feature_key": FEATURE_KEY},
    )
    assert resp.status_code == 404


def test_get_my_vote_returns_vote(client: TestClient) -> None:
    _override_tenant()
    client.post(
        "/v1/feature-interest",
        json={"feature_key": FEATURE_KEY, "vote": "interested"},
    )
    resp = client.get(
        "/v1/feature-interest/me",
        params={"feature_key": FEATURE_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["vote"] == "interested"


def test_get_my_vote_rejects_unknown_feature(client: TestClient) -> None:
    _override_tenant()
    resp = client.get(
        "/v1/feature-interest/me",
        params={"feature_key": "bogus.feature"},
    )
    assert resp.status_code == 400


# ── HTTP: admin endpoints ───────────────────────────────────────────────────


def _set_provisioning(monkeypatch, token: str = "test-prov-token") -> dict[str, str]:
    """Enable PROVISIONING_TOKEN auth and return matching headers."""
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "true")
    monkeypatch.setenv("PROVISIONING_TOKEN", token)
    get_settings.cache_clear()
    # Default header name is `x-zroky-admin-token` per Settings
    return {"x-zroky-admin-token": token}


def test_admin_list_features_requires_provisioning(
    client: TestClient, monkeypatch,
) -> None:
    _set_provisioning(monkeypatch)
    resp = client.get("/v1/admin/feature-interest")
    assert resp.status_code == 401


def test_admin_list_features_with_token(
    client: TestClient, monkeypatch,
) -> None:
    headers = _set_provisioning(monkeypatch)
    resp = client.get("/v1/admin/feature-interest", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "features" in body
    feature_keys = [f["feature_key"] for f in body["features"]]
    assert FEATURE_KEY in feature_keys


def test_admin_feature_detail_returns_summary_and_rows(
    client: TestClient, monkeypatch,
) -> None:
    _override_tenant()
    client.post(
        "/v1/feature-interest",
        json={
            "feature_key": FEATURE_KEY,
            "vote": "interested",
            "use_case": "fallback swap when openai down",
        },
    )

    headers = _set_provisioning(monkeypatch)
    resp = client.get(
        f"/v1/admin/feature-interest/{FEATURE_KEY}",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["total"] == 1
    assert body["summary"]["interested"] == 1
    assert len(body["recent_votes"]) == 1
    assert body["recent_votes"][0]["use_case"] == "fallback swap when openai down"
    assert body["recent_votes"][0]["user_email_masked"] == "d***@acme.com"


def test_admin_csv_export(client: TestClient, monkeypatch) -> None:
    _override_tenant()
    client.post(
        "/v1/feature-interest",
        json={"feature_key": FEATURE_KEY, "vote": "interested"},
    )

    headers = _set_provisioning(monkeypatch)
    resp = client.get(
        f"/v1/admin/feature-interest/{FEATURE_KEY}/export.csv",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    text = resp.text
    assert "created_at" in text  # header line
    assert "interested" in text  # body line
    assert "d***@acme.com" in text  # mask preserved in export


def test_admin_csv_export_escapes_commas_in_use_case(
    client: TestClient, monkeypatch,
) -> None:
    _override_tenant()
    client.post(
        "/v1/feature-interest",
        json={
            "feature_key": FEATURE_KEY,
            "vote": "interested",
            "use_case": "rollback, swap, tune — all three",
        },
    )

    headers = _set_provisioning(monkeypatch)
    resp = client.get(
        f"/v1/admin/feature-interest/{FEATURE_KEY}/export.csv",
        headers=headers,
    )
    # csv.QUOTE_MINIMAL wraps fields with commas in double quotes
    assert '"rollback, swap, tune — all three"' in resp.text


def test_admin_feature_detail_filter_by_vote(
    client: TestClient, monkeypatch,
) -> None:
    _override_tenant(subject="user-alpha")
    client.post(
        "/v1/feature-interest",
        json={"feature_key": FEATURE_KEY, "vote": "interested"},
    )
    _override_tenant(subject="user-beta")
    client.post(
        "/v1/feature-interest",
        json={"feature_key": FEATURE_KEY, "vote": "not_interested"},
    )

    headers = _set_provisioning(monkeypatch)
    resp = client.get(
        f"/v1/admin/feature-interest/{FEATURE_KEY}",
        params={"vote": "interested"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    # Summary reflects all votes; recent_votes is filtered
    assert body["summary"]["total"] == 2
    assert len(body["recent_votes"]) == 1
    assert body["recent_votes"][0]["vote"] == "interested"
