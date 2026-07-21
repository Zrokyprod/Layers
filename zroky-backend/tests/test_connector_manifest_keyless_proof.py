from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
from sqlalchemy import create_engine

from app.domain.connector_manifest import execute_connector_manifest_read, validate_connector_manifest
from app.domain.outcome_graph import build_outcome_graph_snapshot
from app.infrastructure.relay_protocol import RelayReadCommandRequest, prepare_read_command


def test_keyless_rest_and_sql_sources_verify_one_outcome_graph(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def rest_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"record": {"refund_id": "rf_1", "status": "succeeded"}})

    source_db = tmp_path / "source.db"
    engine = create_engine(f"sqlite:///{source_db}", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE invoices (invoice_id TEXT PRIMARY KEY, status TEXT)")
        connection.exec_driver_sql("INSERT INTO invoices (invoice_id, status) VALUES (?, ?)", ("inv_1", "paid"))
    engine.dispose()

    rest_manifest = validate_connector_manifest(
        {
            "manifest_id": "local_refund.v1",
            "connector_id": "local_refund",
            "primitive": "generic_rest",
            "source_binding": "refund_api",
            "connector_capability": "refund.read",
            "auth": {"type": "none"},
            "read": {
                "method": "GET",
                "base_url": "https://proof.example",
                "path_template": "/refunds/{record_ref}",
                "record_path": "record",
            },
            "test_read": {"object_ref": "rf_1"},
            "object_schema": {"refund_id": "string", "status": "string"},
            "correlation": {"claim_field": "refund_id", "source_field": "refund_id"},
            "expected_effect_mapping": {"refund.status": "status"},
            "evidence_template_id": "local_refund_evidence.v1",
        }
    )
    sql_manifest = validate_connector_manifest(
        {
            "manifest_id": "local_invoice_db.v1",
            "connector_id": "database_read",
            "primitive": "postgres_read",
            "source_binding": "invoice_db",
            "connector_capability": "invoice.read",
            "auth": {"type": "none"},
            "read": {
                "method": "GET",
                "database_url": f"sqlite:///{source_db}",
                "query": "SELECT invoice_id, status FROM invoices WHERE invoice_id = :invoice_id",
            },
            "test_read": {"object_ref": "inv_1"},
            "object_schema": {"invoice_id": "string", "status": "string"},
            "correlation": {"claim_field": "invoice_id", "source_field": "invoice_id"},
            "expected_effect_mapping": {"invoice.status": "status"},
            "evidence_template_id": "local_invoice_evidence.v1",
        }
    )

    refund_source = execute_connector_manifest_read(
        prepare_read_command(
            "proj_1",
            RelayReadCommandRequest(
                source_binding="refund_api",
                connector_capability="refund.read",
                object_ref="rf_1",
                selector={"record_ref": "rf_1"},
            ),
        ),
        rest_manifest,
        transport=httpx.MockTransport(rest_handler),
    )
    invoice_source = execute_connector_manifest_read(
        prepare_read_command(
            "proj_1",
            RelayReadCommandRequest(
                source_binding="invoice_db",
                connector_capability="invoice.read",
                object_ref="inv_1",
                selector={"invoice_id": "inv_1"},
            ),
        ),
        sql_manifest,
        allow_sqlite_for_tests=True,
    )

    assert str(requests[0].url) == "https://proof.example/refunds/rf_1"
    assert refund_source.record == {"refund_id": "rf_1", "status": "succeeded", "record_ref": "rf_1"}
    assert invoice_source.record == {"invoice_id": "inv_1", "status": "paid"}

    graph = build_outcome_graph_snapshot(
        intent={"workflow_key": "keyless-proof", "refund_id": "rf_1", "invoice_id": "inv_1"},
        assurance_pack={
            "schema_version": "zroky.workflow_assurance_pack.v1",
            "workflow_key": "keyless-proof",
            "version": "1.0.0",
            "intent_schema": {"type": "object"},
            "object_types": [
                {"key": "refund", "schema": {"type": "object"}},
                {"key": "invoice", "schema": {"type": "object"}},
            ],
            "effects": [
                {"key": "refund_succeeded", "object_type": "refund", "predicate": 'refund.status == "succeeded"'},
                {"key": "invoice_paid", "object_type": "invoice", "predicate": 'invoice.status == "paid"'},
            ],
            "source_bindings": [
                {"key": "refund_api", "connector_capability": "refund.read", "object_type": "refund", "freshness_seconds": 300},
                {"key": "invoice_db", "connector_capability": "invoice.read", "object_type": "invoice", "freshness_seconds": 300},
            ],
            "recovery_playbooks": [],
        },
        observations=[
            _observation("refund_api", "refund:rf_1", refund_source.record, refund_source.metadata),
            _observation("invoice_db", "invoice:inv_1", invoice_source.record, invoice_source.metadata),
        ],
    )

    assert graph["classification"] == "verified"
    assert graph["observation_count"] == 2
    assert {effect["source_binding"] for effect in graph["actual_effects"]} == {"refund_api", "invoice_db"}


def _observation(
    source_binding: str,
    object_ref: str,
    record: dict[str, object] | None,
    metadata: dict[str, object] | None,
) -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "source_kind": source_binding,
        "observed_object_ref": object_ref,
        "observed_state": record,
        "provenance": {**(metadata or {}), "source_binding": source_binding},
        "observed_at": now,
        "read_at": now,
        "freshness": {"age_seconds": 0, "max_freshness_seconds": 300, "fresh": True},
    }
