from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.services.outcome_reconciliation import (
    ApiRecordConnector,
    list_pending_reconciliations_due,
    reconcile_outcome,
    sweep_pending_reconciliation_checks,
    verification_status_for_check,
)
from app.services.proof_connector_manifest import (
    PROOF_MATCHED,
    PROOF_MISMATCHED,
    PROOF_PARTIAL,
    PROOF_PENDING,
    PROOF_UNVERIFIABLE,
    evaluate_proof_manifest,
    proof_coverage_summary,
    proof_status_to_outcome_verdict,
    public_manifest_summary,
)


def _manifest(*, action_time: datetime) -> dict[str, object]:
    return {
        "schema_version": "zroky.proof_connector.v0",
        "connector_type": "generic_rest_api",
        "capability": "user.deactivation.proof",
        "tier": "declarative",
        "match_fields": ["user_id", "status"],
        "temporal": {
            "action_time": action_time.isoformat(),
            "observed_at_field": "updated_at",
            "window_seconds": 60,
        },
        "causal": {
            "actor_field": "updated_by",
            "expected_actor": "zroky-runner",
            "correlation_field": "request_id",
            "expected_correlation_claim_field": "correlation_id",
        },
        "poll": {"interval_seconds": 15},
    }


def test_proof_manifest_requires_temporal_and_causal_match() -> None:
    action_time = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    evaluation = evaluate_proof_manifest(
        claimed={
            "user_id": "usr_123",
            "status": "deactivated",
            "correlation_id": "req_abc",
        },
        actual={
            "user_id": "usr_123",
            "status": "deactivated",
            "updated_at": (action_time + timedelta(seconds=3)).isoformat(),
            "updated_by": "zroky-runner",
            "request_id": "req_abc",
        },
        actual_record_found=True,
        manifest=_manifest(action_time=action_time),
        checked_at=action_time + timedelta(seconds=5),
    )

    assert evaluation.status == PROOF_MATCHED
    assert evaluation.reason == "temporal_causal_match"
    assert proof_status_to_outcome_verdict(evaluation.status) == "matched"


def test_proof_manifest_marks_causal_mismatch_as_mismatched() -> None:
    action_time = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    evaluation = evaluate_proof_manifest(
        claimed={
            "user_id": "usr_123",
            "status": "deactivated",
            "correlation_id": "req_abc",
        },
        actual={
            "user_id": "usr_123",
            "status": "deactivated",
            "updated_at": (action_time + timedelta(seconds=2)).isoformat(),
            "updated_by": "human-admin",
            "request_id": "req_abc",
        },
        actual_record_found=True,
        manifest=_manifest(action_time=action_time),
        checked_at=action_time + timedelta(seconds=5),
    )

    assert evaluation.status == PROOF_MISMATCHED
    assert evaluation.reason == "causal_mismatch"
    assert proof_status_to_outcome_verdict(evaluation.status) == "mismatched"


def test_proof_manifest_distinguishes_partial_from_full_mismatch() -> None:
    action_time = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    evaluation = evaluate_proof_manifest(
        claimed={
            "user_id": "usr_123",
            "status": "deactivated",
            "correlation_id": "req_abc",
        },
        actual={
            "user_id": "usr_123",
            "status": "active",
            "updated_at": (action_time + timedelta(seconds=2)).isoformat(),
            "updated_by": "zroky-runner",
            "request_id": "req_abc",
        },
        actual_record_found=True,
        manifest=_manifest(action_time=action_time),
        checked_at=action_time + timedelta(seconds=5),
    )

    assert evaluation.status == PROOF_PARTIAL
    assert evaluation.reason == "partial_evidence"
    assert evaluation.mismatches[0]["field"] == "status"
    assert proof_status_to_outcome_verdict(evaluation.status) == "mismatched"


def test_proof_manifest_does_not_pass_when_temporal_evidence_is_missing() -> None:
    action_time = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    evaluation = evaluate_proof_manifest(
        claimed={
            "user_id": "usr_123",
            "status": "deactivated",
            "correlation_id": "req_abc",
        },
        actual={
            "user_id": "usr_123",
            "status": "deactivated",
            "updated_by": "zroky-runner",
            "request_id": "req_abc",
        },
        actual_record_found=True,
        manifest=_manifest(action_time=action_time),
        checked_at=action_time + timedelta(seconds=5),
    )

    assert evaluation.status == PROOF_PARTIAL
    assert "updated_at" in evaluation.missing_fields


def test_proof_manifest_keeps_missing_record_pending_inside_window() -> None:
    action_time = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    evaluation = evaluate_proof_manifest(
        claimed={"user_id": "usr_123", "status": "deactivated"},
        actual=None,
        actual_record_found=False,
        manifest=_manifest(action_time=action_time),
        checked_at=action_time + timedelta(seconds=20),
    )

    assert evaluation.status == PROOF_PENDING
    assert evaluation.reason == "verification_window_open"
    assert evaluation.deadline_at == action_time + timedelta(seconds=60)
    assert evaluation.next_check_at == action_time + timedelta(seconds=35)


def test_proof_manifest_marks_missing_record_after_window_as_mismatch() -> None:
    action_time = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    evaluation = evaluate_proof_manifest(
        claimed={"user_id": "usr_123", "status": "deactivated"},
        actual=None,
        actual_record_found=False,
        manifest=_manifest(action_time=action_time),
        checked_at=action_time + timedelta(seconds=90),
    )

    assert evaluation.status == PROOF_MISMATCHED
    assert evaluation.reason == "no_sor_trace"


def test_proof_manifest_marks_connector_outage_as_pending_or_unverifiable() -> None:
    action_time = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)

    pending = evaluate_proof_manifest(
        claimed={"user_id": "usr_123", "status": "deactivated"},
        actual=None,
        actual_record_found=None,
        manifest=_manifest(action_time=action_time),
        connector_metadata={"http_status": 503},
        checked_at=action_time + timedelta(seconds=90),
    )
    assert pending.status == PROOF_PENDING
    assert pending.reason == "sor_unreachable"
    assert pending.deadline_at == action_time + timedelta(seconds=60)
    assert pending.next_check_at == action_time + timedelta(seconds=60)

    unverifiable = evaluate_proof_manifest(
        claimed={"user_id": "usr_123", "status": "deactivated"},
        actual=None,
        actual_record_found=None,
        manifest=_manifest(action_time=action_time),
        connector_metadata={"http_status": 403, "retryable": False},
        checked_at=action_time + timedelta(seconds=90),
    )
    assert unverifiable.status == PROOF_UNVERIFIABLE


def test_public_manifest_summary_excludes_runtime_secrets() -> None:
    action_time = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    manifest = {
        **_manifest(action_time=action_time),
        "auth": {"type": "bearer", "secret_ref": "customer-secret-ref"},
    }

    summary = public_manifest_summary(manifest)

    assert summary["capability"] == "user.deactivation.proof"
    assert summary["has_temporal_rule"] is True
    assert summary["has_causal_rule"] is True
    assert "auth" not in summary
    assert "secret_ref" not in json.dumps(summary)


def test_proof_coverage_summary_tracks_market_dashboard_metric() -> None:
    summary = proof_coverage_summary(
        [
            PROOF_MATCHED,
            PROOF_MATCHED,
            PROOF_PARTIAL,
            PROOF_MISMATCHED,
            PROOF_PENDING,
            PROOF_UNVERIFIABLE,
        ]
    )

    assert summary.total == 6
    assert summary.sor_matched == 2
    assert summary.covered == 4
    assert summary.coverage_percent == 33.33
    assert summary.evidence_coverage_percent == 66.67


def test_reconcile_outcome_stores_proof_status_in_existing_row(tmp_path) -> None:
    project_id = "proj_proof_manifest_reconcile"
    action_time = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'proof_manifest.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        with SessionLocal() as session:
            row = reconcile_outcome(
                session,
                project_id=project_id,
                claimed={
                    "user_id": "usr_123",
                    "status": "deactivated",
                    "correlation_id": "req_abc",
                },
                connector=ApiRecordConnector(
                    record={
                        "user_id": "usr_123",
                        "status": "deactivated",
                        "updated_at": (action_time + timedelta(seconds=5)).isoformat(),
                        "updated_by": "zroky-runner",
                        "request_id": "req_abc",
                    },
                    record_found=True,
                    connector_type="generic_rest_api",
                ),
                action_type="identity.user.disable",
                match_fields=["user_id", "status"],
                proof_manifest=_manifest(action_time=action_time),
                checked_at=action_time + timedelta(seconds=10),
            )

            assert row.verdict == "matched"
            assert row.proof_status == PROOF_MATCHED
            assert row.proof_reason_code == "temporal_causal_match"
            assert row.proof_observed_at == action_time + timedelta(seconds=5)
            assert row.proof_deadline_at == action_time + timedelta(seconds=60)
            assert row.proof_next_check_at is None
            assert verification_status_for_check(row) == PROOF_MATCHED
            metadata = json.loads(row.metadata_json)
            assert metadata["proof"]["status"] == PROOF_MATCHED
            assert metadata["proof"]["point_in_time"] is True
            assert metadata["proof_manifest"]["capability"] == "user.deactivation.proof"
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_pending_proof_rows_are_queryable_and_expire_bounded(tmp_path) -> None:
    project_id = "proj_proof_pending_sweep"
    action_time = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'proof_pending.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        with SessionLocal() as session:
            due_row = reconcile_outcome(
                session,
                project_id=project_id,
                claimed={"user_id": "usr_123", "status": "deactivated"},
                connector=ApiRecordConnector(
                    record=None,
                    record_found=False,
                    connector_type="generic_rest_api",
                ),
                proof_manifest=_manifest(action_time=action_time),
                checked_at=action_time + timedelta(seconds=20),
                idempotency_key="proof-pending-due",
            )
            not_due_row = reconcile_outcome(
                session,
                project_id=project_id,
                claimed={"user_id": "usr_456", "status": "deactivated"},
                connector=ApiRecordConnector(
                    record=None,
                    record_found=False,
                    connector_type="generic_rest_api",
                ),
                proof_manifest=_manifest(action_time=action_time),
                checked_at=action_time + timedelta(seconds=30),
                idempotency_key="proof-pending-not-due",
            )

            assert due_row.proof_status == PROOF_PENDING
            assert due_row.proof_reason_code == "verification_window_open"
            assert due_row.proof_next_check_at == action_time + timedelta(seconds=35)
            assert not_due_row.proof_next_check_at == action_time + timedelta(seconds=45)

            due = list_pending_reconciliations_due(
                session,
                project_id=project_id,
                now=action_time + timedelta(seconds=36),
            )
            assert [row.id for row in due] == [due_row.id]

            result = sweep_pending_reconciliation_checks(
                session,
                project_id=project_id,
                now=action_time + timedelta(seconds=70),
            )
            assert set(result.expired_check_ids) == {due_row.id, not_due_row.id}
            assert result.expired == 2
            assert result.due_for_reverify == 0

            refreshed = {
                row.id: row
                for row in session.query(type(due_row))
                .filter(type(due_row).project_id == project_id)
                .all()
            }
            assert refreshed[due_row.id].proof_status == PROOF_MISMATCHED
            assert refreshed[due_row.id].verdict == "mismatched"
            assert refreshed[due_row.id].proof_next_check_at is None
            assert json.loads(refreshed[due_row.id].metadata_json)["proof"]["resolved_at"]
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
