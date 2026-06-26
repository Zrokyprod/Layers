import json as _json
import logging as _logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.router import api_router
from app.core.config import get_settings, is_production_env, validate_runtime_settings
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.core.trusted_hosts import LivenessBypassTrustedHostMiddleware
from app.observability.context import get_correlation_id
from app.observability.middleware import install_observability_middleware

_startup_logger = _logging.getLogger(__name__)
_drift_sink_registered = False


def _register_judge_drift_alert_sink() -> None:
    """Wire judge calibration drift breaches → project_alerts table.

    Registered once at startup. The callback opens its own DB session so it
    is safe to call from any thread (Celery worker, sync route, test runner).
    Already-open alerts are silently skipped via the unique constraint.
    """
    global _drift_sink_registered
    if _drift_sink_registered:
        return
    _drift_sink_registered = True

    from sqlalchemy.exc import IntegrityError

    from app.db.models import ProjectAlert
    from app.db.session import SessionLocal
    from app.services.judge_calibration import DriftStatus, register_alert_callback

    def _on_drift(status: DriftStatus) -> None:
        diagnosis_id = f"judge_drift:{status.judge_model}"[:64]
        title = (
            f"Judge drift: {status.judge_model} disagreement "
            f"{status.disagreement_rate:.1%} ≥ threshold {status.threshold:.1%}"
        )[:255]
        evidence = _json.dumps(
            {
                "judge_model": status.judge_model,
                "disagreement_rate": round(status.disagreement_rate, 4),
                "disagreement_count": status.disagreement_count,
                "sample_count": status.sample_count,
                "threshold": status.threshold,
            },
            separators=(",", ":"),
        )
        db = SessionLocal()
        try:
            db.add(
                ProjectAlert(
                    tenant_id=status.project_id,
                    diagnosis_id=diagnosis_id,
                    category="JUDGE_DRIFT",
                    severity="high",
                    status="OPEN",
                    source="judge_calibration",
                    title=title,
                    evidence_json=evidence,
                )
            )
            db.commit()
            try:
                from app.services.alerts import auto_send_pending_alerts_to_slack

                auto_send_pending_alerts_to_slack(
                    db,
                    tenant_id=status.project_id,
                    diagnosis_id=diagnosis_id,
                    categories=["JUDGE_DRIFT"],
                    agent_name=status.judge_model,
                )
            except Exception:  # noqa: BLE001
                _startup_logger.exception(
                    "judge_drift_alert_sink: failed to deliver Slack alert project=%s model=%s",
                    status.project_id,
                    status.judge_model,
                )
        except IntegrityError:
            db.rollback()  # alert already open — ignore duplicate
        except Exception:
            db.rollback()
            _startup_logger.exception(
                "judge_drift_alert_sink: failed to persist alert project=%s model=%s",
                status.project_id,
                status.judge_model,
            )
        finally:
            db.close()

    register_alert_callback(_on_drift)

settings = get_settings()
validate_runtime_settings(settings)
setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)

_is_production = is_production_env(settings.APP_ENV)

# Rate limiter — shared instance from app.core.limiter (uses Redis when available)

# Allowed CORS origins — set ALLOWED_ORIGINS env var (comma-separated) in production
_allowed_origins = [o.strip() for o in getattr(settings, "ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not _allowed_origins and not _is_production:
    _allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]


def _normalize_host(host: str) -> str:
    host = host.strip().lower().rstrip(".")
    if host.startswith("[") and "]" in host:
        return host.split("]", 1)[0].lstrip("[")
    return host.split(":", 1)[0]


def _is_trusted_host(host: str, allowed_hosts: list[str]) -> bool:
    normalized = _normalize_host(host)
    if not normalized:
        return False
    for allowed in allowed_hosts:
        candidate = _normalize_host(allowed)
        if candidate == "*":
            return True
        if candidate.startswith("*."):
            suffix = candidate[1:]
            if normalized.endswith(suffix) and normalized != candidate[2:]:
                return True
        elif normalized == candidate:
            return True
    return False


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.DATABASE_URL.startswith("sqlite"):
        Path(".data").mkdir(parents=True, exist_ok=True)
    _register_judge_drift_alert_sink()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
    # Disable interactive docs in production to avoid leaking schema
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# Attach slowapi limiter state and 429 error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

CORRELATION_ID_HEADER = "X-Correlation-Id"


async def _correlation_error_handler(_request: Request, exc: StarletteHTTPException) -> Response:
    """Return correlation_id in every HTTP error response for distributed tracing.

    Merges any headers set on the HTTPException (e.g. X-Zroky-Plan-Hint on 402,
    WWW-Authenticate on 401) so route-level header semantics survive this handler.
    """
    correlation_id = get_correlation_id()
    headers: dict[str, str] = {}
    exc_headers = getattr(exc, "headers", None)
    if exc_headers:
        headers.update(exc_headers)
    if correlation_id and correlation_id != "-":
        headers[CORRELATION_ID_HEADER] = correlation_id
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "correlation_id": correlation_id,
        },
        headers=headers,
    )


app.add_exception_handler(StarletteHTTPException, _correlation_error_handler)


# CORS — lock down to known origins; credentials require explicit origin list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Reject requests with unexpected Host headers (prevents host-header injection)
if _is_production:
    _trusted_hosts = [h.strip() for h in getattr(settings, "TRUSTED_HOSTS", "").split(",") if h.strip()]
    if _trusted_hosts:
        app.add_middleware(LivenessBypassTrustedHostMiddleware, allowed_hosts=_trusted_hosts)

install_observability_middleware(app)

# Reject oversized request bodies before they are read (max 10 MB).
# GZipMiddleware is added to compress large responses.
app.add_middleware(GZipMiddleware, minimum_size=1024)

_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


class _BodyTooLarge(Exception):
    pass


class _BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        content_length = headers.get("content-length")
        if content_length and int(content_length) > self.max_body_bytes:
            await self._send_413(send)
            return

        received = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            await self._send_413(send)

    async def _send_413(self, send: Send) -> None:
        body = b'{"detail":"Request body exceeds the 10 MB limit."}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-length", str(len(body)).encode("latin-1")),
                    (b"content-type", b"application/json"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


app.add_middleware(_BodySizeLimitMiddleware, max_body_bytes=_MAX_BODY_BYTES)


@app.middleware("http")
async def add_security_headers(request: Request, call_next: object) -> Response:
    response: Response = await call_next(request)  # type: ignore[operator]
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "0"
    if _is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


app.include_router(api_router)
# Compatibility alias for blueprint-style routes (for example /api/v1/*).
app.include_router(api_router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {
        "service": settings.APP_NAME,
        "env": settings.APP_ENV,
        "deploy_target": settings.DEPLOY_TARGET,
    }
