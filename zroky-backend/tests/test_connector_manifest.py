from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.connector_manifest import CONNECTOR_MANIFEST_SCHEMA_VERSION, validate_connector_manifest


def _manifest(**overrides):
    payload = {
        "manifest_id": "stripe_refund.v1",
        "connector_id": "stripe_refund",
        "primitive": "generic_rest",
        "source_binding": "stripe",
        "connector_capability": "refund.read",
        "auth": {
            "type": "bearer",
            "credential_ref": "vault://zroky/stripe/read-only",
            "allowed_scopes": ["refunds.read"],
        },
        "read": {"method": "GET", "path_template": "/v1/refunds/{object_ref}"},
        "test_read": {"object_ref": "re_test"},
        "object_schema": {"id": "string", "status": "string"},
        "correlation": {"claim_field": "refund_id", "source_field": "id"},
        "freshness": {"max_age_seconds": 300},
        "expected_effect_mapping": {"refund.status": "status"},
        "evidence_template_id": "stripe_refund_evidence.v1",
    }
    payload.update(overrides)
    return payload


def test_connector_manifest_accepts_minimal_generic_rest_read_preset() -> None:
    manifest = validate_connector_manifest(_manifest())

    assert manifest.schema_version == CONNECTOR_MANIFEST_SCHEMA_VERSION
    assert manifest.primitive == "generic_rest"
    assert manifest.read.method == "GET"
    assert manifest.correlation.source_field == "id"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_connector_manifest_rejects_mutating_http_methods(method: str) -> None:
    with pytest.raises(ValidationError, match="read-only"):
        validate_connector_manifest(_manifest(read={"method": method, "path_template": "/v1/refunds/{object_ref}"}))


def test_connector_manifest_rejects_write_scopes() -> None:
    payload = _manifest(auth={"type": "oauth", "credential_ref": "vault://zroky/github/app", "allowed_scopes": ["checks.write"]})

    with pytest.raises(ValidationError, match="read-only"):
        validate_connector_manifest(payload)


def test_connector_manifest_rejects_raw_secret_fields() -> None:
    payload = _manifest(auth={"type": "bearer", "credential_ref": "vault://zroky/stripe/read-only"})
    payload["read"]["headers"] = {"Authorization": "Bearer sk_test_secret"}

    with pytest.raises(ValueError, match="raw secret"):
        validate_connector_manifest(payload)


def test_postgres_manifest_requires_read_only_query() -> None:
    payload = _manifest(
        connector_id="postgres_read",
        manifest_id="postgres_refunds.v1",
        primitive="postgres_read",
        read={"method": "GET", "query": "UPDATE refunds SET status = 'done'"},
    )

    with pytest.raises(ValidationError, match="read-only"):
        validate_connector_manifest(payload)


def test_webhook_manifest_requires_callback_schema() -> None:
    payload = _manifest(
        connector_id="webhook_callback",
        manifest_id="webhook_refunds.v1",
        primitive="webhook_callback",
        auth={"type": "hmac", "credential_ref": "vault://zroky/webhook/signing"},
        read={"method": "GET"},
    )

    with pytest.raises(ValidationError, match="callback_schema"):
        validate_connector_manifest(payload)
