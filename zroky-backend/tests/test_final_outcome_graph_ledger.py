from __future__ import annotations

import importlib
import inspect
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import FinalAgentRun, FinalAssurancePack, FinalObservation, FinalOutcomeGraph, FinalOutcomeIncident, FinalSourceConnector, FinalWorkflowIntent
from app.db.session import get_db_session
from app.main import app
from app.services.action_receipts import action_receipt_public_key_payload
from app.services.dsse import verify_envelope
from app.services import final_observation_pull
from app.services.final_observation_pull import ObservationPullError
from app.services.final_outcome_graphs import (
    apply_outcome_graph_ledger_state,
    create_missing_outcome_graphs,
    recheck_backoff_seconds,
    recheck_due_outcome_graphs,
)


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


def test_missing_graph_sweep_backfills_linked_run_idempotently(client: TestClient) -> None:
    with client.session_local() as session:
        intent = _intent(intent_json={"refund_id": "rf_backfill"})
        pack = _pack()
        run = FinalAgentRun(
            project_id="proj_test",
            environment="production",
            idempotency_key="run-backfill",
            intent_id=intent.id,
            workflow_key=pack.workflow_key,
            status="succeeded",
            run_digest="run-digest",
            run_json="{}",
        )
        session.add_all([intent, pack, run])
        session.commit()
        run_id = run.id
        intent_id = intent.id

        first = create_missing_outcome_graphs(session, limit=100, verification_window_seconds=300)
        second = create_missing_outcome_graphs(session, limit=100, verification_window_seconds=300)
        graph = session.query(FinalOutcomeGraph).one()

    assert first == 1
    assert second == 0
    assert graph.idempotency_key == f"initial:{run_id}:{intent_id}"
    assert graph.classification == "pending"


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


def test_recheck_sweep_pulls_stripe_observation_and_verifies_without_client_push(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("STRIPE_KEY_PROJ_TEST", "sk_live_read_secret")

    def fake_stripe_get(secret: str, url: str, *, params: dict[str, str] | None = None, secret_ref: str) -> dict:
        assert secret == "sk_live_read_secret"
        assert secret_ref == "STRIPE_KEY_PROJ_TEST"
        assert url == "https://api.stripe.com/v1/refunds"
        assert params == {"charge": "ch_verified", "limit": "10"}
        return {
            "data": [
                {
                    "id": "rf_verified",
                    "charge": "ch_verified",
                    "amount": 450000,
                    "currency": "inr",
                    "status": "succeeded",
                    "created": int(now.timestamp()),
                }
            ]
        }

    monkeypatch.setattr(final_observation_pull, "_stripe_get_json", fake_stripe_get)
    with client.session_local() as session:
        intent = _intent(intent_json={"charge_id": "ch_verified", "amount_minor": 450000, "currency": "inr"})
        pack = _pack(
            capability="stripe_refund.read",
            predicate=(
                "refund.status == 'posted' and refund.amount_minor == intent.amount_minor and "
                "refund.currency == intent.currency and refund.charge_id == intent.charge_id"
            ),
        )
        session.add_all([intent, pack, _connector(capability="stripe_refund.read")])
        row = _pending_graph(intent, pack, now=now)
        session.add(row)
        session.commit()

        result = recheck_due_outcome_graphs(
            session,
            now=now,
            verification_window_seconds=300,
            observation_pull_max_per_sweep=50,
        )
        session.refresh(row)
        observations = session.query(FinalObservation).all()

    assert result == {"checked": 1, "updated": 1}
    assert row.classification == "verified"
    assert row.next_check_at is None
    assert observations[0].source_kind == "stripe_refund"
    payload = json.loads(observations[0].observation_json)
    assert payload["provenance"]["acquired_via"] == "server_pull"
    assert payload["observed_state"]["refund_id"] == "rf_verified"
    assert "sk_live_read_secret" not in observations[0].observation_json


def test_recheck_sweep_pulls_stripe_no_record_and_marks_missing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("STRIPE_KEY_PROJ_TEST", "sk_live_read_secret")
    monkeypatch.setattr(
        final_observation_pull,
        "_stripe_get_json",
        lambda *args, **kwargs: {"data": []},
    )
    with client.session_local() as session:
        intent = _intent(intent_json={"charge_id": "ch_missing"})
        pack = _pack(capability="stripe_refund.read")
        session.add_all([intent, pack, _connector(capability="stripe_refund.read")])
        row = _pending_graph(intent, pack, now=now)
        session.add(row)
        session.commit()

        recheck_due_outcome_graphs(
            session,
            now=now,
            verification_window_seconds=300,
            observation_pull_max_per_sweep=50,
        )
        session.refresh(row)
        observation = session.query(FinalObservation).one()
        incident = session.query(FinalOutcomeIncident).filter_by(outcome_graph_id=row.id).one()

    assert row.classification == "missing"
    assert row.verification_status == "failed"
    assert row.next_check_at is None
    assert incident.status == "open"
    assert json.loads(incident.incident_json)["deviation_type"] == "missing"
    assert json.loads(observation.observation_json)["observed_state"] is None


def test_recovery_recheck_replaces_fresh_missing_proof_and_resolves(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("STRIPE_KEY_PROJ_TEST", "sk_live_read_secret")
    responses = iter(
        [
            {"data": []},
            {
                "data": [
                    {
                        "id": "rf_recovered",
                        "charge": "ch_recovered",
                        "amount": 450000,
                        "currency": "inr",
                        "status": "succeeded",
                        "created": int(now.timestamp()),
                    }
                ]
            },
        ]
    )
    monkeypatch.setattr(final_observation_pull, "_stripe_get_json", lambda *args, **kwargs: next(responses))

    with client.session_local() as session:
        intent = _intent(intent_json={"charge_id": "ch_recovered"})
        pack = _pack(capability="stripe_refund.read")
        row = _pending_graph(intent, pack, now=now)
        session.add_all([intent, pack, _connector(capability="stripe_refund.read"), row])
        session.commit()

        recheck_due_outcome_graphs(session, now=now, verification_window_seconds=300)
        incident = session.query(FinalOutcomeIncident).filter_by(outcome_graph_id=row.id).one()
        assert row.classification == "missing"

        incident.status = "recovering"
        row.classification = "pending"
        row.verification_status = "pending"
        row.next_check_at = now
        session.commit()

        result = recheck_due_outcome_graphs(session, now=now, verification_window_seconds=300)
        session.refresh(row)
        session.refresh(incident)
        observations = session.query(FinalObservation).order_by(FinalObservation.created_at).all()

    assert result == {"checked": 1, "updated": 1}
    assert row.classification == "verified"
    assert incident.status == "resolved"
    assert len(observations) == 2
    assert len({item.observed_object_ref for item in observations}) == 1


def test_recheck_sweep_fetch_failure_sets_sor_unreachable_with_backoff(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("STRIPE_KEY_PROJ_TEST", "super-secret-value")

    def fail_fetch(*args, **kwargs):
        raise ObservationPullError("Stripe fetch failed for secret_ref STRIPE_KEY_PROJ_TEST: HTTP 500")

    monkeypatch.setattr(final_observation_pull, "_stripe_get_json", fail_fetch)
    with client.session_local() as session:
        intent = _intent(intent_json={"charge_id": "ch_fail"})
        pack = _pack(capability="stripe_refund.read")
        session.add_all([intent, pack, _connector(capability="stripe_refund.read")])
        row = _pending_graph(intent, pack, now=now)
        session.add(row)
        session.commit()

        recheck_due_outcome_graphs(
            session,
            now=now,
            verification_window_seconds=300,
            observation_pull_max_per_sweep=50,
        )
        session.refresh(row)

    assert row.classification == "pending"
    assert row.reason_code == "sor_unreachable"
    assert row.next_check_at == now + timedelta(seconds=60)
    assert "super-secret-value" not in row.graph_json


def test_recheck_sweep_without_connector_sets_no_connector(client: TestClient) -> None:
    now = datetime.now(timezone.utc)
    with client.session_local() as session:
        intent = _intent(intent_json={"charge_id": "ch_no_connector"})
        pack = _pack(capability="stripe_refund.read")
        session.add_all([intent, pack])
        row = _pending_graph(intent, pack, now=now)
        session.add(row)
        session.commit()

        recheck_due_outcome_graphs(
            session,
            now=now,
            verification_window_seconds=300,
            observation_pull_max_per_sweep=50,
        )
        session.refresh(row)

    assert row.classification == "pending"
    assert row.reason_code == "no_connector"
    assert row.next_check_at == now + timedelta(seconds=60)


def test_recheck_backoff_progression_is_exact() -> None:
    assert [recheck_backoff_seconds(attempt) for attempt in range(1, 6)] == [60, 300, 900, 3600, 21600]
    assert recheck_backoff_seconds(99) == 21600


def test_observation_puller_has_no_post_path() -> None:
    source = inspect.getsource(final_observation_pull)
    assert ".post(" not in source
    assert "httpx.post" not in source


def test_outcome_graph_recheck_due_endpoint_drains_pending_graph(client: TestClient) -> None:
    now = datetime.now(timezone.utc)
    other_tenant_graph_id = str(uuid4())
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
        other_tenant_row = FinalOutcomeGraph(
            id=other_tenant_graph_id,
            project_id="proj_other",
            environment="production",
            intent_id=intent.id,
            graph_digest="pending-other-tenant",
            graph_json=json.dumps({"observation_count": 0}, separators=(",", ":")),
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
        session.add_all([row, other_tenant_row, observation])
        session.commit()

    triggered = client.post("/v1/outcome-graphs/recheck-due")
    assert triggered.status_code == 200, triggered.text
    assert triggered.json() == {"checked": 1, "updated": 1}
    with client.session_local() as session:
        assert session.get(FinalOutcomeGraph, other_tenant_graph_id).classification == "pending"


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
    assert listed.json() | {"items": []} == {"items": [], "total": 1, "limit": 50, "offset": 0}

    first_page = client.get(
        "/v1/outcome-graphs",
        params={"classification": "wrong,verified", "limit": 1},
    )
    second_page = client.get(
        "/v1/outcome-graphs",
        params={"classification": "wrong,verified", "limit": 1, "offset": 1},
    )
    assert first_page.status_code == 200, first_page.text
    assert second_page.status_code == 200, second_page.text
    assert first_page.json()["total"] == second_page.json()["total"] == 2
    assert first_page.json()["offset"] == 0
    assert second_page.json()["offset"] == 1
    assert {
        first_page.json()["items"][0]["classification"],
        second_page.json()["items"][0]["classification"],
    } == {"wrong", "verified"}

    invalid = client.get("/v1/outcome-graphs", params={"classification": "wrong,not-real"})
    assert invalid.status_code == 400

    summary = client.get("/v1/outcome-graphs/coverage-summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["counts"]["verified"] == 1
    assert body["counts"]["pending"] == 1
    assert body["counts"]["unknown"] == 1
    assert body["coverage_percent"] == 25.0


def test_outcome_graph_attestation_contains_canonical_subject_digest(client: TestClient) -> None:
    graph = {
        "workflow_key": "refund-workflow",
        "pack_version": "1.0.0",
        "expected_effects": [{"effect_key": "refund_posted"}],
        "actual_effects": [{"effect_key": "refund_posted", "matched": True, "observation_digest": "obs_1"}],
        "classification": "verified",
    }
    with client.session_local() as session:
        intent = _intent(intent_json={"refund_id": "rf_private"})
        session.add(intent)
        row = FinalOutcomeGraph(
            project_id="proj_test",
            environment="production",
            intent_id=intent.id,
            graph_digest="digest",
            graph_json=json.dumps(graph, sort_keys=True, separators=(",", ":")),
            classification="verified",
            verification_status="verified",
            verified_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.commit()
        graph_id = row.id
        intent_id = intent.id
        intent_digest = intent.intent_digest

    response = client.get(f"/v1/outcome-graphs/{graph_id}/attestation")
    assert response.status_code == 200, response.text
    statement = verify_envelope(response.json(), action_receipt_public_key_payload()["public_key"])
    assert statement["subject"] == [
        {
            "name": f"outcome-graph/{graph_id}",
            "digest": {"sha256": hashlib.sha256(json.dumps(graph, sort_keys=True, separators=(",", ":")).encode()).hexdigest()},
        },
        {"name": f"intent/{intent_id}", "digest": {"sha256": intent_digest}},
    ]
    assert statement["predicate"]["effects"] == [
        {"effect_key": "refund_posted", "matched": True, "observation_digest": "obs_1"}
    ]


def test_outcome_graph_evidence_export_is_tenant_scoped(client: TestClient) -> None:
    with client.session_local() as session:
        intent = _intent()
        session.add(intent)
        other = FinalOutcomeGraph(
            project_id="proj_other",
            environment="production",
            intent_id=intent.id,
            graph_digest="digest",
            graph_json="{}",
            classification="verified",
            verification_status="verified",
        )
        session.add(other)
        session.commit()
        graph_id = other.id

    response = client.get(f"/v1/outcome-graphs/{graph_id}/evidence-export")
    assert response.status_code == 404


def test_outcome_graph_attestation_returns_503_without_prod_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    with client.session_local() as session:
        intent = _intent()
        session.add(intent)
        row = FinalOutcomeGraph(
            project_id="proj_test",
            environment="production",
            intent_id=intent.id,
            graph_digest="digest",
            graph_json="{}",
            classification="verified",
            verification_status="verified",
        )
        session.add(row)
        session.commit()
        graph_id = row.id

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ACTION_RECEIPT_ED25519_PRIVATE_KEY", raising=False)
    get_settings.cache_clear()
    try:
        response = client.get(f"/v1/outcome-graphs/{graph_id}/attestation")
    finally:
        get_settings.cache_clear()
    assert response.status_code == 503
    assert response.json()["detail"] == "attestation signing key not configured"


def test_source_connector_crud_is_tenant_scoped_and_never_returns_secret_value(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRIPE_KEY_PROJ_TEST", "sk_live_secret_value")
    created = client.post(
        "/v1/source-connectors",
        json={
            "environment": "production",
            "capability": "stripe_refund.read",
            "connector_kind": "stripe",
            "secret_ref": "STRIPE_KEY_PROJ_TEST",
            "config": {"account": "acct_test"},
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["secret_ref"] == "STRIPE_KEY_PROJ_TEST"
    assert "sk_live_secret_value" not in created.text

    with client.session_local() as session:
        session.add(
            FinalSourceConnector(
                project_id="proj_other",
                environment="production",
                capability="stripe_refund.read",
                connector_kind="stripe",
                secret_ref="STRIPE_KEY_OTHER",
                config_json="{}",
            )
        )
        session.commit()

    listed = client.get("/v1/source-connectors")
    assert listed.status_code == 200, listed.text
    assert [item["project_id"] for item in listed.json()["items"]] == ["proj_test"]
    assert "sk_live_secret_value" not in listed.text

    app.dependency_overrides[require_tenant_context] = lambda: TenantContext(
        tenant_id="proj_test",
        role="viewer",
        subject="viewer",
    )
    forbidden = client.post(
        "/v1/source-connectors",
        json={
            "capability": "stripe_refund.read",
            "connector_kind": "stripe",
            "secret_ref": "STRIPE_KEY_PROJ_TEST",
        },
    )
    assert forbidden.status_code == 403


def _intent(*, intent_json: dict | None = None) -> FinalWorkflowIntent:
    return FinalWorkflowIntent(
        id=str(uuid4()),
        project_id="proj_test",
        environment="production",
        idempotency_key=str(uuid4()),
        intent_digest=str(uuid4()),
        intent_json=json.dumps(intent_json or {}, separators=(",", ":")),
    )


def _pending_graph(intent: FinalWorkflowIntent, pack: FinalAssurancePack, *, now: datetime) -> FinalOutcomeGraph:
    graph = {
        "workflow_key": pack.workflow_key,
        "pack_version": pack.version,
        "intent_id": intent.id,
        "assurance_pack_id": pack.id,
        "observation_count": 0,
    }
    return FinalOutcomeGraph(
        project_id="proj_test",
        environment="production",
        intent_id=intent.id,
        graph_digest="pending",
        graph_json=json.dumps(graph, separators=(",", ":")),
        classification="pending",
        verification_status="pending",
        next_check_at=now - timedelta(seconds=1),
    )


def _connector(*, capability: str = "refund.read") -> FinalSourceConnector:
    return FinalSourceConnector(
        project_id="proj_test",
        environment="production",
        capability=capability,
        connector_kind="stripe",
        secret_ref="STRIPE_KEY_PROJ_TEST",
        config_json="{}",
    )


def _pack(*, capability: str = "refund.read", predicate: str = "refund.status == 'posted'") -> FinalAssurancePack:
    pack = {
        "schema_version": "zroky.workflow_assurance_pack.v1",
        "workflow_key": "refund-workflow",
        "version": "1.0.0",
        "object_types": [{"key": "refund", "schema": {"type": "object"}}],
        "effects": [{"key": "refund_posted", "object_type": "refund", "predicate": predicate}],
        "source_bindings": [
            {
                "key": "ledger_refunds",
                "connector_capability": capability,
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
