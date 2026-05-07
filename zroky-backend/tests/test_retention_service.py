from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Call, DiagnosisFixWatch, DiagnosisJob, DiagnosisShareToken
from app.services.retention import (
    normalize_retention_days,
    purge_project_all_data,
    purge_project_retention_data,
)


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory(), engine


def _insert_call_and_job(
    db,
    *,
    tenant_id: str,
    call_id: str,
    created_at: datetime,
) -> None:
    db.add(
        Call(
            id=call_id,
            project_id=tenant_id,
            event_id=f"event-{call_id}",
            provider="openai",
            model="gpt-test",
            status="success",
            created_at=created_at,
            payload_json="{}",
        )
    )
    db.add(
        DiagnosisJob(
            tenant_id=tenant_id,
            diagnosis_id=call_id,
            call_id=call_id,
            status="done",
            created_at=created_at,
            payload_json="{}",
        )
    )
    db.commit()


def test_purge_project_retention_data_deletes_only_expired_rows() -> None:
    db, engine = _session()
    now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    try:
        _insert_call_and_job(
            db,
            tenant_id="proj-a",
            call_id="call-old-a",
            created_at=now - timedelta(days=40),
        )
        _insert_call_and_job(
            db,
            tenant_id="proj-a",
            call_id="call-new-a",
            created_at=now - timedelta(days=5),
        )
        _insert_call_and_job(
            db,
            tenant_id="proj-b",
            call_id="call-old-b",
            created_at=now - timedelta(days=50),
        )

        summary = purge_project_retention_data(
            session=db,
            tenant_id="proj-a",
            retention_days=30,
            now=now,
            batch_size=10,
            dry_run=False,
        )

        assert summary["total_deleted"] == 2
        assert summary["deleted_by_table"]["diagnosis_jobs"] == 1
        assert summary["deleted_by_table"]["calls"] == 1

        remaining_calls = set(db.execute(select(Call.id)).scalars().all())
        remaining_jobs = set(db.execute(select(DiagnosisJob.diagnosis_id)).scalars().all())

        assert "call-old-a" not in remaining_calls
        assert "call-old-a" not in remaining_jobs
        assert "call-new-a" in remaining_calls
        assert "call-new-a" in remaining_jobs
        assert "call-old-b" in remaining_calls
        assert "call-old-b" in remaining_jobs
    finally:
        db.close()
        engine.dispose()


def test_purge_project_retention_data_dry_run_reports_without_deleting() -> None:
    db, engine = _session()
    now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    try:
        _insert_call_and_job(
            db,
            tenant_id="proj-dry",
            call_id="call-old-dry",
            created_at=now - timedelta(days=45),
        )

        summary = purge_project_retention_data(
            session=db,
            tenant_id="proj-dry",
            retention_days=30,
            now=now,
            batch_size=10,
            dry_run=True,
        )

        assert summary["dry_run"] is True
        assert summary["total_deleted"] == 2
        assert summary["deleted_by_table"]["diagnosis_jobs"] == 1
        assert summary["deleted_by_table"]["calls"] == 1

        assert db.execute(select(Call).where(Call.id == "call-old-dry")).scalar_one_or_none() is not None
        assert (
            db.execute(
                select(DiagnosisJob).where(
                    DiagnosisJob.tenant_id == "proj-dry",
                    DiagnosisJob.diagnosis_id == "call-old-dry",
                )
            ).scalar_one_or_none()
            is not None
        )
    finally:
        db.close()
        engine.dispose()


def test_normalize_retention_days_clamps_invalid_values() -> None:
    assert normalize_retention_days(None) == 30
    assert normalize_retention_days(0) == 30
    assert normalize_retention_days(-10) == 30
    assert normalize_retention_days(14) == 14
    assert normalize_retention_days(999999) == 3650


def test_purge_project_all_data_deletes_all_rows_for_tenant() -> None:
    db, engine = _session()
    now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    try:
        _insert_call_and_job(
            db,
            tenant_id="proj-full",
            call_id="call-full-1",
            created_at=now - timedelta(days=1),
        )
        _insert_call_and_job(
            db,
            tenant_id="proj-other",
            call_id="call-other-1",
            created_at=now - timedelta(days=1),
        )

        db.add(
            DiagnosisShareToken(
                tenant_id="proj-full",
                diagnosis_id="diag-share-1",
                token_prefix="tok_full",
                token_hash="hash_full",
                expires_at=now + timedelta(days=7),
                created_at=now,
            )
        )
        db.commit()

        dry_run = purge_project_all_data(
            session=db,
            tenant_id="proj-full",
            batch_size=5,
            dry_run=True,
        )
        assert dry_run["dry_run"] is True
        assert dry_run["deleted_by_table"]["calls"] == 1
        assert dry_run["deleted_by_table"]["diagnosis_jobs"] == 1
        assert dry_run["deleted_by_table"]["diagnosis_share_tokens"] == 1
        assert dry_run["total_deleted"] == 3

        summary = purge_project_all_data(
            session=db,
            tenant_id="proj-full",
            batch_size=5,
            dry_run=False,
        )
        assert summary["dry_run"] is False
        assert summary["deleted_by_table"]["calls"] == 1
        assert summary["deleted_by_table"]["diagnosis_jobs"] == 1
        assert summary["deleted_by_table"]["diagnosis_share_tokens"] == 1
        assert summary["total_deleted"] == 3

        assert db.execute(select(Call).where(Call.project_id == "proj-full")).scalars().all() == []
        assert db.execute(select(DiagnosisJob).where(DiagnosisJob.tenant_id == "proj-full")).scalars().all() == []
        assert (
            db.execute(select(DiagnosisShareToken).where(DiagnosisShareToken.tenant_id == "proj-full"))
            .scalars()
            .all()
            == []
        )

        assert db.execute(select(Call).where(Call.project_id == "proj-other")).scalars().all() != []
    finally:
        db.close()
        engine.dispose()


def test_purge_project_retention_data_uses_expiry_for_tokens_and_watches() -> None:
    db, engine = _session()
    now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    try:
        db.add(
            DiagnosisShareToken(
                tenant_id="proj-exp",
                diagnosis_id="diag-token-future",
                token_prefix="tok_future",
                token_hash="hash_future",
                expires_at=now + timedelta(days=2),
                created_at=now - timedelta(days=90),
            )
        )
        db.add(
            DiagnosisShareToken(
                tenant_id="proj-exp",
                diagnosis_id="diag-token-expired",
                token_prefix="tok_expired",
                token_hash="hash_expired",
                expires_at=now - timedelta(days=45),
                created_at=now - timedelta(days=90),
            )
        )
        db.add(
            DiagnosisFixWatch(
                tenant_id="proj-exp",
                diagnosis_id="diag-watch-future",
                target_categories_json="[]",
                resolved_at=now - timedelta(days=10),
                watch_expires_at=now + timedelta(days=2),
                created_at=now - timedelta(days=90),
            )
        )
        db.add(
            DiagnosisFixWatch(
                tenant_id="proj-exp",
                diagnosis_id="diag-watch-expired",
                target_categories_json="[]",
                resolved_at=now - timedelta(days=70),
                watch_expires_at=now - timedelta(days=45),
                created_at=now - timedelta(days=90),
            )
        )
        db.commit()

        summary = purge_project_retention_data(
            session=db,
            tenant_id="proj-exp",
            retention_days=30,
            now=now,
            batch_size=10,
            dry_run=False,
        )

        assert summary["deleted_by_table"]["diagnosis_share_tokens"] == 1
        assert summary["deleted_by_table"]["diagnosis_fix_watches"] == 1

        remaining_token_ids = set(
            db.execute(
                select(DiagnosisShareToken.diagnosis_id).where(DiagnosisShareToken.tenant_id == "proj-exp")
            ).scalars().all()
        )
        remaining_watch_ids = set(
            db.execute(
                select(DiagnosisFixWatch.diagnosis_id).where(DiagnosisFixWatch.tenant_id == "proj-exp")
            ).scalars().all()
        )

        assert "diag-token-future" in remaining_token_ids
        assert "diag-token-expired" not in remaining_token_ids
        assert "diag-watch-future" in remaining_watch_ids
        assert "diag-watch-expired" not in remaining_watch_ids
    finally:
        db.close()
        engine.dispose()
