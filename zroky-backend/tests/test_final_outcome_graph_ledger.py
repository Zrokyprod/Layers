from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.db.base import Base
from app.db.models import FinalAssurancePack, FinalObservation, FinalOutcomeGraph, FinalWorkflowIntent
from app.db.session import get_db_session
from app.main import app
from app.services.final_outcome_graphs import apply_outcome_graph_ledger_state, recheck_due_outcome_graphs


@pytest.fixture()
def client():
    importlib.import_module("app.db.models")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[require_tenant_context] = lambda: TenantContext(
        tenant_id="proj_test",
        role="admin",
        subject="tester",
    )
    with TestClient(app) as test_client:
        test_client.session_local = session_local
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.parametrize(
    ("classification", "verification_status"),
    [
        ("verified", "verified"),
        ("wrong", "failed"),
        ("missing", "failed"),
        ("stale", "inconclusive"),
        ("duplicate", "failed"),
        ("conflicted", "inconclusive"),
        ("forbidden", "failed"),
        ("unknown", "inconclusive"),
    ],
)
def test_final_outcome_graph_persists_classification_columns(
    client: TestClient,
    classification: str,
    verification_status: str,
) -> None:
    with client.session_local() as session:
        intent = _intent()
        session.add(intent)
        row = FinalOutcomeGraph(
            project_id="proj_test",
            environment="production",
            intent_id=intent.id,
            graph_digest="digest",
            graph_json="{}",
        )
        graph = {"classification": classification, "observation_count": 1, "actual_effects": [{"matched": True}]}
        apply_outcome_graph_ledger_state(row, graph, verification_window_seconds=60)
        session.add(row)
        session.commit()
        session.refresh(row)

    assert row.classification == classification
    assert row.verification_status == verification_status
    assert row.last_checked_at is not None
    assert row.next_check_at is None if classification != "unknown" else row.next_check_at is not None


def test_final_outcome_graph_pending_sets_next_check(client: TestClient) -> None:
    with client.session_local() as session:
        intent = _intent()
        session.add(intent)
        row = FinalOutcomeGraph(
            project_id="proj_test",
            environment="production",
            intent_id=intent.id,
            graph_digest="digest",
            graph_json="{}",
        )
        apply_outcome_graph_ledger_state(row, {"observation_count": 0}, verification_window_seconds=60)
        session.add(row)
        session.commit()
        session.refresh(row)

    assert row.classification == "pending"
    assert row.verification_status == "pending"
    assert row.reason_code == "no_sor_trace"
    assert row.next_check_at is not None


def test_recheck_sweep_drains_pending_graph_to_verified(client: TestClient) -> None:
    now = datetime.now(timezone.utc)
    with client.session_local() as session:
        intent = _intent(intent_json={"refund_id": "rf_1"})
        pack = _pack()
        session.add_all([intent, pack])
        graph = {
            "workflow_key": "refund-workflow",
            "pack_version": "1.0.0",
            "intent_id": intent.id,
            "assurance_pack_id": pack.id,
            "observation_count": 0,
        }
        row = FinalOutcomeGraph(
            project_id="proj_test",
            environment="production",
            intent_id=intent.id,
            graph_digest="pending",
            graph_json=json.dumps(graph, separators=(",", ":")),
            classification="pending",
            verification_status="pending",
            next_check_at=now - timedelta(seconds=1),
        )
        observation = FinalObservation(
            project_id="proj_test",
            environment="production",
            intent_id=intent.id,
            source_kind="generic_rest",
            observed_object_ref="refund:rf_1",
            observation_digest="obs",
            observation_json=json.dumps(
                {
                    "observed_state": {"refund_id": "rf_1", "status": "posted"},
                    "provenance": {"source_binding": "ledger_refunds"},
                    "read_at": now.isoformat(),
                },
                separators=(",", ":"),
            ),
            observed_at=now,
        )
        session.add_all([row, observation])
        session.commit()

        result = recheck_due_outcome_graphs(
            session,
            now=now,
            verification_window_seconds=60,
        )
        session.refresh(row)

    assert result == {"checked": 1, "updated": 1}
    assert row.classification == "verified"
    assert row.verification_status == "verified"
    assert row.next_check_at is None


def test_outcome_graph_recheck_due_endpoint_drains_pending_graph(client: TestClient) -> None:
    now = datetime.now(timezone.utc)
    with client.session_local() as session:
        intent = _intent(intent_json={"refund_id": "rf_endpoint"})
        pack = _pack()
        session.add_all([intent, pack])
        row = FinalOutcomeGraph(
            project_id="proj_test",
            environment="production",
            intent_id=intent.id,
            graph_digest="pending-endpoint",
            graph_json=json.dumps(
                {
                    "workflow_key": "refund-workflow",
                    "pack_version": "1.0.0",
                    "intent_id": intent.id,
                    "assurance_pack_id": pack.id,
                    "observation_count": 0,
                },
                separators=(",", ":"),
            ),
            classification="pending",
            verification_status="pending",
            next_check_at=now - timedelta(seconds=1),
        )
        observation = FinalObservation(
            project_id="proj_test",
            environment="production",
            intent_id=intent.id,
            source_kind="generic_rest",
            observed_object_ref="refund:rf_endpoint",
            observation_digest="obs-endpoint",
            observation_json=json.dumps(
                {
                    "observed_state": {"refund_id": "rf_endpoint", "status": "posted"},
                    "provenance": {"source_binding": "ledger_refunds"},
                    "read_at": now.isoformat(),
                },
                separators=(",", ":"),
            ),
            observed_at=now,
        )
        session.add_all([row, observation])
        session.commit()

    triggered = client.post("/v1/outcome-graphs/recheck-due")
    assert triggered.status_code == 200, triggered.text
    assert triggered.json() == {"checked": 1, "updated": 1}


def test_outcome_graph_ledger_endpoints_filter_and_count_verified_only(client: TestClient) -> None:
    with client.session_local() as session:
        intent = _intent()
        session.add(intent)
        for classification in ("verified", "pending", "unknown", "wrong"):
            row = FinalOutcomeGraph(
                project_id="proj_test",
                environment="production",
                intent_id=intent.id,
                graph_digest=f"digest-{classification}",
                graph_json=json.dumps({"classification": classification, "observation_count": 1}),
            )
            apply_outcome_graph_ledger_state(
                row,
                {"classification": classification, "observation_count": 1},
                verification_window_seconds=60,
            )
            session.add(row)
        session.commit()

    listed = client.get("/v1/outcome-graphs", params={"classification": "wrong", "limit": 50})
    assert listed.status_code == 200, listed.text
    assert [item["classification"] for item in listed.json()["items"]] == ["wrong"]

    summary = client.get("/v1/outcome-graphs/coverage-summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["counts"]["verified"] == 1
    assert body["counts"]["pending"] == 1
    assert body["counts"]["unknown"] == 1
    assert body["coverage_percent"] == 25.0


def _intent(*, intent_json: dict | None = None) -> FinalWorkflowIntent:
    return FinalWorkflowIntent(
        id=str(uuid4()),
        project_id="proj_test",
        environment="production",
        idempotency_key=str(uuid4()),
        intent_digest=str(uuid4()),
        intent_json=json.dumps(intent_json or {}, separators=(",", ":")),
    )


def _pack() -> FinalAssurancePack:
    pack = {
        "schema_version": "zroky.workflow_assurance_pack.v1",
        "workflow_key": "refund-workflow",
        "version": "1.0.0",
        "object_types": [{"key": "refund", "schema": {"type": "object"}}],
        "effects": [{"key": "refund_posted", "object_type": "refund", "predicate": "refund.status == 'posted'"}],
        "source_bindings": [
            {
                "key": "ledger_refunds",
                "connector_capability": "refund.read",
                "object_type": "refund",
                "freshness_seconds": 300,
            }
        ],
    }
    return FinalAssurancePack(
        id=str(uuid4()),
        project_id="proj_test",
        environment="production",
        workflow_key="refund-workflow",
        version="1.0.0",
        pack_digest=str(uuid4()),
        pack_json=json.dumps(pack, separators=(",", ":")),
        status="active",
    )
