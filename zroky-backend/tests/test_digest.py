"""Tests for the Pilot-tier digest read surface (Module 4.4):

  - GET /v1/digest          compact list with cursor by week_start
  - GET /v1/digest/{week}   detail (404 missing, 422 malformed/non-Monday)

Service-level coverage: parse_week_param, get_digest/list_digests,
defensive parsers (summary + recipients), serializer wire shape.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Digest
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.digest_engine import (
    WeekFormatError,
    get_digest,
    list_digests,
    monday_of,
    parse_recipients,
    parse_summary_json,
    parse_week_param,
    serialize_digest,
    serialize_digest_summary,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_digest_svc.db"
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
    db_path = tmp_path / "test_digest_route.db"
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


# ── helpers ──────────────────────────────────────────────────────────────────


def _seed_digest(
    session,
    *,
    project_id: str,
    week_start: date,
    summary: dict | None = None,
    html_blob: str | None = None,
    recipients: list[str] | None = None,
    sent_at: datetime | None = None,
) -> Digest:
    digest = Digest(
        project_id=project_id,
        week_start=week_start,
        summary_json=json.dumps(summary) if summary is not None else None,
        html_blob=html_blob,
        sent_to_emails=json.dumps(recipients) if recipients is not None else None,
        sent_at=sent_at,
    )
    session.add(digest)
    session.commit()
    session.refresh(digest)
    return digest


# ── service: parse_week_param ────────────────────────────────────────────────


class TestParseWeekParam:
    def test_iso_date_monday(self) -> None:
        assert parse_week_param("2026-05-11") == date(2026, 5, 11)

    def test_iso_date_not_monday_raises(self) -> None:
        # 2026-05-14 is a Thursday
        with pytest.raises(WeekFormatError, match="Monday"):
            parse_week_param("2026-05-14")

    def test_iso_week(self) -> None:
        # ISO week 19 of 2026 starts on 2026-05-04 (Mon)
        assert parse_week_param("2026-W19") == date(2026, 5, 4)

    def test_iso_week_lowercase_w(self) -> None:
        # "2026-w19" should also work (we uppercase)
        assert parse_week_param("2026-w19") == date(2026, 5, 4)

    def test_iso_week_zero_padding(self) -> None:
        # "2026-W01" -> 2025-12-29 (the Monday of ISO week 1, 2026)
        assert parse_week_param("2026-W01") == date(2025, 12, 29)

    def test_iso_week_53_invalid_year(self) -> None:
        # 2026 has only 53 weeks if it does — most years don't.
        # Pick a year with 52 weeks: 2027 has 52 weeks → W53 invalid.
        with pytest.raises(WeekFormatError):
            parse_week_param("2027-W53")

    def test_iso_week_out_of_range_raises(self) -> None:
        with pytest.raises(WeekFormatError, match="out of range"):
            parse_week_param("2026-W54")
        with pytest.raises(WeekFormatError, match="out of range"):
            parse_week_param("2026-W0")

    def test_garbage_raises(self) -> None:
        with pytest.raises(WeekFormatError):
            parse_week_param("not-a-date")

    def test_empty_raises(self) -> None:
        with pytest.raises(WeekFormatError):
            parse_week_param("")

    def test_none_raises(self) -> None:
        with pytest.raises(WeekFormatError):
            parse_week_param(None)  # type: ignore[arg-type]

    def test_whitespace_raises(self) -> None:
        with pytest.raises(WeekFormatError):
            parse_week_param("   ")

    def test_iso_week_malformed_raises(self) -> None:
        with pytest.raises(WeekFormatError, match="ISO week"):
            parse_week_param("2026-WAB")

    def test_monday_of_helper(self) -> None:
        # Thursday 2026-05-14 → Monday 2026-05-11
        assert monday_of(date(2026, 5, 14)) == date(2026, 5, 11)
        # Already Monday → unchanged
        assert monday_of(date(2026, 5, 11)) == date(2026, 5, 11)
        # Sunday 2026-05-17 → Monday 2026-05-11
        assert monday_of(date(2026, 5, 17)) == date(2026, 5, 11)


# ── service: defensive parsers ───────────────────────────────────────────────


class TestParsers:
    def test_summary_none(self) -> None:
        assert parse_summary_json(None) == {}

    def test_summary_empty_string(self) -> None:
        assert parse_summary_json("") == {}

    def test_summary_malformed(self) -> None:
        assert parse_summary_json("{not-json") == {}

    def test_summary_non_object(self) -> None:
        assert parse_summary_json("[1,2,3]") == {}

    def test_summary_valid(self) -> None:
        result = parse_summary_json(json.dumps({"a": 1, "b": "x"}))
        assert result == {"a": 1, "b": "x"}

    def test_recipients_none(self) -> None:
        assert parse_recipients(None) == []

    def test_recipients_empty(self) -> None:
        assert parse_recipients("") == []

    def test_recipients_malformed(self) -> None:
        assert parse_recipients("not-json") == []

    def test_recipients_non_list(self) -> None:
        assert parse_recipients(json.dumps({"oops": "yes"})) == []

    def test_recipients_filters_non_strings(self) -> None:
        raw = json.dumps(["a@example.com", 42, None, "  ", "b@example.com"])
        assert parse_recipients(raw) == ["a@example.com", "b@example.com"]


# ── service: reads ───────────────────────────────────────────────────────────


class TestServiceReads:
    def test_get_missing_returns_none(self, db_session) -> None:
        assert get_digest(
            db_session, project_id="proj-1", week_start=date(2026, 5, 11)
        ) is None

    def test_get_cross_tenant_returns_none(self, db_session) -> None:
        _seed_digest(
            db_session,
            project_id="proj-A",
            week_start=date(2026, 5, 11),
            summary={"calls": 100},
        )
        result = get_digest(
            db_session,
            project_id="proj-B",
            week_start=date(2026, 5, 11),
        )
        assert result is None

    def test_get_happy(self, db_session) -> None:
        _seed_digest(
            db_session,
            project_id="proj-1",
            week_start=date(2026, 5, 11),
            summary={"prevented_waste_usd": 12.34},
        )
        digest = get_digest(
            db_session,
            project_id="proj-1",
            week_start=date(2026, 5, 11),
        )
        assert digest is not None
        assert digest.project_id == "proj-1"

    def test_list_empty(self, db_session) -> None:
        assert list_digests(db_session, project_id="proj-1") == []

    def test_list_newest_first(self, db_session) -> None:
        _seed_digest(
            db_session, project_id="proj-1", week_start=date(2026, 5, 4)
        )
        _seed_digest(
            db_session, project_id="proj-1", week_start=date(2026, 5, 11)
        )
        _seed_digest(
            db_session, project_id="proj-1", week_start=date(2026, 4, 27)
        )

        rows = list_digests(db_session, project_id="proj-1")
        weeks = [r.week_start for r in rows]
        assert weeks == [date(2026, 5, 11), date(2026, 5, 4), date(2026, 4, 27)]

    def test_list_tenant_isolation(self, db_session) -> None:
        _seed_digest(
            db_session, project_id="proj-A", week_start=date(2026, 5, 11)
        )
        _seed_digest(
            db_session, project_id="proj-B", week_start=date(2026, 5, 11)
        )
        a_rows = list_digests(db_session, project_id="proj-A")
        assert len(a_rows) == 1
        assert a_rows[0].project_id == "proj-A"

    def test_list_cursor(self, db_session) -> None:
        for offset in range(5):
            _seed_digest(
                db_session,
                project_id="proj-1",
                week_start=date(2026, 5, 11) - 7 * offset * date.resolution,
            )
        # Walk pages
        rows1 = list_digests(db_session, project_id="proj-1", limit=2)
        assert len(rows1) == 2
        rows2 = list_digests(
            db_session,
            project_id="proj-1",
            limit=2,
            before_week_start=rows1[-1].week_start,
        )
        assert len(rows2) == 2
        assert rows2[0].week_start < rows1[-1].week_start

    def test_list_invalid_limit_raises(self, db_session) -> None:
        with pytest.raises(ValueError, match="limit"):
            list_digests(db_session, project_id="proj-1", limit=0)


# ── service: serializer ──────────────────────────────────────────────────────


class TestSerializer:
    def test_full_shape(self, db_session) -> None:
        digest = _seed_digest(
            db_session,
            project_id="proj-1",
            week_start=date(2026, 5, 11),
            summary={"prevented_waste_usd": 12.34, "incidents_caught": 3},
            html_blob="<html>...</html>",
            recipients=["a@example.com", "b@example.com"],
            sent_at=datetime(2026, 5, 18, 23, 0, 0, tzinfo=timezone.utc),
        )
        wire = serialize_digest(digest)
        assert wire["project_id"] == "proj-1"
        assert wire["week_start"] == "2026-05-11"
        assert wire["summary"] == {
            "prevented_waste_usd": 12.34,
            "incidents_caught": 3,
        }
        assert wire["html_blob"] == "<html>...</html>"
        assert wire["sent_to_emails"] == ["a@example.com", "b@example.com"]
        assert wire["sent_at"].startswith("2026-05-18T23:00:00")

    def test_unpopulated_row(self, db_session) -> None:
        # No summary, no html, no recipients, no sent_at
        digest = _seed_digest(
            db_session, project_id="proj-1", week_start=date(2026, 5, 11)
        )
        wire = serialize_digest(digest)
        assert wire["summary"] == {}
        assert wire["html_blob"] is None
        assert wire["sent_to_emails"] == []
        assert wire["sent_at"] is None

    def test_summary_shape_drops_html_and_summary(self, db_session) -> None:
        digest = _seed_digest(
            db_session,
            project_id="proj-1",
            week_start=date(2026, 5, 11),
            summary={"a": 1},
            html_blob="huge",
        )
        compact = serialize_digest_summary(digest)
        assert "summary" not in compact
        assert "html_blob" not in compact
        assert compact["week_start"] == "2026-05-11"


# ── route: GET /v1/digest/{week} ─────────────────────────────────────────────


class TestGetDigestRoute:
    def test_404_when_missing(self, client: TestClient) -> None:
        response = client.get(
            "/v1/digest/2026-05-11", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 404

    def test_200_iso_date(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_digest(
                session,
                project_id="proj-1",
                week_start=date(2026, 5, 11),
                summary={"prevented_waste_usd": 12.34},
                html_blob="<html>",
                recipients=["a@example.com"],
            )
        response = client.get(
            "/v1/digest/2026-05-11", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["project_id"] == "proj-1"
        assert body["week_start"] == "2026-05-11"
        assert body["summary"] == {"prevented_waste_usd": 12.34}
        assert body["html_blob"] == "<html>"
        assert body["sent_to_emails"] == ["a@example.com"]
        assert body["sent_at"] is None

    def test_200_iso_week(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            # ISO week 19 of 2026 starts on 2026-05-04
            _seed_digest(
                session,
                project_id="proj-1",
                week_start=date(2026, 5, 4),
                summary={"calls": 99},
            )
        response = client.get(
            "/v1/digest/2026-W19", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        assert response.json()["week_start"] == "2026-05-04"

    def test_422_non_monday(self, client: TestClient) -> None:
        # 2026-05-14 is a Thursday
        response = client.get(
            "/v1/digest/2026-05-14", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 422
        assert "Monday" in response.json()["detail"]

    def test_422_garbage(self, client: TestClient) -> None:
        response = client.get(
            "/v1/digest/not-a-date", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 422

    def test_422_iso_week_out_of_range(self, client: TestClient) -> None:
        response = client.get(
            "/v1/digest/2026-W99", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 422

    def test_404_cross_tenant(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_digest(
                session,
                project_id="proj-A",
                week_start=date(2026, 5, 11),
                summary={"calls": 1},
            )
        response = client.get(
            "/v1/digest/2026-05-11", headers={PROJECT_HEADER: "proj-B"}
        )
        assert response.status_code == 404


# ── route: GET /v1/digest (list) ─────────────────────────────────────────────


class TestListDigestsRoute:
    def test_empty(self, client: TestClient) -> None:
        response = client.get(
            "/v1/digest", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["next_cursor"] is None
        assert body["total_in_page"] == 0

    def test_compact_shape_no_html_blob(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_digest(
                session,
                project_id="proj-1",
                week_start=date(2026, 5, 11),
                summary={"calls": 100},
                html_blob="<html>HUGE</html>",
            )
        response = client.get(
            "/v1/digest", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        # Compact shape: no html_blob, no summary
        assert "html_blob" not in items[0]
        assert "summary" not in items[0]
        assert items[0]["week_start"] == "2026-05-11"

    def test_newest_first(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            for week in [date(2026, 4, 27), date(2026, 5, 11), date(2026, 5, 4)]:
                _seed_digest(session, project_id="proj-1", week_start=week)

        response = client.get(
            "/v1/digest", headers={PROJECT_HEADER: "proj-1"}
        )
        weeks = [i["week_start"] for i in response.json()["items"]]
        assert weeks == ["2026-05-11", "2026-05-04", "2026-04-27"]

    def test_pagination_via_cursor(self, client: TestClient) -> None:
        from datetime import timedelta

        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            # 5 consecutive Mondays starting 2026-04-06
            base = date(2026, 4, 6)
            for n in range(5):
                _seed_digest(
                    session,
                    project_id="proj-1",
                    week_start=base + timedelta(weeks=n),
                )

        first = client.get(
            "/v1/digest?limit=2", headers={PROJECT_HEADER: "proj-1"}
        ).json()
        assert len(first["items"]) == 2
        assert first["next_cursor"] is not None

        second = client.get(
            f"/v1/digest?limit=2&cursor={first['next_cursor']}",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        assert len(second["items"]) == 2

        third = client.get(
            f"/v1/digest?limit=2&cursor={second['next_cursor']}",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        assert len(third["items"]) == 1
        assert third["next_cursor"] is None

        seen = (
            [i["week_start"] for i in first["items"]]
            + [i["week_start"] for i in second["items"]]
            + [i["week_start"] for i in third["items"]]
        )
        assert len(set(seen)) == 5

    def test_cursor_invalid_422(self, client: TestClient) -> None:
        response = client.get(
            "/v1/digest?cursor=not-a-date",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_tenant_isolation(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_digest(
                session, project_id="proj-A", week_start=date(2026, 5, 11)
            )
            _seed_digest(
                session, project_id="proj-B", week_start=date(2026, 5, 11)
            )

        response = client.get(
            "/v1/digest", headers={PROJECT_HEADER: "proj-A"}
        )
        items = response.json()["items"]
        assert {i["project_id"] for i in items} == {"proj-A"}

    def test_limit_bounds_check(self, client: TestClient) -> None:
        # FastAPI Query(le=100, ge=1) — fast-fail on out-of-range
        response = client.get(
            "/v1/digest?limit=0",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422
        response = client.get(
            "/v1/digest?limit=101",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422
