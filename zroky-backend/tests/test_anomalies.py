"""Tests for the new anomalies service + /v1/anomalies route surface.

Module 3 Phase B coverage:
  - Service-level: fingerprint determinism, failure_code mapping, upsert
    insert + upsert paths, sample-call-id merge, status transitions.
  - Route-level: list filters, validation errors, cursor pagination,
    detail 404/200, resolve/acknowledge/mute.
  - Issue-consolidation integration: public issue writes create canonical
    `anomalies` rows, and `/v1/anomalies` advertises its deprecated status.
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
from app.db.models import Anomaly
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.anomalies import (
    VALID_DETECTORS,
    VALID_STATUSES,
    acknowledge_anomaly,
    compute_fingerprint,
    map_failure_code_to_detector,
    mute_anomaly,
    resolve_anomaly,
    upsert_anomaly,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    """Stand-alone session against a per-test SQLite db (service-level tests)."""
    db_path = tmp_path / "test_anomalies_svc.db"
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
    """TestClient + per-test SQLite engine + dependency overrides."""
    get_settings.cache_clear()
    db_path = tmp_path / "test_anomalies_route.db"
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
        # expose the session factory so tests can seed rows directly
        test_client._session_factory = session_factory  # type: ignore[attr-defined]
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


# ── helpers ──────────────────────────────────────────────────────────────────


def _seed_anomaly(
    session_factory,
    *,
    project_id: str,
    detector: str = "LOOP_DETECTED",
    prompt_fingerprint: str | None = "fp-A",
    agent_name: str | None = "agent-A",
    call_id: str | None = "call-1",
    occurred_at: datetime | None = None,
) -> Anomaly:
    session = session_factory()
    try:
        anomaly = upsert_anomaly(
            session,
            project_id=project_id,
            detector=detector,
            prompt_fingerprint=prompt_fingerprint,
            agent_name=agent_name,
            call_id=call_id,
            occurred_at=occurred_at,
        )
        assert anomaly is not None
        # re-fetch detached copy for the test to work with
        return session.get(Anomaly, anomaly.id)  # type: ignore[return-value]
    finally:
        session.close()


# ── service: pure helpers ────────────────────────────────────────────────────


class TestFingerprintHelper:
    def test_fingerprint_is_deterministic(self) -> None:
        a = compute_fingerprint(
            detector="LOOP_DETECTED", prompt_fingerprint="fp", agent_name="alpha"
        )
        b = compute_fingerprint(
            detector="LOOP_DETECTED", prompt_fingerprint="fp", agent_name="alpha"
        )
        assert a == b
        assert len(a) == 64  # sha256 hex

    def test_fingerprint_differs_on_any_field(self) -> None:
        base = compute_fingerprint(
            detector="LOOP_DETECTED", prompt_fingerprint="fp", agent_name="alpha"
        )
        assert base != compute_fingerprint(
            detector="COST_SPIKE", prompt_fingerprint="fp", agent_name="alpha"
        )
        assert base != compute_fingerprint(
            detector="LOOP_DETECTED", prompt_fingerprint="fp2", agent_name="alpha"
        )
        assert base != compute_fingerprint(
            detector="LOOP_DETECTED", prompt_fingerprint="fp", agent_name="beta"
        )
        assert base != compute_fingerprint(
            detector="LOOP_DETECTED",
            prompt_fingerprint="fp",
            agent_name="alpha",
            extra="v2",
        )

    def test_fingerprint_normalises_whitespace_and_case(self) -> None:
        a = compute_fingerprint(
            detector="loop_detected", prompt_fingerprint=" fp ", agent_name="alpha"
        )
        b = compute_fingerprint(
            detector="LOOP_DETECTED", prompt_fingerprint="fp", agent_name="alpha"
        )
        assert a == b


class TestFailureCodeMapping:
    @pytest.mark.parametrize(
        "code,expected",
        [
            ("LOOP_DETECTED", "LOOP_DETECTED"),
            ("loop_detected", "LOOP_DETECTED"),
            ("COST_SPIKE", "COST_SPIKE"),
            ("HALLUCINATION", "HALLUCINATION_RISK"),
            ("SCHEMA_MISMATCH", "SCHEMA_VIOLATION"),
            ("LATENCY_REGRESSION", "LATENCY_REGRESSION"),
        ],
    )
    def test_kept_codes_map_to_detector(self, code: str, expected: str) -> None:
        assert map_failure_code_to_detector(code) == expected

    @pytest.mark.parametrize(
        "code",
        ["AUTH_FAILURE", "TOKEN_OVERFLOW", "RATE_LIMIT", "PROVIDER_ERROR"],
    )
    def test_former_preflight_codes_are_canonical_issues(self, code: str) -> None:
        assert map_failure_code_to_detector(code) == code

    @pytest.mark.parametrize("code", [None, "", "   ", "NOT_A_REAL_CODE"])
    def test_unknown_or_empty_returns_none(self, code: str | None) -> None:
        assert map_failure_code_to_detector(code) is None


# ── service: upsert + transitions ────────────────────────────────────────────


class TestUpsertAnomaly:
    def test_insert_creates_row_with_occurrence_one(self, db_session) -> None:
        anomaly = upsert_anomaly(
            db_session,
            project_id="proj-1",
            detector="LOOP_DETECTED",
            prompt_fingerprint="fp",
            agent_name="alpha",
            call_id="call-1",
        )
        assert anomaly is not None
        assert anomaly.project_id == "proj-1"
        assert anomaly.detector == "LOOP_DETECTED"
        assert anomaly.status == "open"
        assert anomaly.occurrence_count == 1
        assert anomaly.severity in {"low", "medium", "high", "critical"}
        ids = json.loads(anomaly.sample_call_ids_json or "[]")
        assert ids == ["call-1"]

    def test_repeat_upsert_increments_count_and_appends_call_id(self, db_session) -> None:
        first = upsert_anomaly(
            db_session,
            project_id="proj-1",
            detector="COST_SPIKE",
            prompt_fingerprint="fp",
            agent_name="alpha",
            call_id="call-1",
        )
        assert first is not None
        first_id = first.id

        second = upsert_anomaly(
            db_session,
            project_id="proj-1",
            detector="COST_SPIKE",
            prompt_fingerprint="fp",
            agent_name="alpha",
            call_id="call-2",
        )
        assert second is not None
        assert second.id == first_id, "same fingerprint must reuse the row"
        assert second.occurrence_count == 2
        ids = json.loads(second.sample_call_ids_json or "[]")
        assert ids == ["call-1", "call-2"]

    def test_sample_call_ids_capped_at_five(self, db_session) -> None:
        for n in range(1, 8):
            upsert_anomaly(
                db_session,
                project_id="proj-cap",
                detector="LOOP_DETECTED",
                prompt_fingerprint="fp",
                agent_name="alpha",
                call_id=f"call-{n}",
            )
        row = db_session.execute(
            select(Anomaly).where(Anomaly.project_id == "proj-cap")
        ).scalar_one()
        ids = json.loads(row.sample_call_ids_json or "[]")
        assert ids == ["call-3", "call-4", "call-5", "call-6", "call-7"]
        assert row.occurrence_count == 7

    def test_unknown_detector_returns_none_without_writing(self, db_session) -> None:
        result = upsert_anomaly(
            db_session,
            project_id="proj-x",
            detector="NOT_A_DETECTOR",
        )
        assert result is None
        rows = db_session.execute(
            select(Anomaly).where(Anomaly.project_id == "proj-x")
        ).scalars().all()
        assert rows == []

    def test_resolved_row_reopens_on_next_upsert(self, db_session) -> None:
        first = upsert_anomaly(
            db_session,
            project_id="proj-r",
            detector="LOOP_DETECTED",
            prompt_fingerprint="fp",
            agent_name="alpha",
            call_id="call-1",
        )
        assert first is not None
        resolved = resolve_anomaly(
            db_session, project_id="proj-r", anomaly_id=first.id
        )
        assert resolved is not None
        assert resolved.status == "resolved"

        repeat = upsert_anomaly(
            db_session,
            project_id="proj-r",
            detector="LOOP_DETECTED",
            prompt_fingerprint="fp",
            agent_name="alpha",
            call_id="call-2",
        )
        assert repeat is not None
        assert repeat.id == first.id
        assert repeat.status == "open"


class TestStatusTransitions:
    def test_resolve_marks_resolved(self, db_session) -> None:
        anomaly = upsert_anomaly(
            db_session,
            project_id="proj-1",
            detector="LOOP_DETECTED",
            prompt_fingerprint="fp",
            agent_name="alpha",
            call_id="call-1",
        )
        assert anomaly is not None
        result = resolve_anomaly(
            db_session, project_id="proj-1", anomaly_id=anomaly.id
        )
        assert result is not None
        assert result.status == "resolved"

    def test_acknowledge_marks_acknowledged(self, db_session) -> None:
        anomaly = upsert_anomaly(
            db_session,
            project_id="proj-1",
            detector="LOOP_DETECTED",
            prompt_fingerprint="fp",
            agent_name="alpha",
            call_id="call-1",
        )
        assert anomaly is not None
        result = acknowledge_anomaly(
            db_session, project_id="proj-1", anomaly_id=anomaly.id
        )
        assert result is not None
        assert result.status == "acknowledged"

    def test_mute_marks_muted(self, db_session) -> None:
        anomaly = upsert_anomaly(
            db_session,
            project_id="proj-1",
            detector="LOOP_DETECTED",
            prompt_fingerprint="fp",
            agent_name="alpha",
            call_id="call-1",
        )
        assert anomaly is not None
        result = mute_anomaly(
            db_session, project_id="proj-1", anomaly_id=anomaly.id
        )
        assert result is not None
        assert result.status == "muted"

    def test_transition_unknown_id_returns_none(self, db_session) -> None:
        assert resolve_anomaly(
            db_session, project_id="proj-1", anomaly_id="does-not-exist"
        ) is None

    def test_transition_wrong_tenant_returns_none(self, db_session) -> None:
        anomaly = upsert_anomaly(
            db_session,
            project_id="proj-A",
            detector="LOOP_DETECTED",
            prompt_fingerprint="fp",
            agent_name="alpha",
            call_id="call-1",
        )
        assert anomaly is not None
        # cross-tenant attempt
        assert resolve_anomaly(
            db_session, project_id="proj-B", anomaly_id=anomaly.id
        ) is None


# ── routes ────────────────────────────────────────────────────────────────────


PROJECT_HEADER = "X-Project-Id"


class TestListAnomalies:
    def test_empty_list(self, client: TestClient) -> None:
        response = client.get(
            "/v1/anomalies", headers={PROJECT_HEADER: "proj-empty"}
        )
        assert response.status_code == 200
        assert response.headers["Deprecation"] == "true"
        assert "use /v1/issues" in response.headers["X-Zroky-Deprecated"]
        body = response.json()
        assert body["items"] == []
        assert body["next_cursor"] is None
        assert body["total_in_page"] == 0

    def test_list_returns_seeded_rows_newest_first(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        base = datetime(2026, 5, 14, 0, 0, 0, tzinfo=timezone.utc)
        for n in range(3):
            _seed_anomaly(
                factory,
                project_id="proj-list",
                detector="LOOP_DETECTED",
                prompt_fingerprint=f"fp-{n}",
                agent_name="alpha",
                call_id=f"call-{n}",
                occurred_at=base + timedelta(minutes=n),
            )

        response = client.get(
            "/v1/anomalies", headers={PROJECT_HEADER: "proj-list"}
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 3
        # newest-first by last_seen_at
        timestamps = [i["last_seen_at"] for i in items]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_status_filter_default_is_open(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        anomaly = _seed_anomaly(factory, project_id="proj-filter")
        # resolve it so it should be excluded by the default 'open' filter
        with factory() as session:
            resolve_anomaly(
                session, project_id="proj-filter", anomaly_id=anomaly.id
            )

        # default filter (status=open) → empty
        response = client.get(
            "/v1/anomalies", headers={PROJECT_HEADER: "proj-filter"}
        )
        assert response.status_code == 200
        assert response.json()["items"] == []

        # status=all → returned
        response = client.get(
            "/v1/anomalies?status=all", headers={PROJECT_HEADER: "proj-filter"}
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

        # status=resolved → returned
        response = client.get(
            "/v1/anomalies?status=resolved",
            headers={PROJECT_HEADER: "proj-filter"},
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_detector_filter(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        _seed_anomaly(
            factory,
            project_id="proj-det",
            detector="LOOP_DETECTED",
            prompt_fingerprint="fp-loop",
        )
        _seed_anomaly(
            factory,
            project_id="proj-det",
            detector="COST_SPIKE",
            prompt_fingerprint="fp-cost",
        )

        response = client.get(
            "/v1/anomalies?detector=COST_SPIKE",
            headers={PROJECT_HEADER: "proj-det"},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["detector"] == "COST_SPIKE"

    def test_invalid_status_rejected(self, client: TestClient) -> None:
        response = client.get(
            "/v1/anomalies?status=bogus",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_invalid_detector_rejected(self, client: TestClient) -> None:
        response = client.get(
            "/v1/anomalies?detector=NOT_A_DETECTOR",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_invalid_severity_rejected(self, client: TestClient) -> None:
        response = client.get(
            "/v1/anomalies?severity=ultra",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_invalid_cursor_rejected(self, client: TestClient) -> None:
        response = client.get(
            "/v1/anomalies?cursor=not-base64-json",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_cursor_pagination(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        base = datetime(2026, 5, 14, 0, 0, 0, tzinfo=timezone.utc)
        for n in range(5):
            _seed_anomaly(
                factory,
                project_id="proj-page",
                detector="LOOP_DETECTED",
                prompt_fingerprint=f"fp-{n}",
                occurred_at=base + timedelta(minutes=n),
            )

        first = client.get(
            "/v1/anomalies?limit=2",
            headers={PROJECT_HEADER: "proj-page"},
        ).json()
        assert len(first["items"]) == 2
        assert first["next_cursor"] is not None

        second = client.get(
            f"/v1/anomalies?limit=2&cursor={first['next_cursor']}",
            headers={PROJECT_HEADER: "proj-page"},
        ).json()
        assert len(second["items"]) == 2
        assert second["next_cursor"] is not None

        third = client.get(
            f"/v1/anomalies?limit=2&cursor={second['next_cursor']}",
            headers={PROJECT_HEADER: "proj-page"},
        ).json()
        assert len(third["items"]) == 1
        assert third["next_cursor"] is None

        seen_ids = (
            [i["id"] for i in first["items"]]
            + [i["id"] for i in second["items"]]
            + [i["id"] for i in third["items"]]
        )
        assert len(set(seen_ids)) == 5  # no duplicates across pages

    def test_tenant_isolation(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        _seed_anomaly(factory, project_id="proj-A")
        _seed_anomaly(factory, project_id="proj-B")

        a_response = client.get(
            "/v1/anomalies", headers={PROJECT_HEADER: "proj-A"}
        ).json()
        assert {item["project_id"] for item in a_response["items"]} == {"proj-A"}


class TestGetAnomaly:
    def test_404_for_missing(self, client: TestClient) -> None:
        response = client.get(
            "/v1/anomalies/does-not-exist",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 404

    def test_returns_seeded_row(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        anomaly = _seed_anomaly(factory, project_id="proj-detail")
        response = client.get(
            f"/v1/anomalies/{anomaly.id}",
            headers={PROJECT_HEADER: "proj-detail"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == anomaly.id
        assert body["detector"] == "LOOP_DETECTED"
        assert body["status"] == "open"

    def test_cross_tenant_returns_404(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        anomaly = _seed_anomaly(factory, project_id="proj-A")
        response = client.get(
            f"/v1/anomalies/{anomaly.id}",
            headers={PROJECT_HEADER: "proj-B"},
        )
        assert response.status_code == 404


class TestStatusTransitionRoutes:
    def test_resolve(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        anomaly = _seed_anomaly(factory, project_id="proj-1")
        response = client.post(
            f"/v1/anomalies/{anomaly.id}/resolve",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "resolved"

    def test_acknowledge(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        anomaly = _seed_anomaly(factory, project_id="proj-1")
        response = client.post(
            f"/v1/anomalies/{anomaly.id}/acknowledge",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "acknowledged"

    def test_mute(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        anomaly = _seed_anomaly(factory, project_id="proj-1")
        response = client.post(
            f"/v1/anomalies/{anomaly.id}/mute",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "muted"

    def test_resolve_unknown_returns_404(self, client: TestClient) -> None:
        response = client.post(
            "/v1/anomalies/missing-id/resolve",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 404


# ── dual-write integration ───────────────────────────────────────────────────


class TestIssueConsolidation:
    """Verify public issue writes now target the canonical anomaly model."""

    def test_upsert_issue_writes_canonical_anomaly(self, db_session) -> None:
        from app.services.issues import upsert_issue

        now = datetime.now(timezone.utc)
        anomaly = upsert_issue(
            db_session,
            project_id="proj-dual",
            failure_code="LOOP_DETECTED",
            prompt_fingerprint="fp-dual",
            agent_name="alpha",
            call_id="call-dual-1",
            diagnosis_id="diag-dual-1",
            occurred_at=now,
            call_cost_usd=0.5,
            evidence={"summary": "loop detected"},
        )
        assert anomaly is not None
        detector = map_failure_code_to_detector("LOOP_DETECTED")
        assert detector == "LOOP_DETECTED"

        anomalies = db_session.execute(
            select(Anomaly).where(Anomaly.project_id == "proj-dual")
        ).scalars().all()
        assert len(anomalies) == 1
        assert anomalies[0].detector == "LOOP_DETECTED"
        evidence = json.loads(anomalies[0].evidence_json or "{}")
        assert evidence["legacy_issue"]["failure_code"] == "LOOP_DETECTED"

    def test_auth_failure_is_canonical_anomaly(self, db_session) -> None:
        from app.services.issues import upsert_issue

        now = datetime.now(timezone.utc)
        anomaly = upsert_issue(
            db_session,
            project_id="proj-demoted",
            failure_code="AUTH_FAILURE",
            prompt_fingerprint="fp-x",
            agent_name="alpha",
            call_id="call-x",
            diagnosis_id="diag-x",
            occurred_at=now,
            call_cost_usd=0.0,
            evidence={"summary": "auth failure"},
        )
        assert anomaly is not None
        detector = map_failure_code_to_detector("AUTH_FAILURE")
        assert detector == "AUTH_FAILURE"

        anomalies = db_session.execute(
            select(Anomaly).where(Anomaly.project_id == "proj-demoted")
        ).scalars().all()
        assert len(anomalies) == 1
        assert anomalies[0].detector == "AUTH_FAILURE"


# ── invariants ───────────────────────────────────────────────────────────────


class TestInvariants:
    def test_valid_detectors_match_db_check(self) -> None:
        # The set declared in the service must match what the migration's
        # CHECK constraint allows. Drift here = silent runtime failure.
        assert VALID_DETECTORS == frozenset({
            "LOOP_DETECTED",
            "COST_SPIKE",
            "ACCURACY_REGRESSION",
            "HALLUCINATION_RISK",
            "SCHEMA_VIOLATION",
            "LATENCY_REGRESSION",
            "TOOL_SELECTION_FAILURE",
            "TOOL_CALL_FAILURE",
            "TOOL_ARGUMENT_MISMATCH",
            "RAG_RETRIEVAL_MISSING",
            "RETRIEVAL_MISSING",
            "TOKEN_USAGE_DRIFT",
            "TOKEN_OVERFLOW",
            "RATE_LIMIT",
            "AUTH_FAILURE",
            "PROVIDER_ERROR",
            "LATENCY_ANOMALY",
            "LATENCY_DRIFT",
            "ERROR_RATE_DRIFT",
            "EMPTY_OUTPUT",
            "OUTPUT_TRUNCATED",
            "OUTPUT_LENGTH_DRIFT",
            "REPEATED_OUTPUT",
            "BEHAVIORAL_DRIFT",
            "UNKNOWN",
        })

    def test_valid_statuses_match_db_check(self) -> None:
        assert VALID_STATUSES == frozenset({
            "open", "acknowledged", "resolved", "muted",
        })
