"""Export FastAPI OpenAPI schema to a JSON file for API contract generation.

Patches heavy production dependencies (pgvector, pandas, numpy, redis, celery)
so the script runs in a minimal environment without installing them.
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


def _patch_heavy_deps() -> None:
    """Stub out heavy optional dependencies so schema export can import the app."""
    # pgvector
    pgvector_mod = types.ModuleType("pgvector")
    pgvector_sqlalchemy = types.ModuleType("pgvector.sqlalchemy")
    # Vector must be a SQLAlchemy-compatible type for Mapped[list[float]] annotations
    from sqlalchemy.types import UserDefinedType

    class _MockVector(UserDefinedType):
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            pass

        def get_col_spec(self, **kwargs):  # type: ignore[override]
            return "vector(1536)"

    pgvector_sqlalchemy.Vector = _MockVector
    pgvector_mod.sqlalchemy = pgvector_sqlalchemy
    sys.modules["pgvector"] = pgvector_mod
    sys.modules["pgvector.sqlalchemy"] = pgvector_sqlalchemy

    # pandas (used in some service imports)
    pandas_mod = types.ModuleType("pandas")
    pandas_mod.DataFrame = MagicMock
    pandas_mod.Series = MagicMock
    sys.modules["pandas"] = pandas_mod
    sys.modules["pd"] = pandas_mod

    # numpy (used via pandas and embeddings)
    numpy_mod = types.ModuleType("numpy")
    numpy_mod.ndarray = MagicMock
    numpy_mod.array = MagicMock()
    numpy_mod.float32 = float
    sys.modules["numpy"] = numpy_mod
    sys.modules["np"] = numpy_mod

    # redis (optional for cache / limiter)
    redis_mod = types.ModuleType("redis")
    redis_mod.Redis = MagicMock
    redis_mod.RedisError = Exception
    sys.modules["redis"] = redis_mod

    # celery (optional for worker tasks)
    celery_mod = types.ModuleType("celery")
    celery_app = types.ModuleType("celery.schedules")
    celery_app.crontab = MagicMock()

    class _MockConf:
        def update(self, **kwargs):  # type: ignore[no-untyped-def]
            pass

    class _MockCelery:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            self.conf = _MockConf()

        def task(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            def decorator(func):  # type: ignore[no-untyped-def]
                return func
            return decorator

        def autodiscover_tasks(self, packages, **kwargs):  # type: ignore[no-untyped-def]
            pass

    celery_mod.Celery = _MockCelery
    celery_mod.schedules = celery_app
    sys.modules["celery"] = celery_mod
    sys.modules["celery.schedules"] = celery_app

    # slowapi
    slowapi_mod = types.ModuleType("slowapi")
    slowapi_errors = types.ModuleType("slowapi.errors")
    slowapi_errors.RateLimitExceeded = type("RateLimitExceeded", (Exception,), {})
    slowapi_mod.errors = slowapi_errors
    slowapi_mod._rate_limit_exceeded_handler = lambda request, exc: None

    class _MockLimiter:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            pass

        def limit(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            def decorator(func):  # type: ignore[no-untyped-def]
                return func
            return decorator

    slowapi_mod.Limiter = _MockLimiter
    sys.modules["slowapi"] = slowapi_mod
    sys.modules["slowapi.errors"] = slowapi_errors
    slowapi_ext = types.ModuleType("slowapi.util")
    slowapi_ext.get_remote_address = lambda: "127.0.0.1"
    sys.modules["slowapi.util"] = slowapi_ext

    # bcrypt
    bcrypt_mod = types.ModuleType("bcrypt")
    bcrypt_mod.gensalt = MagicMock(return_value=b"salt")
    bcrypt_mod.hashpw = MagicMock(return_value=b"hash")
    bcrypt_mod.checkpw = MagicMock(return_value=True)
    sys.modules["bcrypt"] = bcrypt_mod

    # razorpay (optional billing SDK; only import-time symbols are needed)
    razorpay_mod = types.ModuleType("razorpay")
    razorpay_errors = types.ModuleType("razorpay.errors")
    razorpay_errors.BadRequestError = type("BadRequestError", (Exception,), {})
    razorpay_errors.GatewayError = type("GatewayError", (Exception,), {})
    razorpay_errors.ServerError = type("ServerError", (Exception,), {})

    class _MockRazorpayClient:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            self.order = MagicMock()
            self.payment = MagicMock()

    razorpay_mod.Client = _MockRazorpayClient
    razorpay_mod.errors = razorpay_errors
    sys.modules["razorpay"] = razorpay_mod
    sys.modules["razorpay.errors"] = razorpay_errors

    # prometheus_client
    prom_mod = types.ModuleType("prometheus_client")
    prom_mod.Counter = MagicMock
    prom_mod.Histogram = MagicMock
    prom_mod.Gauge = MagicMock
    prom_mod.generate_latest = MagicMock(return_value=b"")
    prom_mod.CONTENT_TYPE_LATEST = "text/plain"
    sys.modules["prometheus_client"] = prom_mod

    # llm_client (our unified OpenRouter client – we never call it during schema export)
    llm_mod = types.ModuleType("app.services.llm_client")

    class _MockLLMClient:
        """No-op client for schema export."""

        def chat_completions_create(self, **kwargs):
            return MagicMock(choices=[MagicMock(message=MagicMock(content="{}"))])

    def _mock_get_llm_client():
        return _MockLLMClient()

    llm_mod.get_llm_client = _mock_get_llm_client
    llm_mod.OpenRouterClient = _MockLLMClient
    sys.modules["app.services.llm_client"] = llm_mod


def _clear_pycache(root: Path) -> None:
    for pycache in root.rglob("__pycache__"):
        if pycache.is_dir():
            import shutil
            shutil.rmtree(pycache, ignore_errors=True)


def main() -> int:
    # Purge stale bytecode so removed modules don't resurrect from .pyc files
    backend_root = Path(__file__).resolve().parent.parent
    _clear_pycache(backend_root)
    sys.dont_write_bytecode = True

    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-for-schema-export")
    os.environ.setdefault("GITHUB_TOKEN_ENCRYPTION_KEY", "test-encryption-key-for-schema-export")
    os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-for-schema-export")
    os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key-for-schema-export")
    os.environ.setdefault("PII_ENCRYPTION_KEY", "test-pii-key-for-schema-export")
    _patch_heavy_deps()

    backend_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(backend_root))

    from app.main import app  # noqa: E402

    schema = app.openapi()
    if schema is None:
        print("ERROR: app.openapi() returned None", file=sys.stderr)
        return 1

    output_path = Path(backend_root).parent / "api-contracts" / "zroky-api-v1.openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print(f"Exported OpenAPI schema to {output_path}")
    info = schema.get("info", {})
    paths = schema.get("paths", {})
    components = schema.get("components", {})
    schemas = components.get("schemas", {})
    print(f"  Title: {info.get('title')}")
    print(f"  Version: {info.get('version')}")
    print(f"  Paths: {len(paths)}")
    print(f"  Schemas: {len(schemas)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
