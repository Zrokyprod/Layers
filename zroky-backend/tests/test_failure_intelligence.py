from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Anomaly, IssueOccurrence
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.detectors.rag_grounding_failure import detect_rag_grounding_failure
from app.services.detectors.task_outcome_failure import detect_task_outcome_failure
from app.services.detectors.tool_failures import (
    detect_tool_argument_mismatch,
    detect_tool_call_failure,
    detect_tool_selection_failure,
)
from app.services.detectors.unsafe_action import detect_unsafe_action
from app.services.issues import upsert_issue


PROJECT_HEADER = "X-Project-Id"


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_failure_intelligence.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client_ctx(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_failure_intelligence_api.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_get_db_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session
    with TestClient(app) as client:
        yield client, session_factory
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def test_phase5_detectors_emit_actionable_fields() -> None:
    cases = [
        detect_tool_selection_failure(
            {"expected_tool": "lookup_order", "tool_calls": [{"name": "refund_user"}]}
        ),
        detect_tool_call_failure(
            {"tool_calls": [{"name": "refund_user", "status": "failed", "error": "timeout"}]}
        ),
        detect_tool_argument_mismatch(
            {
                "required_tool_args": ["order_id"],
                "tool_calls": [{"name": "refund_user", "arguments": {"amount": 10}}],
            }
        ),
        detect_unsafe_action({"tool_calls": [{"name": "delete_customer_record"}]}),
        detect_task_outcome_failure(
            {"workflow_name": "refund", "business_outcome": {"success": False, "reason": "policy check missing"}}
        ),
        detect_rag_grounding_failure(
            {"final_answer": "Refund approved", "retrieval": {"documents": [], "required_document": "refund-policy"}}
        ),
    ]

    assert all(item is not None for item in cases)
    for item in cases:
        assert item is not None
        assert item["what_happened"]
        assert item["why_it_matters"]
        assert item["root_cause"]
        assert item["recommended_next_action"]
        assert item["grouping_signature"]
        assert item["severity_hint"] in {"medium", "high", "critical"}


def test_issue_grouping_collapses_many_traces_into_root_cause_groups(db_session) -> None:
    now = datetime.now(timezone.utc)
    signatures = [
        ("TOOL_CALL_FAILURE", "tool_call_failure:refund_user:timeout"),
        ("TOOL_ARGUMENT_MISMATCH", "tool_argument_mismatch:refund_user:missing-order-id"),
        ("RAG_GROUNDING_FAILURE", "rag_grounding_failure:required-refund-policy"),
    ]

    for index in range(500):
        failure_code, signature = signatures[index % len(signatures)]
        anomaly = upsert_issue(
            db_session,
            project_id="proj-fi",
            failure_code=failure_code,
            prompt_fingerprint="prompt-v9",
            agent_name="refund-agent",
            call_id=f"call-{index}",
            diagnosis_id=f"diag-{index}",
            occurred_at=now + timedelta(seconds=index),
            call_cost_usd=0.01,
            trace_id=f"trace-{index}",
            user_id=f"user-{index % 25}",
            fingerprint_extra=signature,
            evidence={
                "summary": signature,
                "what_happened": "grouped failure",
                "why_it_matters": "same root cause",
                "root_cause": signature,
                "recommended_next_action": "Replay grouped trace",
                "grouping_signature": signature,
                "suspected_introduced_version": "deployment_id:dep-42",
            },
        )
        assert anomaly is not None

    anomalies = db_session.execute(
        select(Anomaly).where(Anomaly.project_id == "proj-fi")
    ).scalars().all()
    occurrences = db_session.execute(
        select(IssueOccurrence).where(IssueOccurrence.project_id == "proj-fi")
    ).scalars().all()

    assert len(anomalies) == 3
    assert sum(row.occurrence_count for row in anomalies) == 500
    assert len(occurrences) == 500


def test_duplicate_occurrence_does_not_inflate_issue_count(db_session) -> None:
    now = datetime.now(timezone.utc)
    for _ in range(2):
        upsert_issue(
            db_session,
            project_id="proj-dupe",
            failure_code="TASK_OUTCOME_FAILURE",
            prompt_fingerprint="prompt-v1",
            agent_name="checkout-agent",
            call_id="call-1",
            diagnosis_id="diag-1",
            occurred_at=now,
            fingerprint_extra="task_outcome_failure:checkout:failed",
            evidence={"summary": "checkout failed"},
        )

    anomaly = db_session.execute(
        select(Anomaly).where(Anomaly.project_id == "proj-dupe")
    ).scalar_one()
    occurrences = db_session.execute(
        select(IssueOccurrence).where(IssueOccurrence.project_id == "proj-dupe")
    ).scalars().all()
    assert anomaly.occurrence_count == 1
    assert len(occurrences) == 1


def test_issues_api_projects_failure_intelligence_fields(client_ctx) -> None:
    client, session_factory = client_ctx
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        issue = upsert_issue(
            session,
            project_id="proj-fi-api",
            failure_code="UNSAFE_ACTION",
            prompt_fingerprint="prompt-v7",
            agent_name="refund-agent",
            call_id="call-unsafe",
            diagnosis_id="diag-unsafe",
            occurred_at=now,
            call_cost_usd=1.5,
            trace_id="trace-unsafe",
            user_id="user-1",
            fingerprint_extra="unsafe_action:refund_user:missing_policy",
            evidence={
                "summary": "refund tool executed without policy approval",
                "what_happened": "Unsafe refund action detected.",
                "why_it_matters": "Refunds must have policy proof before execution.",
                "root_cause": "No policy approval span was captured.",
                "recommended_next_action": "Add policy approval and replay.",
                "grouping_signature": "unsafe_action:refund_user:missing_policy",
                "severity_hint": "critical",
                "suspected_introduced_version": "code_sha:abc123",
            },
        )
        assert issue is not None

    response = client.get(f"/v1/issues/{issue.id}", headers={PROJECT_HEADER: "proj-fi-api"})
    assert response.status_code == 200
    body = response.json()
    assert body["failure_code"] == "UNSAFE_ACTION"
    assert body["what_happened"] == "Unsafe refund action detected."
    assert body["why_it_matters"] == "Refunds must have policy proof before execution."
    assert body["affected_trace_count"] == 1
    assert body["affected_user_count"] == 1
    assert body["suspected_introduced_version"] == "code_sha:abc123"
    assert body["blast_radius"]["affected_traces"] == 1
    assert body["recommended_next_action"] == "Add policy approval and replay."
