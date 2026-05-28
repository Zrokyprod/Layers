from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.trusted_hosts import LivenessBypassTrustedHostMiddleware


async def _ok(_request):
    return JSONResponse({"status": "ok"})


def test_liveness_bypasses_trusted_host_check():
    app = Starlette(routes=[Route("/health/live", _ok)])
    app.add_middleware(LivenessBypassTrustedHostMiddleware, allowed_hosts=["api.example.com"])

    response = TestClient(app).get("/health/live", headers={"host": "100.64.0.2"})

    assert response.status_code == 200


def test_other_paths_still_enforce_trusted_host_check():
    app = Starlette(routes=[Route("/private", _ok)])
    app.add_middleware(LivenessBypassTrustedHostMiddleware, allowed_hosts=["api.example.com"])

    response = TestClient(app).get("/private", headers={"host": "100.64.0.2"})

    assert response.status_code == 400
