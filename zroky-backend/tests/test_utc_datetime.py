"""Tests for UTCDateTime SQLAlchemy column type — fixes the SQLite tz bug."""
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test_utc_datetime.db")
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-utc-datetime")

from sqlalchemy import select

from app.db.base import Base
from app.db.models import AuditLog
from app.db.session import SessionLocal, engine


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def session():
    with SessionLocal() as s:
        yield s
        s.rollback()


def _make_log(session, *, created_at: datetime | None = None) -> AuditLog:
    log = AuditLog(
        tenant_id="t1",
        diagnosis_id="d1",
        action="test",
        actor_subject="actor",
    )
    if created_at is not None:
        log.created_at = created_at
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


def test_aware_datetime_round_trip(session):
    """An aware UTC datetime should round-trip unchanged."""
    when = datetime(2026, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
    log = _make_log(session, created_at=when)

    assert log.created_at == when
    assert log.created_at.tzinfo is not None
    assert log.created_at.utcoffset() == timedelta(0)


def test_aware_non_utc_datetime_is_converted_to_utc(session):
    """Non-UTC tz inputs should be converted to UTC before storage."""
    ist = timezone(timedelta(hours=5, minutes=30))
    when_ist = datetime(2026, 1, 15, 18, 0, 45, tzinfo=ist)  # 12:30:45 UTC
    expected_utc = when_ist.astimezone(timezone.utc)

    log = _make_log(session, created_at=when_ist)
    session.expire_all()
    reloaded = session.execute(select(AuditLog).where(AuditLog.id == log.id)).scalar_one()

    assert reloaded.created_at == expected_utc
    assert reloaded.created_at.tzinfo is not None


def test_naive_datetime_is_treated_as_utc(session):
    """A naive datetime input should be treated as UTC, not silently corrupt data."""
    naive = datetime(2026, 1, 15, 12, 30, 45)  # no tzinfo
    log = _make_log(session, created_at=naive)
    session.expire_all()
    reloaded = session.execute(select(AuditLog).where(AuditLog.id == log.id)).scalar_one()

    assert reloaded.created_at.tzinfo is not None
    assert reloaded.created_at == naive.replace(tzinfo=timezone.utc)


def test_read_always_returns_aware_datetime(session):
    """Critical bug fix: reads must always be tz-aware regardless of backend."""
    log = _make_log(session)  # uses server_default (DB-generated)
    session.expire_all()
    reloaded = session.execute(select(AuditLog).where(AuditLog.id == log.id)).scalar_one()

    assert reloaded.created_at.tzinfo is not None, (
        "UTCDateTime column must return tz-aware datetimes; "
        "this is the SQLite timezone bug."
    )


def test_aware_datetime_arithmetic_works(session):
    """The original bug: comparing query results with aware now() raised TypeError."""
    log = _make_log(session)
    session.expire_all()
    reloaded = session.execute(select(AuditLog).where(AuditLog.id == log.id)).scalar_one()

    # This used to raise: "can't compare offset-naive and offset-aware datetimes"
    delta = datetime.now(timezone.utc) - reloaded.created_at
    assert isinstance(delta, timedelta)
    assert delta.total_seconds() >= 0


def test_filter_with_aware_datetime_does_not_crash(session):
    """Querying with an aware datetime threshold should work on SQLite."""
    log = _make_log(session)
    session.expire_all()

    threshold = datetime.now(timezone.utc) - timedelta(hours=1)
    rows = session.execute(
        select(AuditLog).where(AuditLog.created_at >= threshold)
    ).scalars().all()
    assert any(row.id == log.id for row in rows)


def test_none_value_handled(session):
    """None datetime values should remain None on round-trip."""
    log = AuditLog(
        tenant_id="t1",
        diagnosis_id="d1",
        action="test",
    )
    session.add(log)
    session.commit()
    # AuditLog.created_at is non-nullable, but other models have nullable datetimes;
    # verify the type itself handles None at the API level.
    from app.db.utc_datetime import UTCDateTime
    t = UTCDateTime()
    assert t.process_bind_param(None, engine.dialect) is None
    assert t.process_result_value(None, engine.dialect) is None
