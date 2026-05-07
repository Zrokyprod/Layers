from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.router import api_router
from app.core.config import get_settings, validate_runtime_settings
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.observability.context import get_correlation_id
from app.observability.middleware import install_observability_middleware

settings = get_settings()
validate_runtime_settings(settings)
setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)

_is_production = settings.APP_ENV == "production"

# Rate limiter — shared instance from app.core.limiter (uses Redis when available)

# Allowed CORS origins — set ALLOWED_ORIGINS env var (comma-separated) in production
_allowed_origins = [o.strip() for o in getattr(settings, "ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not _allowed_origins and not _is_production:
    _allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.DATABASE_URL.startswith("sqlite"):
        Path(".data").mkdir(parents=True, exist_ok=True)
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
    """Return correlation_id in every HTTP error response for distributed tracing."""
    correlation_id = get_correlation_id()
    headers = {CORRELATION_ID_HEADER: correlation_id} if correlation_id and correlation_id != "-" else {}
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
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted_hosts)

install_observability_middleware(app)

# Reject oversized request bodies before they are read (max 10 MB).
# GZipMiddleware is added to compress large responses.
app.add_middleware(GZipMiddleware, minimum_size=1024)

_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


@app.middleware("http")
async def _limit_body_size(request: Request, call_next: object) -> Response:
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body exceeds the 10 MB limit."},
        )
    return await call_next(request)  # type: ignore[operator]


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
