import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Call, DiagnosisJob, FixEvent
from app.services.fix_adoption import (
    calibrate_resolved_fix_confidence,
    evaluate_fix_regressions,
    get_fix_adoption_rate,
    get_fix_adoption_rate_by_priority,
    get_fix_success_rate,
    get_fix_success_rate_by_tag,
    get_pr_conversion_rate,
    mark_resolved_if_no_recurrence,
    record_fix_event,
)


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def _add_source_job(db, *, project_id: str, diagnosis_id: str, category: str) -> None:
    db.add(
        DiagnosisJob(
            tenant_id=project_id,
            diagnosis_id=diagnosis_id,
            status="done",
            result_json=json.dumps({"diagnoses": [{"category": category}]}),
            payload_json="{}",
        )
    )
    db.commit()


def _add_call_with_job(
    db,
    *,
    project_id: str,
    call_id: str,
    created_at: datetime,
    category: str | None = None,
) -> None:
    db.add(
        Call(
            id=call_id,
            project_id=project_id,
            event_id=f"event-{call_id}",
            provider="openai",
            model="gpt-test",
            status="success",
            created_at=created_at,
            payload_json="{}",
        )
    )
    result_payload = {"diagnoses": []}
    if category is not None:
        result_payload = {"diagnoses": [{"category": category}]}
    db.add(
        DiagnosisJob(
            tenant_id=project_id,
            diagnosis_id=call_id,
            call_id=call_id,
            status="done",
            created_at=created_at,
            result_json=json.dumps(result_payload),
            payload_json="{}",
        )
    )
    db.commit()


def _record_fix_progression(
    db,
    *,
    project_id: str,
    diagnosis_id: str,
    fix_id: str,
    base_time: datetime,
    through: str = "pr_merged",
) -> dict[str, FixEvent]:
    events: dict[str, FixEvent] = {}
    if through == "pr_merged":
        sequence = ["shown", "copied", "pr_generated", "pr_merged"]
    else:
        sequence = ["shown", "copied", "pr_generated", "applied", "resolved"]
    for index, event_type in enumerate(sequence):
        events[event_type] = record_fix_event(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id=fix_id,
            event_type=event_type,
            source="system" if event_type == "resolved" else "dashboard",
            timestamp=base_time + timedelta(minutes=index),
        )
        if event_type == through:
            break
    return events


def test_record_fix_event_persists_metadata() -> None:
    db = _session()
    try:
        event = record_fix_event(
            db,
            project_id="project-1",
            diagnosis_id="diag-1",
            fix_id="fix-token-diag-1",
            event_type="shown",
            metadata={"surface": "dashboard"},
        )

        assert event.project_id == "project-1"
        assert event.event_type == "shown"
        assert event.source == "dashboard"
        assert event.idempotency_key.startswith("auto:diag-1:fix-token-diag-1:shown:")
        assert len(event.timestamp_bucket) == 12
        assert json.loads(event.metadata_json) == {"source": "dashboard", "surface": "dashboard"}
    finally:
        db.close()


def test_record_fix_event_dedupes_client_retries() -> None:
    db = _session()
    try:
        record_fix_event(
            db,
            project_id="project-1",
            diagnosis_id="diag-1",
            fix_id="fix-token-diag-1",
            event_type="shown",
        )
        first = record_fix_event(
            db,
            project_id="project-1",
            diagnosis_id="diag-1",
            fix_id="fix-token-diag-1",
            event_type="copied",
            idempotency_key="copy-event-1",
            metadata={"attempt": 1},
        )
        second = record_fix_event(
            db,
            project_id="project-1",
            diagnosis_id="diag-1",
            fix_id="fix-token-diag-1",
            event_type="copied",
            idempotency_key="copy-event-1",
            metadata={"attempt": 2},
        )

        assert second.id == first.id
        assert db.query(FixEvent).filter(FixEvent.event_type == "copied").count() == 1
        assert json.loads(second.metadata_json) == {"attempt": 1, "source": "dashboard"}
    finally:
        db.close()


def test_state_machine_rejects_invalid_jumps() -> None:
    db = _session()
    try:
        record_fix_event(
            db,
            project_id="project-1",
            diagnosis_id="diag-1",
            fix_id="fix-token-diag-1",
            event_type="shown",
        )

        try:
            record_fix_event(
                db,
                project_id="project-1",
                diagnosis_id="diag-1",
                fix_id="fix-token-diag-1",
                event_type="pr_generated",
            )
        except ValueError as exc:
            assert "requires prior copied" in str(exc)
        else:
            raise AssertionError("Expected invalid fix transition to be rejected")
    finally:
        db.close()


def test_record_fix_event_dedupes_server_timestamp_bucket_retries() -> None:
    db = _session()
    try:
        event_time = datetime(2026, 4, 26, 12, 1, 30, tzinfo=timezone.utc)
        first = record_fix_event(
            db,
            project_id="project-1",
            diagnosis_id="diag-1",
            fix_id="fix-token-diag-1",
            event_type="shown",
            timestamp=event_time,
        )
        second = record_fix_event(
            db,
            project_id="project-1",
            diagnosis_id="diag-1",
            fix_id="fix-token-diag-1",
            event_type="shown",
            timestamp=event_time + timedelta(seconds=20),
        )

        assert second.id == first.id
        assert db.query(FixEvent).count() == 1
    finally:
        db.close()


def test_late_pr_merged_repairs_existing_resolution_correlation() -> None:
    db = _session()
    try:
        project_id = "project-1"
        diagnosis_id = "diag-token-1"
        fix_id = "fix-token_overflow-diag-token-1"
        base_time = datetime(2026, 4, 26, 12, tzinfo=timezone.utc)

        _record_fix_progression(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id=fix_id,
            base_time=base_time,
            through="applied",
        )
        resolved = record_fix_event(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id=fix_id,
            event_type="resolved",
            metadata={"resolution_correlation": "medium"},
            source="system",
            timestamp=base_time + timedelta(hours=2),
        )
        merged = record_fix_event(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id=fix_id,
            event_type="pr_merged",
            source="github_webhook",
            timestamp=base_time + timedelta(minutes=3, seconds=30),
        )

        db.refresh(resolved)
        resolved_metadata = json.loads(resolved.metadata_json)
        merged_metadata = json.loads(merged.metadata_json)
        assert merged.source == "github_webhook"
        assert merged_metadata["out_of_order"] is True
        assert resolved_metadata["resolution_correlation"] == "high"
        assert resolved_metadata["applied_signal"] == "pr_merged"
        assert resolved_metadata["late_signal_event_id"] == merged.id
    finally:
        db.close()


def test_resolution_marks_resolved_after_completed_window_without_recurrence() -> None:
    db = _session()
    try:
        project_id = "project-1"
        diagnosis_id = "diag-token-1"
        fix_id = "fix-token_overflow-diag-token-1"
        base_time = datetime(2026, 4, 26, 12, tzinfo=timezone.utc)
        _add_source_job(db, project_id=project_id, diagnosis_id=diagnosis_id, category="TOKEN_OVERFLOW")
        progression = _record_fix_progression(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id=fix_id,
            base_time=base_time,
            through="pr_merged",
        )

        for index in range(3):
            _add_call_with_job(
                db,
                project_id=project_id,
                call_id=f"call-{index}",
                created_at=base_time + timedelta(minutes=10 + index),
            )

        evaluation, resolved_event = mark_resolved_if_no_recurrence(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id=fix_id,
            since=progression["pr_merged"].timestamp,
            window_calls=3,
            window_hours=0,
            minimum_observations_threshold=1,
            correlation_signal="pr_merged",
            now=base_time + timedelta(hours=1),
        )

        assert evaluation.resolved is True
        assert evaluation.resolution_confidence == 0.85
        assert evaluation.resolution_correlation == "high"
        assert evaluation.attribution_mode == "single"
        assert evaluation.confidence_calibration == "initial_window"
        assert evaluation.resolution_window == "3_calls"
        assert resolved_event is not None
        assert resolved_event.event_type == "resolved"
        resolved_metadata = json.loads(resolved_event.metadata_json)
        assert resolved_metadata["target_categories"] == ["TOKEN_OVERFLOW"]
        assert resolved_metadata["resolution_correlation"] == "high"
        assert resolved_event.source == "system"
    finally:
        db.close()


def test_resolution_does_not_resolve_when_recurrence_is_seen() -> None:
    db = _session()
    try:
        project_id = "project-1"
        diagnosis_id = "diag-token-1"
        base_time = datetime(2026, 4, 26, 12, tzinfo=timezone.utc)
        _add_source_job(db, project_id=project_id, diagnosis_id=diagnosis_id, category="TOKEN_OVERFLOW")
        progression = _record_fix_progression(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id="fix-token_overflow-diag-token-1",
            base_time=base_time,
            through="pr_merged",
        )

        _add_call_with_job(
            db,
            project_id=project_id,
            call_id="call-1",
            created_at=base_time + timedelta(minutes=10),
            category="TOKEN_OVERFLOW",
        )
        _add_call_with_job(
            db,
            project_id=project_id,
            call_id="call-2",
            created_at=base_time + timedelta(minutes=11),
        )

        evaluation, resolved_event = mark_resolved_if_no_recurrence(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id="fix-token_overflow-diag-token-1",
            since=progression["pr_merged"].timestamp,
            window_calls=2,
            window_hours=0,
            minimum_observations_threshold=1,
            now=base_time + timedelta(hours=1),
        )

        assert evaluation.resolved is False
        assert evaluation.reason == "recurrence_detected"
        assert evaluation.recurrence_count == 1
        assert resolved_event is None
    finally:
        db.close()


def test_resolution_requires_call_and_time_windows() -> None:
    db = _session()
    try:
        project_id = "project-1"
        diagnosis_id = "diag-token-1"
        base_time = datetime(2026, 4, 26, 12, tzinfo=timezone.utc)
        _add_source_job(db, project_id=project_id, diagnosis_id=diagnosis_id, category="TOKEN_OVERFLOW")
        progression = _record_fix_progression(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id="fix-token_overflow-diag-token-1",
            base_time=base_time,
            through="pr_merged",
        )

        for index in range(3):
            _add_call_with_job(
                db,
                project_id=project_id,
                call_id=f"call-{index}",
                created_at=base_time + timedelta(minutes=10 + index),
            )

        evaluation, resolved_event = mark_resolved_if_no_recurrence(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id="fix-token_overflow-diag-token-1",
            since=progression["pr_merged"].timestamp,
            window_calls=3,
            window_hours=24,
            minimum_observations_threshold=1,
            correlation_signal="applied",
            now=base_time + timedelta(hours=1),
        )

        assert evaluation.resolved is False
        assert evaluation.reason == "insufficient_time_window"
        assert evaluation.resolution_window == "3_calls_and_24h"
        assert resolved_event is None
    finally:
        db.close()


def test_regression_detection_marks_regressed_after_cooldown() -> None:
    db = _session()
    try:
        project_id = "project-1"
        diagnosis_id = "diag-token-1"
        fix_id = "fix-token_overflow-diag-token-1"
        base_time = datetime(2026, 4, 26, 12, tzinfo=timezone.utc)
        _add_source_job(db, project_id=project_id, diagnosis_id=diagnosis_id, category="TOKEN_OVERFLOW")
        _record_fix_progression(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id=fix_id,
            base_time=base_time,
            through="resolved",
        )
        for index in range(10):
            _add_call_with_job(
                db,
                project_id=project_id,
                call_id=f"cooldown-call-{index}",
                created_at=base_time + timedelta(minutes=6 + index),
            )
        _add_call_with_job(
            db,
            project_id=project_id,
            call_id="regression-call",
            created_at=base_time + timedelta(minutes=16),
            category="TOKEN_OVERFLOW",
        )

        regressed_count = evaluate_fix_regressions(
            db,
            project_id=project_id,
            cooldown_calls=10,
            cooldown_minutes=10,
        )

        assert regressed_count == 1
        regression = db.query(FixEvent).filter(FixEvent.event_type == "regressed").one()
        regression_metadata = json.loads(regression.metadata_json)
        assert regression.source == "system"
        assert regression_metadata["recurrence_diagnosis_id"] == "regression-call"
        assert regression_metadata["regression_severity"] == "minor"
        assert regression_metadata["target_categories"] == ["TOKEN_OVERFLOW"]
    finally:
        db.close()


def test_resolution_attribution_becomes_multi_when_multiple_fixes_apply() -> None:
    db = _session()
    try:
        project_id = "project-1"
        diagnosis_id = "diag-token-1"
        base_time = datetime(2026, 4, 26, 12, tzinfo=timezone.utc)
        _add_source_job(db, project_id=project_id, diagnosis_id=diagnosis_id, category="TOKEN_OVERFLOW")
        first = _record_fix_progression(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id="fix-1",
            base_time=base_time,
            through="pr_merged",
        )
        _record_fix_progression(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id="fix-2",
            base_time=base_time + timedelta(minutes=10),
            through="pr_merged",
        )

        for index in range(3):
            _add_call_with_job(
                db,
                project_id=project_id,
                call_id=f"post-fix-call-{index}",
                created_at=base_time + timedelta(hours=1, minutes=index),
            )

        evaluation, _ = mark_resolved_if_no_recurrence(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id="fix-1",
            since=first["pr_merged"].timestamp,
            window_calls=3,
            window_hours=0,
            minimum_observations_threshold=1,
            correlation_signal="pr_merged",
            now=base_time + timedelta(hours=2),
        )

        assert evaluation.resolved is True
        assert evaluation.attribution_mode == "multi"
    finally:
        db.close()


def test_resolution_confidence_calibration_rises_after_stable_time() -> None:
    db = _session()
    try:
        project_id = "project-1"
        diagnosis_id = "diag-token-1"
        fix_id = "fix-token_overflow-diag-token-1"
        base_time = datetime(2026, 4, 1, 12, tzinfo=timezone.utc)
        _record_fix_progression(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id=fix_id,
            base_time=base_time,
            through="resolved",
        )

        updated = calibrate_resolved_fix_confidence(
            db,
            project_id=project_id,
            now=base_time + timedelta(days=8),
        )

        assert updated == 1
        resolved = db.query(FixEvent).filter(FixEvent.event_type == "resolved").one()
        metadata = json.loads(resolved.metadata_json)
        assert metadata["resolution_confidence"] == 0.97
        assert metadata["resolution_correlation"] == "high"
        assert metadata["confidence_calibration"] == "stable_7d"
    finally:
        db.close()


def test_metrics_rates_use_distinct_fix_ids() -> None:
    db = _session()
    try:
        for fix_id in ("fix-1", "fix-2"):
            record_fix_event(
                db,
                project_id="project-1",
                diagnosis_id=f"diag-{fix_id}",
                fix_id=fix_id,
                event_type="shown",
                metadata={
                    "fix_tags": ["token", "prompt"] if fix_id == "fix-1" else ["loop"],
                    "recommended_priority": "P0" if fix_id == "fix-1" else "P1",
                },
            )

        record_fix_event(
            db,
            project_id="project-1",
            diagnosis_id="diag-fix-1",
            fix_id="fix-1",
            event_type="copied",
        )
        record_fix_event(
            db,
            project_id="project-1",
            diagnosis_id="diag-fix-1",
            fix_id="fix-1",
            event_type="pr_generated",
        )
        record_fix_event(
            db,
            project_id="project-1",
            diagnosis_id="diag-fix-1",
            fix_id="fix-1",
            event_type="applied",
        )
        record_fix_event(
            db,
            project_id="project-1",
            diagnosis_id="diag-fix-1",
            fix_id="fix-1",
            event_type="resolved",
        )

        assert get_fix_adoption_rate(db, project_id="project-1") == {
            "numerator": 1,
            "denominator": 2,
            "rate": 0.5,
        }
        assert get_pr_conversion_rate(db, project_id="project-1") == {
            "numerator": 1,
            "denominator": 2,
            "rate": 0.5,
        }
        assert get_fix_success_rate(db, project_id="project-1") == {
            "numerator": 1,
            "denominator": 1,
            "rate": 1.0,
        }
        assert get_fix_success_rate_by_tag(db, project_id="project-1") == {
            "prompt": {"numerator": 1, "denominator": 1, "rate": 1.0},
            "token": {"numerator": 1, "denominator": 1, "rate": 1.0},
        }
        assert get_fix_adoption_rate_by_priority(db, project_id="project-1") == {
            "P0": {"numerator": 1, "denominator": 1, "rate": 1.0},
            "P1": {"numerator": 0, "denominator": 1, "rate": 0.0},
        }
    finally:
        db.close()
