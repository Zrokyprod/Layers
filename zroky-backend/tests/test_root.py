from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert "service" in payload
    assert "env" in payload
    assert "deploy_target" in payload
