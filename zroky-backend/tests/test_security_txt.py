"""Tests for RFC 9116 security.txt and responsible-disclosure endpoints."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test_security.db")
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-security")

from fastapi.testclient import TestClient

from app.main import app


def test_security_txt_is_plain_text():
    """security.txt must be served as text/plain with proper headers."""
    client = TestClient(app)
    resp = client.get("/.well-known/security.txt")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


def test_security_txt_contains_contact():
    """security.txt must contain a Contact: mailto: line."""
    client = TestClient(app)
    resp = client.get("/.well-known/security.txt")
    body = resp.text
    assert "Contact: mailto:" in body
    assert "security@zroky.ai" in body


def test_security_txt_contains_expires():
    """security.txt must contain an Expires field (RFC 9116)."""
    client = TestClient(app)
    resp = client.get("/.well-known/security.txt")
    body = resp.text
    assert "Expires:" in body


def test_security_txt_contains_policy():
    """security.txt must reference the responsible-disclosure policy."""
    client = TestClient(app)
    resp = client.get("/.well-known/security.txt")
    body = resp.text
    assert "Policy:" in body


def test_security_response_json():
    """The /security endpoint returns a JSON responsible-disclosure policy."""
    client = TestClient(app)
    resp = client.get("/security")
    assert resp.status_code == 200
    data = resp.json()
    assert data["policy"] == "Responsible Disclosure"
    assert "contact" in data
    assert "safe_harbor" in data


def test_security_acknowledgments():
    """The /security/acknowledgments endpoint returns an acknowledgments list."""
    client = TestClient(app)
    resp = client.get("/security/acknowledgments")
    assert resp.status_code == 200
    data = resp.json()
    assert "acknowledgments" in data
    assert isinstance(data["acknowledgments"], list)
