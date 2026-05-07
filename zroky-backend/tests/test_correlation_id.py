"""Tests for request correlation-id middleware."""
import os

from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test_correlation_id.db")
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-for-correlation-id")
os.environ.setdefault("ALLOW_PROJECT_HEADER_CONTEXT", "true")
os.environ.setdefault("REQUIRE_PROVISIONING_TOKEN", "false")

from app.main import app


def test_response_includes_request_id_header():
    """Every response must include X-Request-Id header."""
    client = TestClient(app)
    resp = client.get("/")
    assert "X-Request-Id" in resp.headers
    assert resp.headers["X-Request-Id"]


def test_response_includes_correlation_id_header():
    """Every response must include X-Correlation-Id header."""
    client = TestClient(app)
    resp = client.get("/")
    assert "X-Correlation-Id" in resp.headers
    assert resp.headers["X-Correlation-Id"]


def test_provided_correlation_id_is_echoed():
    """If client sends X-Correlation-Id header, server must echo it back."""
    client = TestClient(app)
    expected = "trace-abc-123"
    resp = client.get("/", headers={"X-Correlation-Id": expected})
    assert resp.headers["X-Correlation-Id"] == expected


def test_provided_request_id_is_echoed():
    """If client sends X-Request-Id header, server must echo it back."""
    client = TestClient(app)
    expected = "req-xyz-456"
    resp = client.get("/", headers={"X-Request-Id": expected})
    assert resp.headers["X-Request-Id"] == expected


def test_no_correlation_id_when_none_provided():
    """When no correlation ID header is sent, one is generated (as UUID-like string)."""
    client = TestClient(app)
    resp = client.get("/")
    cid = resp.headers["X-Correlation-Id"]
    # Should be a non-empty string, and equal to X-Request-Id when no CID provided
    assert cid
    assert "-" in cid  # uuid4 format


def test_error_response_includes_correlation_id():
    """HTTPException responses must include correlation_id in body and header."""
    client = TestClient(app)
    # Use an endpoint that raises HTTPException to trigger our custom handler
    resp = client.get("/v1/auth/me", headers={"Authorization": "Bearer invalid-token"})
    assert resp.status_code in (401, 403)
    body = resp.json()
    assert "correlation_id" in body
    assert resp.headers["X-Correlation-Id"] == body["correlation_id"]


def test_validation_error_header_includes_correlation_id():
    """422 validation error responses must include X-Correlation-Id header."""
    client = TestClient(app)
    # Trigger a 422 via mismatched passwords
    resp = client.post("/v1/auth/register", json={
        "email": "valid@example.com",
        "password": "password123",
        "confirm_password": "different123",
    })
    assert resp.status_code in (422,)  # FastAPI returns 422 for password mismatch
    # We primarily care that correlation_id header is present in error responses
    assert "X-Correlation-Id" in resp.headers
    assert resp.headers["X-Correlation-Id"]


def test_correlation_id_propagated_in_logs():
    """Logs emitted during a request must include the correlation ID."""
    import logging
    import json

    log_records: list[dict] = []
    test_handler = logging.StreamHandler()
    test_handler.setFormatter(logging.Formatter("%(message)s"))

    # Add a custom handler to capture JSON log output
    class CaptureHandler(logging.Handler):
        def emit(self, record):
            log_records.append(json.loads(self.format(record)))

    cap = CaptureHandler()
    cap.setFormatter(logging.Formatter("%(message)s"))

    from app.core.logging import StructuredJsonFormatter
    cap.setFormatter(StructuredJsonFormatter())

    logger = logging.getLogger("app.observability.middleware")
    logger.addHandler(cap)
    logger.setLevel(logging.INFO)

    try:
        client = TestClient(app)
        resp = client.get("/", headers={"X-Correlation-Id": "trace-log-test"})
        assert resp.status_code == 200

        # Find the http_request_completed log record
        matching = [r for r in log_records if "http_request" in str(r)]
        assert matching, f"No http_request log found in {log_records}"
        # correlation_id may be at top-level or in context depending on format
        record = matching[0]
        assert record.get("correlation_id") == "trace-log-test" or record.get("context", {}).get("correlation_id") == "trace-log-test"
    finally:
        logger.removeHandler(cap)
