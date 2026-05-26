import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Anomaly, Call, GoldenSet, GoldenTrace, ReplayJob, ReplayRun, ReplayRunTrace
from app.services.anomalies import VALID_DETECTORS, compute_fingerprint
from app.db.session import get_db_session, get_db_session_read
from app.main import app


PROJECT_HEADER = "X-Project-Id"


@pytest.fixture()
def client_ctx(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_product_issues.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_get_db_session():
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session

    with TestClient(app) as client:
        yield client, testing_session_local

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _seed_call(
    session,
    *,
    project_id: str,
    call_id: str,
    agent_name: str,
    prompt_fingerprint: str,
    prompt_version: str,
    workflow_name: str,
    trace_id: str,
    created_at: datetime,
) -> None:
    payload = {
        "trace_id": trace_id,
        "agent_name": agent_name,
        "prompt_fingerprint": prompt_fingerprint,
        "prompt_version": prompt_version,
        "workflow_name": workflow_name,
        "completion_tokens": 32,
    }
    session.add(
        Call(
            id=call_id,
            project_id=project_id,
            event_id=f"event-{call_id}",
            created_at=created_at,
            agent_name=agent_name,
            call_type="chat",
            provider="openai",
            model="gpt-4o-mini",
            status="success",
            latency_ms=412.0,
            input_tokens=120,
            output_tokens=32,
            reasoning_tokens=0,
            total_tokens=152,
            cost_total=0.021,
            reasoning_cost_total=0.0,
            cache_savings_total=0.0,
            cost_confidence="high",
            payload_json=json.dumps(payload, separators=(",", ":")),
            metadata_json=json.dumps(payload, separators=(",", ":")),
        )
    )


def _seed_issue(
    session,
    *,
    project_id: str,
    issue_id: str,
    failure_code: str,
    severity: str,
    occurrence_count: int,
    blast_radius_usd: float,
    sample_call_id: str | None,
    agent_name: str | None = "refund-agent",
    prompt_fingerprint: str | None = "fp-schema",
    evidence: dict | None = None,
    last_seen_delta: int = 0,
) -> None:
    now = datetime.now(timezone.utc) - timedelta(minutes=last_seen_delta)
    evidence_payload = dict(evidence or {})
    evidence_payload.update(
        {
            "failure_code": failure_code,
            "prompt_fingerprint": prompt_fingerprint,
            "agent_name": agent_name,
            "blast_radius_usd": blast_radius_usd,
            "legacy_issue": {
                "failure_code": failure_code,
                "prompt_fingerprint": prompt_fingerprint,
                "agent_name": agent_name,
                "sample_call_id": sample_call_id,
                "sample_diagnosis_id": f"diag-{issue_id}",
                "blast_radius_usd": blast_radius_usd,
                "sample_evidence_json": json.dumps(evidence or {}, separators=(",", ":")),
                "last_fix_id": None,
                "resolved_at": None,
                "resolution_source": None,
            },
        }
    )
    detector = failure_code if failure_code in VALID_DETECTORS else "UNKNOWN"
    session.add(
        Anomaly(
            id=issue_id,
            project_id=project_id,
            fingerprint=compute_fingerprint(
                detector=detector,
                prompt_fingerprint=prompt_fingerprint,
                agent_name=agent_name,
            ),
            detector=detector,
            status="open",
            severity=severity,
            occurrence_count=occurrence_count,
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now,
            sample_call_ids_json=json.dumps([sample_call_id]) if sample_call_id else None,
            evidence_json=json.dumps(evidence_payload, separators=(",", ":")),
            created_at=now - timedelta(hours=1),
            updated_at=now,
        )
    )


def test_issues_api_returns_top_five_product_problems(client_ctx) -> None:
    client, session_local = client_ctx
    project_id = "proj-product-issues"
    now = datetime.now(timezone.utc)

    with session_local() as session:
        _seed_call(
            session,
            project_id=project_id,
            call_id="call-schema",
            agent_name="refund-agent",
            prompt_fingerprint="fp-schema",
            prompt_version="support-v42",
            workflow_name="refund-resolution",
            trace_id="trace-schema",
            created_at=now,
        )
        session.add(
            ReplayJob(
                tenant_id=project_id,
                call_id="call-schema",
                status="pass",
                created_at=now,
            )
        )
        _seed_issue(
            session,
            project_id=project_id,
            issue_id="issue-schema",
            failure_code="SCHEMA_VIOLATION",
            severity="high",
            occurrence_count=7,
            blast_radius_usd=2.5,
            sample_call_id="call-schema",
            evidence={"summary": "JSON response missed required refund_reason field"},
        )
        _seed_issue(
            session,
            project_id=project_id,
            issue_id="issue-cost",
            failure_code="COST_SPIKE",
            severity="critical",
            occurrence_count=3,
            blast_radius_usd=40,
            sample_call_id=None,
            last_seen_delta=1,
        )
        _seed_issue(
            session,
            project_id=project_id,
            issue_id="issue-auth",
            failure_code="AUTH_FAILURE",
            severity="critical",
            occurrence_count=1,
            blast_radius_usd=0,
            sample_call_id=None,
            last_seen_delta=2,
        )
        _seed_issue(
            session,
            project_id=project_id,
            issue_id="issue-loop",
            failure_code="LOOP_DETECTED",
            severity="high",
            occurrence_count=12,
            blast_radius_usd=1,
            sample_call_id=None,
            last_seen_delta=3,
        )
        _seed_issue(
            session,
            project_id=project_id,
            issue_id="issue-rag",
            failure_code="RAG_RETRIEVAL_MISSING",
            severity="medium",
            occurrence_count=4,
            blast_radius_usd=0.5,
            sample_call_id=None,
            evidence={"missing_document": "policy docs"},
            last_seen_delta=4,
        )
        _seed_issue(
            session,
            project_id=project_id,
            issue_id="issue-empty-low",
            failure_code="EMPTY_OUTPUT",
            severity="low",
            occurrence_count=1,
            blast_radius_usd=0,
            sample_call_id=None,
            last_seen_delta=5,
        )
        session.commit()

    response = client.get("/v1/issues", headers={PROJECT_HEADER: project_id})
    assert response.status_code == 200
    payload = response.json()
    ids = [item["id"] for item in payload["items"]]

    assert len(ids) == 5
    assert "issue-empty-low" not in ids
    assert ids[0] == "issue-cost"

    schema_issue = next(item for item in payload["items"] if item["id"] == "issue-schema")
    assert schema_issue["title"] == "Prompt support-v42 increased schema failures"
    assert schema_issue["affected_agent"] == "refund-agent"
    assert schema_issue["affected_workflow"] == "refund-resolution"
    assert schema_issue["root_cause"] == "JSON response missed required refund_reason field"
    assert schema_issue["user_impact"] == "7 affected calls, $2.50 estimated wasted spend."
    assert schema_issue["replay_coverage_status"] == "covered_passed"
    assert "Use the covered replay trace" in schema_issue["recommended_next_action"]
    assert schema_issue["evidence_traces"][0]["call_id"] == "call-schema"
    assert schema_issue["evidence_traces"][0]["trace_id"] == "trace-schema"
    assert schema_issue["evidence_traces"][0]["prompt_version"] == "support-v42"

    rag_issue = next(item for item in payload["items"] if item["id"] == "issue-rag")
    assert rag_issue["title"] == "RAG retrieval is missing policy docs"


def test_issue_detail_keeps_same_product_projection(client_ctx) -> None:
    client, session_local = client_ctx
    project_id = "proj-issue-detail"

    with session_local() as session:
        _seed_issue(
            session,
            project_id=project_id,
            issue_id="issue-tool",
            failure_code="TOOL_SELECTION_WRONG",
            severity="high",
            occurrence_count=5,
            blast_radius_usd=1.25,
            sample_call_id=None,
            evidence={"summary": "refund lookup called before validating order id"},
        )
        session.commit()

    response = client.get("/v1/issues/issue-tool", headers={PROJECT_HEADER: project_id})
    assert response.status_code == 200
    body = response.json()

    assert body["title"] == "Refund agent is selecting the wrong tool"
    assert body["root_cause"] == "refund lookup called before validating order id"
    assert body["replay_coverage_status"] == "not_covered"
    assert body["evidence_traces"][0]["evidence_summary"] == "refund lookup called before validating order id"
    assert body["priority_score"] > 0


def test_issue_replay_coverage_is_mode_aware(client_ctx) -> None:
    client, session_local = client_ctx
    project_id = "proj-issue-replay-mode"
    now = datetime.now(timezone.utc)

    with session_local() as session:
        _seed_call(
            session,
            project_id=project_id,
            call_id="call-verified",
            agent_name="refund-agent",
            prompt_fingerprint="fp-schema",
            prompt_version="support-v42",
            workflow_name="refund-resolution",
            trace_id="trace-verified",
            created_at=now,
        )
        golden_set = GoldenSet(
            id="golden-set-verified",
            project_id=project_id,
            name="Verified issue set",
            created_at=now,
            updated_at=now,
        )
        golden_trace = GoldenTrace(
            id="golden-trace-verified",
            golden_set_id=golden_set.id,
            project_id=project_id,
            call_id="call-verified",
            expected_output_text="ok",
            created_at=now,
            updated_at=now,
        )
        replay_run = ReplayRun(
            id="replay-run-verified",
            project_id=project_id,
            golden_set_id=golden_set.id,
            trigger="manual",
            status="pass",
            summary_json=json.dumps(
                {
                    "replay_mode": "real_llm",
                    "requested_replay_mode": "mocked-tool",
                    "verified_fix": True,
                    "verification_status": "verified_fix",
                },
                separators=(",", ":"),
            ),
            created_at=now,
        )
        run_trace = ReplayRunTrace(
            id="replay-trace-verified",
            replay_run_id=replay_run.id,
            golden_trace_id=golden_trace.id,
            project_id=project_id,
            call_id_replayed="call-verified",
            status="pass",
            created_at=now,
        )
        session.add_all([golden_set, golden_trace, replay_run, run_trace])
        _seed_issue(
            session,
            project_id=project_id,
            issue_id="issue-verified",
            failure_code="SCHEMA_VIOLATION",
            severity="high",
            occurrence_count=3,
            blast_radius_usd=1.0,
            sample_call_id="call-verified",
        )
        session.commit()

    response = client.get("/v1/issues/issue-verified", headers={PROJECT_HEADER: project_id})
    assert response.status_code == 200
    body = response.json()
    assert body["replay_coverage_status"] == "verified_fix"
    assert "Use the covered replay trace" in body["recommended_next_action"]
