"""Tests for the Pilot-tier Intel feed (Module 4.6):

  GET /v1/intel/feed   filterable, paginated read surface over the
                       Intel Pulse `intel_signals` table.

Coverage:
  - validators (kind, min_severity, source, model)
  - severity threshold helper (≥-semantics)
  - cursor encode / decode (incl. tamper rejection)
  - defensive payload_json parser
  - service: filter combinations, only_active window, pagination
  - route: 200 happy path, 422 surfaces, opaque cursor round-trip,
    unknown-cursor 422, tenant-auth gate
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import IntelSignal
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.intel_feed import (
    IntelFeedFilterError,
    SEVERITY_RANK,
    VALID_KINDS,
    VALID_SEVERITIES,
    decode_cursor,
    encode_cursor,
    list_intel_signals,
    parse_kind,
    parse_min_severity,
    parse_model,
    parse_payload,
    parse_source,
    serialize_intel_signal,
    severities_at_or_above,
)


PROJECT_HEADER = "X-Project-Id"


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_intel_svc.db"
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
    db_path = tmp_path / "test_intel_route.db"
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


# ── helpers ──────────────────────────────────────────────────────────────────


def _seed_signal(
    session,
    *,
    source: str = "openai_status",
    kind: str = "outage",
    severity: str = "medium",
    confidence: float = 1.0,
    model_affected: str | None = None,
    url: str | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    payload: dict | str | None = None,
    created_at: datetime | None = None,
) -> IntelSignal:
    now = valid_from or datetime.now(timezone.utc)
    if isinstance(payload, dict):
        payload_json = json.dumps(payload)
    elif isinstance(payload, str):
        payload_json = payload
    else:
        payload_json = None
    row = IntelSignal(
        id=str(uuid4()),
        source=source,
        kind=kind,
        severity=severity,
        confidence=confidence,
        model_affected=model_affected,
        url=url,
        valid_from=now,
        valid_to=valid_to,
        payload_json=payload_json,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    if created_at is not None:
        # Override server-default created_at for ordering tests
        row.created_at = created_at
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


# ── validators ───────────────────────────────────────────────────────────────


class TestValidators:
    def test_parse_kind_valid(self) -> None:
        for k in VALID_KINDS:
            assert parse_kind(k) == k

    def test_parse_kind_normalises(self) -> None:
        assert parse_kind("  OUTAGE ") == "outage"

    def test_parse_kind_none_or_empty(self) -> None:
        assert parse_kind(None) is None
        assert parse_kind("") is None
        assert parse_kind("   ") is None

    def test_parse_kind_invalid(self) -> None:
        with pytest.raises(IntelFeedFilterError, match="kind"):
            parse_kind("not-a-kind")

    def test_parse_min_severity_valid(self) -> None:
        for s in VALID_SEVERITIES:
            assert parse_min_severity(s) == s

    def test_parse_min_severity_invalid(self) -> None:
        with pytest.raises(IntelFeedFilterError, match="min_severity"):
            parse_min_severity("urgent")

    def test_parse_source_lowers_and_strips(self) -> None:
        assert parse_source("  Openai_Status ") == "openai_status"

    def test_parse_source_too_long(self) -> None:
        with pytest.raises(IntelFeedFilterError, match="64"):
            parse_source("x" * 65)

    def test_parse_source_empty(self) -> None:
        assert parse_source(None) is None
        assert parse_source("") is None
        assert parse_source("   ") is None

    def test_parse_model_strips(self) -> None:
        assert parse_model("  gpt-4 ") == "gpt-4"

    def test_parse_model_too_long(self) -> None:
        with pytest.raises(IntelFeedFilterError, match="128"):
            parse_model("g" * 129)


class TestSeverityThreshold:
    def test_low_returns_all(self) -> None:
        assert severities_at_or_above("low") == [
            "low", "medium", "high", "critical"
        ]

    def test_medium_drops_low(self) -> None:
        assert severities_at_or_above("medium") == ["medium", "high", "critical"]

    def test_high_drops_low_and_medium(self) -> None:
        assert severities_at_or_above("high") == ["high", "critical"]

    def test_critical_only(self) -> None:
        assert severities_at_or_above("critical") == ["critical"]

    def test_rank_ordering(self) -> None:
        # Sanity check that the ranks are strictly increasing
        ranks = [SEVERITY_RANK[s] for s in ["low", "medium", "high", "critical"]]
        assert ranks == sorted(ranks)
        assert len(set(ranks)) == 4


# ── cursor encode/decode ─────────────────────────────────────────────────────


class TestCursor:
    def test_round_trip(self) -> None:
        token = encode_cursor("abc-123")
        assert decode_cursor(token) == "abc-123"

    def test_decode_none(self) -> None:
        assert decode_cursor(None) is None

    def test_decode_empty(self) -> None:
        assert decode_cursor("") is None
        assert decode_cursor("   ") is None

    def test_decode_garbage(self) -> None:
        with pytest.raises(IntelFeedFilterError, match="cursor"):
            decode_cursor("!!!not-base64!!!")

    def test_decode_yields_empty_payload_raises(self) -> None:
        # base64 of an empty string decodes to empty → invalid cursor
        empty_token = encode_cursor("   ")
        with pytest.raises(IntelFeedFilterError):
            decode_cursor(empty_token)


# ── parse_payload ────────────────────────────────────────────────────────────


class TestParsePayload:
    def test_none(self) -> None:
        assert parse_payload(None) == {}

    def test_empty(self) -> None:
        assert parse_payload("") == {}
        assert parse_payload("   ") == {}

    def test_malformed(self) -> None:
        assert parse_payload("{not-json") == {}

    def test_non_object(self) -> None:
        assert parse_payload("[1,2,3]") == {}
        assert parse_payload('"a string"') == {}

    def test_valid(self) -> None:
        assert parse_payload(json.dumps({"a": 1, "b": "x"})) == {"a": 1, "b": "x"}


# ── service: list_intel_signals ──────────────────────────────────────────────


class TestListSignalsService:
    def test_empty(self, db_session) -> None:
        assert list_intel_signals(db_session) == []

    def test_kind_filter(self, db_session) -> None:
        _seed_signal(db_session, kind="outage")
        _seed_signal(db_session, kind="cve")
        rows = list_intel_signals(db_session, kind="cve")
        assert len(rows) == 1
        assert rows[0].kind == "cve"

    def test_min_severity_threshold(self, db_session) -> None:
        _seed_signal(db_session, severity="low")
        _seed_signal(db_session, severity="medium")
        _seed_signal(db_session, severity="high")
        _seed_signal(db_session, severity="critical")
        # min=high → 2 rows
        rows = list_intel_signals(db_session, min_severity="high")
        kinds = sorted(r.severity for r in rows)
        assert kinds == ["critical", "high"]

    def test_source_filter(self, db_session) -> None:
        _seed_signal(db_session, source="openai_status")
        _seed_signal(db_session, source="anthropic_status")
        rows = list_intel_signals(db_session, source="openai_status")
        assert len(rows) == 1
        assert rows[0].source == "openai_status"

    def test_model_substring(self, db_session) -> None:
        _seed_signal(db_session, model_affected="gpt-4o-2024-05-13")
        _seed_signal(db_session, model_affected="gpt-4-turbo")
        _seed_signal(db_session, model_affected="claude-3-haiku")
        rows = list_intel_signals(db_session, model="gpt-4")
        models = sorted(r.model_affected for r in rows)
        assert models == ["gpt-4-turbo", "gpt-4o-2024-05-13"]

    def test_model_filter_skips_null_rows(self, db_session) -> None:
        _seed_signal(db_session, model_affected=None)
        _seed_signal(db_session, model_affected="gpt-4o")
        rows = list_intel_signals(db_session, model="gpt")
        assert len(rows) == 1
        assert rows[0].model_affected == "gpt-4o"

    def test_only_active_default_excludes_expired(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        # Already-expired
        _seed_signal(
            db_session,
            valid_from=now - timedelta(days=10),
            valid_to=now - timedelta(days=1),
        )
        # Currently active
        active = _seed_signal(
            db_session,
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=1),
        )
        # Active with no end date
        open_ended = _seed_signal(
            db_session,
            valid_from=now - timedelta(hours=1),
            valid_to=None,
        )
        rows = list_intel_signals(db_session, only_active=True, now=now)
        ids = {r.id for r in rows}
        assert ids == {active.id, open_ended.id}

    def test_only_active_excludes_future_signals(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        _seed_signal(
            db_session,
            valid_from=now + timedelta(days=1),
            valid_to=now + timedelta(days=2),
        )
        rows = list_intel_signals(db_session, only_active=True, now=now)
        assert rows == []

    def test_only_active_false_returns_all(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        _seed_signal(
            db_session,
            valid_from=now - timedelta(days=10),
            valid_to=now - timedelta(days=1),
        )
        _seed_signal(db_session, valid_from=now - timedelta(hours=1))
        rows = list_intel_signals(db_session, only_active=False)
        assert len(rows) == 2

    def test_newest_first(self, db_session) -> None:
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        a = _seed_signal(db_session, created_at=base)
        b = _seed_signal(db_session, created_at=base + timedelta(hours=1))
        c = _seed_signal(db_session, created_at=base + timedelta(hours=2))
        rows = list_intel_signals(db_session, only_active=False)
        assert [r.id for r in rows] == [c.id, b.id, a.id]

    def test_pagination_via_cursor(self, db_session) -> None:
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        seeded = [
            _seed_signal(db_session, created_at=base + timedelta(hours=n))
            for n in range(5)
        ]
        # Newest first: seeded[4], [3], [2], [1], [0]
        first = list_intel_signals(db_session, only_active=False, limit=2)
        assert [r.id for r in first] == [seeded[4].id, seeded[3].id]

        second = list_intel_signals(
            db_session, only_active=False, limit=2, cursor_id=seeded[3].id
        )
        assert [r.id for r in second] == [seeded[2].id, seeded[1].id]

        third = list_intel_signals(
            db_session, only_active=False, limit=2, cursor_id=seeded[1].id
        )
        assert [r.id for r in third] == [seeded[0].id]

    def test_invalid_cursor_id_raises(self, db_session) -> None:
        with pytest.raises(IntelFeedFilterError, match="cursor"):
            list_intel_signals(db_session, cursor_id="missing")

    def test_invalid_limit_raises(self, db_session) -> None:
        with pytest.raises(IntelFeedFilterError, match="limit"):
            list_intel_signals(db_session, limit=0)
        with pytest.raises(IntelFeedFilterError, match="limit"):
            list_intel_signals(db_session, limit=101)

    def test_combined_filters(self, db_session) -> None:
        # Match: openai_status + outage + critical + gpt-4
        match = _seed_signal(
            db_session,
            source="openai_status",
            kind="outage",
            severity="critical",
            model_affected="gpt-4o",
        )
        # Different kind → excluded
        _seed_signal(
            db_session,
            source="openai_status", kind="cve", severity="critical",
            model_affected="gpt-4o",
        )
        # Different model → excluded
        _seed_signal(
            db_session,
            source="openai_status", kind="outage", severity="critical",
            model_affected="claude-3",
        )
        rows = list_intel_signals(
            db_session,
            kind="outage",
            min_severity="high",
            source="openai_status",
            model="gpt-4",
        )
        assert len(rows) == 1 and rows[0].id == match.id


# ── service: serialize_intel_signal ──────────────────────────────────────────


class TestSerialize:
    def test_full_shape(self, db_session) -> None:
        now = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)
        row = _seed_signal(
            db_session,
            source="openai_status",
            kind="outage",
            severity="high",
            confidence=0.9,
            url="https://status.openai.com/incidents/abc",
            model_affected="gpt-4o",
            valid_from=now,
            valid_to=now + timedelta(hours=2),
            payload={"region": "us-east-1", "incident_id": "abc"},
        )
        wire = serialize_intel_signal(row)
        assert wire["id"] == row.id
        assert wire["source"] == "openai_status"
        assert wire["kind"] == "outage"
        assert wire["severity"] == "high"
        assert wire["confidence"] == 0.9
        assert wire["url"].endswith("/abc")
        assert wire["model_affected"] == "gpt-4o"
        assert wire["valid_from"].startswith("2026-05-13T12:00:00")
        assert wire["valid_to"].startswith("2026-05-13T14:00:00")
        assert wire["payload"] == {"region": "us-east-1", "incident_id": "abc"}

    def test_empty_payload(self, db_session) -> None:
        row = _seed_signal(db_session, payload=None)
        wire = serialize_intel_signal(row)
        assert wire["payload"] == {}
        assert wire["valid_to"] is None

    def test_corrupt_payload_degrades_to_empty(self, db_session) -> None:
        row = _seed_signal(db_session, payload="{not-json")
        wire = serialize_intel_signal(row)
        assert wire["payload"] == {}


# ── route: GET /v1/intel/feed ────────────────────────────────────────────────


class TestIntelFeedRoute:
    def test_401_without_tenant(self, client: TestClient) -> None:
        # No X-Project-Id header → 401 from tenant guard
        response = client.get("/v1/intel/feed")
        assert response.status_code == 401

    def test_empty(self, client: TestClient) -> None:
        response = client.get(
            "/v1/intel/feed", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["next_cursor"] is None
        assert body["total_in_page"] == 0

    def test_happy_path(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_signal(
                session, kind="outage", severity="high",
                model_affected="gpt-4o",
                payload={"region": "us-east-1"},
            )
        response = client.get(
            "/v1/intel/feed", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["kind"] == "outage"
        assert items[0]["payload"] == {"region": "us-east-1"}

    def test_filter_kind(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_signal(session, kind="outage")
            _seed_signal(session, kind="cve")
            _seed_signal(session, kind="advisory")
        body = client.get(
            "/v1/intel/feed?kind=cve", headers={PROJECT_HEADER: "proj-1"}
        ).json()
        assert len(body["items"]) == 1
        assert body["items"][0]["kind"] == "cve"

    def test_filter_min_severity(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_signal(session, severity="low")
            _seed_signal(session, severity="critical")
        body = client.get(
            "/v1/intel/feed?min_severity=high",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        sevs = [i["severity"] for i in body["items"]]
        assert sevs == ["critical"]

    def test_filter_source(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_signal(session, source="openai_status")
            _seed_signal(session, source="anthropic_status")
        body = client.get(
            "/v1/intel/feed?source=anthropic_status",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        assert len(body["items"]) == 1
        assert body["items"][0]["source"] == "anthropic_status"

    def test_filter_model_substring(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_signal(session, model_affected="gpt-4o-2024-05-13")
            _seed_signal(session, model_affected="claude-3-haiku")
        body = client.get(
            "/v1/intel/feed?model=gpt-4",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        assert len(body["items"]) == 1
        assert "gpt-4" in body["items"][0]["model_affected"]

    def test_only_active_default(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        now = datetime.now(timezone.utc)
        with factory() as session:
            _seed_signal(
                session,
                valid_from=now - timedelta(days=10),
                valid_to=now - timedelta(days=1),
            )
            _seed_signal(session, valid_from=now - timedelta(hours=1))

        body = client.get(
            "/v1/intel/feed", headers={PROJECT_HEADER: "proj-1"}
        ).json()
        # default only_active=true → expired row is excluded
        assert body["total_in_page"] == 1

    def test_only_active_false(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        now = datetime.now(timezone.utc)
        with factory() as session:
            _seed_signal(
                session,
                valid_from=now - timedelta(days=10),
                valid_to=now - timedelta(days=1),
            )
            _seed_signal(session, valid_from=now - timedelta(hours=1))

        body = client.get(
            "/v1/intel/feed?only_active=false",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        assert body["total_in_page"] == 2

    def test_pagination_round_trip(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        with factory() as session:
            for n in range(5):
                _seed_signal(
                    session,
                    valid_from=base + timedelta(hours=n),
                    created_at=base + timedelta(hours=n),
                )

        first = client.get(
            "/v1/intel/feed?only_active=false&limit=2",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        assert len(first["items"]) == 2
        assert first["next_cursor"] is not None

        second = client.get(
            f"/v1/intel/feed?only_active=false&limit=2&cursor={first['next_cursor']}",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        assert len(second["items"]) == 2

        third = client.get(
            f"/v1/intel/feed?only_active=false&limit=2&cursor={second['next_cursor']}",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        assert len(third["items"]) == 1
        assert third["next_cursor"] is None

        seen = (
            [i["id"] for i in first["items"]]
            + [i["id"] for i in second["items"]]
            + [i["id"] for i in third["items"]]
        )
        assert len(set(seen)) == 5  # no duplicates across pages

    def test_invalid_kind_422(self, client: TestClient) -> None:
        response = client.get(
            "/v1/intel/feed?kind=bogus",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_invalid_severity_422(self, client: TestClient) -> None:
        response = client.get(
            "/v1/intel/feed?min_severity=urgent",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_invalid_cursor_422(self, client: TestClient) -> None:
        response = client.get(
            "/v1/intel/feed?cursor=!!!garbage!!!",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_unknown_cursor_id_422(self, client: TestClient) -> None:
        # Valid base64, decodes to a cursor row that doesn't exist
        bad = encode_cursor("missing-id-xyz")
        response = client.get(
            f"/v1/intel/feed?cursor={bad}",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_limit_bounds_check(self, client: TestClient) -> None:
        for bad_limit in (0, 101):
            response = client.get(
                f"/v1/intel/feed?limit={bad_limit}",
                headers={PROJECT_HEADER: "proj-1"},
            )
            assert response.status_code == 422

    def test_global_table_two_tenants_see_same_data(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_signal(session, kind="outage")
            _seed_signal(session, kind="cve")

        body_a = client.get(
            "/v1/intel/feed", headers={PROJECT_HEADER: "proj-A"}
        ).json()
        body_b = client.get(
            "/v1/intel/feed", headers={PROJECT_HEADER: "proj-B"}
        ).json()
        # intel_signals is global — both tenants see all rows
        assert body_a["total_in_page"] == 2
        assert body_b["total_in_page"] == 2
        assert {i["id"] for i in body_a["items"]} == {
            i["id"] for i in body_b["items"]
        }


# ── invariants ──────────────────────────────────────────────────────────────


class TestInvariants:
    def test_kinds_match_migration_check_vocab(self) -> None:
        # Mirrors `kind IN (...)` from alembic/versions/0055_*.py
        assert VALID_KINDS == frozenset(
            {"outage", "deprecation", "cve", "pricing_change", "advisory"}
        )

    def test_severities_match_migration_check_vocab(self) -> None:
        assert VALID_SEVERITIES == frozenset(
            {"low", "medium", "high", "critical"}
        )
