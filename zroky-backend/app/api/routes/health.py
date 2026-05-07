import secrets

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.config import get_settings
from app.db.session import db_healthcheck
from app.observability.metrics import metrics_content_type, render_metrics
from app.services.redis_client import redis_healthcheck

router = APIRouter()


@router.get("/health/live")
def liveness() -> dict:
    settings = get_settings()
    return {"status": "ok", "service": settings.APP_NAME}


@router.get("/health/ready")
def readiness() -> dict:
    settings = get_settings()
    checks: dict[str, str] = {}
    healthy = True

    if settings.ENABLE_READY_DB_CHECK:
        if db_healthcheck():
            checks["database"] = "ok"
        else:
            checks["database"] = "failed"
            healthy = False
    else:
        checks["database"] = "skipped"

    if settings.ENABLE_READY_REDIS_CHECK:
        if redis_healthcheck():
            checks["redis"] = "ok"
        else:
            checks["redis"] = "failed"
            healthy = False
    else:
        checks["redis"] = "skipped"

    return {
        "status": "ok" if healthy else "degraded",
        "checks": checks,
    }


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    settings = get_settings()
    if not settings.ENABLE_METRICS_ENDPOINT:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metrics endpoint is disabled")

    if settings.METRICS_TOKEN:
        provided_token = request.headers.get(settings.METRICS_TOKEN_HEADER_NAME)
        if not provided_token or not secrets.compare_digest(provided_token, settings.METRICS_TOKEN):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid metrics credentials")

    return Response(content=render_metrics(), media_type=metrics_content_type())
