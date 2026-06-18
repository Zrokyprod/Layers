"""API v1 contract freeze check (ZROKY-006).

Detects BREAKING changes between the committed frozen spec
(api-contracts/zroky-api-v1.openapi.json) and the spec generated from the
current app code.

Additive changes (new paths, new operations, new optional fields) are allowed
and reported as INFO only.  Breaking changes cause a non-zero exit so CI fails.

Breaking = removed path, removed HTTP operation, removed required request-body
           field, removed response property, removed 200/201 response body.

Run locally:  python scripts/check_api_v1_frozen.py
CI:           same (non-zero exit fails the job).
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Repo / path helpers
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        if (ancestor / ".git").exists():
            return ancestor
    return here.parent.parent


# ---------------------------------------------------------------------------
# Heavy-dependency stubs (mirrors export_openapi.py so the app can be
# imported without a full production venv)
# ---------------------------------------------------------------------------

def _patch_heavy_deps() -> None:
    pgvector_mod = types.ModuleType("pgvector")
    pgvector_sqlalchemy = types.ModuleType("pgvector.sqlalchemy")
    from sqlalchemy.types import UserDefinedType

    class _MockVector(UserDefinedType):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def get_col_spec(self, **kwargs: Any) -> str:  # type: ignore[override]
            return "vector(1536)"

    pgvector_sqlalchemy.Vector = _MockVector
    pgvector_mod.sqlalchemy = pgvector_sqlalchemy
    sys.modules.setdefault("pgvector", pgvector_mod)
    sys.modules.setdefault("pgvector.sqlalchemy", pgvector_sqlalchemy)

    pandas_mod = types.ModuleType("pandas")
    pandas_mod.DataFrame = MagicMock  # type: ignore[attr-defined]
    pandas_mod.Series = MagicMock  # type: ignore[attr-defined]
    sys.modules.setdefault("pandas", pandas_mod)
    sys.modules.setdefault("pd", pandas_mod)

    numpy_mod = types.ModuleType("numpy")
    numpy_mod.ndarray = MagicMock  # type: ignore[attr-defined]
    numpy_mod.array = MagicMock()  # type: ignore[attr-defined]
    numpy_mod.float32 = float  # type: ignore[attr-defined]
    sys.modules.setdefault("numpy", numpy_mod)
    sys.modules.setdefault("np", numpy_mod)

    redis_mod = types.ModuleType("redis")
    redis_mod.Redis = MagicMock  # type: ignore[attr-defined]
    redis_mod.RedisError = Exception  # type: ignore[attr-defined]
    sys.modules.setdefault("redis", redis_mod)

    celery_mod = types.ModuleType("celery")
    celery_schedules = types.ModuleType("celery.schedules")
    celery_schedules.crontab = MagicMock()  # type: ignore[attr-defined]

    class _MockConf:
        def update(self, **kwargs: Any) -> None:
            pass

    class _MockCelery:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.conf = _MockConf()

        def task(self, *args: Any, **kwargs: Any) -> Any:
            def decorator(func: Any) -> Any:
                return func
            return decorator

        def autodiscover_tasks(self, packages: Any, **kwargs: Any) -> None:
            pass

    celery_mod.Celery = _MockCelery  # type: ignore[attr-defined]
    celery_mod.schedules = celery_schedules  # type: ignore[attr-defined]
    sys.modules.setdefault("celery", celery_mod)
    sys.modules.setdefault("celery.schedules", celery_schedules)

    slowapi_mod = types.ModuleType("slowapi")
    slowapi_errors = types.ModuleType("slowapi.errors")
    slowapi_errors.RateLimitExceeded = type("RateLimitExceeded", (Exception,), {})  # type: ignore[attr-defined]
    slowapi_mod.errors = slowapi_errors  # type: ignore[attr-defined]
    slowapi_mod._rate_limit_exceeded_handler = lambda request, exc: None  # type: ignore[attr-defined]

    class _MockLimiter:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def limit(self, *args: Any, **kwargs: Any) -> Any:
            def decorator(func: Any) -> Any:
                return func
            return decorator

    slowapi_mod.Limiter = _MockLimiter  # type: ignore[attr-defined]
    sys.modules.setdefault("slowapi", slowapi_mod)
    sys.modules.setdefault("slowapi.errors", slowapi_errors)
    slowapi_util = types.ModuleType("slowapi.util")
    slowapi_util.get_remote_address = lambda: "127.0.0.1"  # type: ignore[attr-defined]
    sys.modules.setdefault("slowapi.util", slowapi_util)

    bcrypt_mod = types.ModuleType("bcrypt")
    bcrypt_mod.gensalt = MagicMock(return_value=b"salt")  # type: ignore[attr-defined]
    bcrypt_mod.hashpw = MagicMock(return_value=b"hash")  # type: ignore[attr-defined]
    bcrypt_mod.checkpw = MagicMock(return_value=True)  # type: ignore[attr-defined]
    sys.modules.setdefault("bcrypt", bcrypt_mod)

    razorpay_mod = types.ModuleType("razorpay")
    razorpay_errors = types.ModuleType("razorpay.errors")
    razorpay_errors.BadRequestError = type("BadRequestError", (Exception,), {})  # type: ignore[attr-defined]
    razorpay_errors.GatewayError = type("GatewayError", (Exception,), {})  # type: ignore[attr-defined]
    razorpay_errors.ServerError = type("ServerError", (Exception,), {})  # type: ignore[attr-defined]

    class _MockRazorpayClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.order = MagicMock()
            self.payment = MagicMock()

    razorpay_mod.Client = _MockRazorpayClient  # type: ignore[attr-defined]
    razorpay_mod.errors = razorpay_errors  # type: ignore[attr-defined]
    sys.modules.setdefault("razorpay", razorpay_mod)
    sys.modules.setdefault("razorpay.errors", razorpay_errors)

    prom_mod = types.ModuleType("prometheus_client")
    prom_mod.Counter = MagicMock  # type: ignore[attr-defined]
    prom_mod.Histogram = MagicMock  # type: ignore[attr-defined]
    prom_mod.Gauge = MagicMock  # type: ignore[attr-defined]
    prom_mod.generate_latest = MagicMock(return_value=b"")  # type: ignore[attr-defined]
    prom_mod.CONTENT_TYPE_LATEST = "text/plain"  # type: ignore[attr-defined]
    sys.modules.setdefault("prometheus_client", prom_mod)

    llm_mod = types.ModuleType("app.services.llm_client")

    class _MockLLMClient:
        def chat_completions_create(self, **kwargs: Any) -> Any:
            return MagicMock(choices=[MagicMock(message=MagicMock(content="{}"))])

    llm_mod.get_llm_client = lambda: _MockLLMClient()  # type: ignore[attr-defined]
    llm_mod.OpenRouterClient = _MockLLMClient  # type: ignore[attr-defined]
    sys.modules.setdefault("app.services.llm_client", llm_mod)


# ---------------------------------------------------------------------------
# Generate current spec from the live app code
# ---------------------------------------------------------------------------

def _generate_current_spec(repo_root: Path) -> dict[str, Any]:
    backend_root = repo_root / "zroky-backend"

    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-for-contract-check-32ch")
    os.environ.setdefault("GITHUB_TOKEN_ENCRYPTION_KEY", "test-encryption-key-for-check")
    os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-for-check")
    os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key-for-check")
    os.environ.setdefault("PII_ENCRYPTION_KEY", "test-pii-key-for-check")
    # The frozen v1 spec still includes legacy billing paths. Keep them
    # visible during the contract check so the checker verifies the full
    # compatibility surface, independent of production feature defaults.
    os.environ.setdefault("FEATURE_LEGACY_BILLING", "true")

    _patch_heavy_deps()

    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    # Import fresh — clear any cached app module
    for key in list(sys.modules.keys()):
        if key.startswith("app.") or key == "app":
            del sys.modules[key]

    from app.main import app  # type: ignore[import]  # noqa: E402
    schema = app.openapi()
    if not schema:
        raise RuntimeError("app.openapi() returned empty — cannot compare specs.")
    return schema  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# $ref resolution
# ---------------------------------------------------------------------------

def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    """Walk a JSON Pointer (e.g. '#/components/schemas/Foo') in spec."""
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for part in parts:
        if not isinstance(node, dict):
            return {}
        node = node.get(part, {})
    return node if isinstance(node, dict) else {}


def _inline(spec: dict[str, Any], node: Any, _depth: int = 0) -> Any:
    """Recursively resolve all $ref nodes.  Caps at depth 12 to avoid cycles."""
    if _depth > 12:
        return node
    if isinstance(node, dict):
        if "$ref" in node:
            resolved = _resolve_ref(spec, node["$ref"])
            return _inline(spec, resolved, _depth + 1)
        return {k: _inline(spec, v, _depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline(spec, item, _depth + 1) for item in node]
    return node


# ---------------------------------------------------------------------------
# Breaking-change detection helpers
# ---------------------------------------------------------------------------

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def _schema_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """Return merged properties, handling allOf/anyOf/oneOf trivially."""
    props: dict[str, Any] = dict(schema.get("properties") or {})
    for combiner in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(combiner) or []:
            props.update(sub.get("properties") or {})
    return props


def _check_schema_properties(
    frozen_schema: dict[str, Any],
    current_schema: dict[str, Any],
    context: str,
    breaking: list[str],
) -> None:
    """Verify every property present in frozen_schema exists in current_schema."""
    if not frozen_schema:
        return

    frozen_props = _schema_properties(frozen_schema)
    current_props = _schema_properties(current_schema)
    frozen_required: set[str] = set(frozen_schema.get("required") or [])
    current_required: set[str] = set(current_schema.get("required") or [])

    for field in frozen_required:
        if field not in current_required and field not in current_props:
            breaking.append(f"REQUIRED FIELD REMOVED: {context}.{field}")

    for prop in frozen_props:
        if prop not in current_props:
            breaking.append(f"PROPERTY REMOVED: {context}.{prop}")


def _get_json_schema(spec: dict[str, Any], body_or_resp: dict[str, Any]) -> dict[str, Any]:
    content = body_or_resp.get("content") or {}
    json_entry = content.get("application/json") or {}
    raw_schema = json_entry.get("schema") or {}
    return _inline(spec, raw_schema)


def _check_operation(
    frozen_spec: dict[str, Any],
    current_spec: dict[str, Any],
    frozen_op: dict[str, Any],
    current_op: dict[str, Any],
    label: str,
    breaking: list[str],
) -> None:
    # -- Request body --
    frozen_body = frozen_op.get("requestBody")
    current_body = current_op.get("requestBody")
    if frozen_body:
        if not current_body:
            breaking.append(f"REQUEST BODY REMOVED: {label}")
        else:
            _check_schema_properties(
                _get_json_schema(frozen_spec, frozen_body),
                _get_json_schema(current_spec, current_body),
                f"{label} requestBody",
                breaking,
            )

    # -- Responses (200 / 201) --
    for code in ("200", "201"):
        frozen_resp = (frozen_op.get("responses") or {}).get(code)
        current_resp = (current_op.get("responses") or {}).get(code)
        if not frozen_resp:
            continue
        if not current_resp:
            breaking.append(f"RESPONSE {code} REMOVED: {label}")
            continue
        frozen_json = (frozen_resp.get("content") or {}).get("application/json")
        current_json = (current_resp.get("content") or {}).get("application/json")
        if frozen_json and not current_json:
            breaking.append(f"RESPONSE BODY REMOVED: {label} [{code}]")
            continue
        if frozen_json and current_json:
            _check_schema_properties(
                _inline(frozen_spec, frozen_json.get("schema") or {}),
                _inline(current_spec, current_json.get("schema") or {}),
                f"{label} response[{code}]",
                breaking,
            )

    # -- Path/query parameters --
    frozen_params = {
        p["name"]: p
        for p in (frozen_op.get("parameters") or [])
        if isinstance(p, dict) and p.get("required")
    }
    current_params = {
        p["name"]: p
        for p in (current_op.get("parameters") or [])
        if isinstance(p, dict)
    }
    for name in frozen_params:
        if name in {"args", "kwargs"}:
            # Historical specs captured decorator implementation details from
            # wrappers. These were never public query parameters.
            continue
        if name not in current_params:
            breaking.append(f"REQUIRED PARAMETER REMOVED: {label} ?{name}")


def _diff_specs(
    frozen: dict[str, Any],
    current: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Return (breaking_changes, additive_changes)."""
    breaking: list[str] = []
    additive: list[str] = []

    frozen_paths: dict[str, Any] = frozen.get("paths") or {}
    current_paths: dict[str, Any] = current.get("paths") or {}

    # Removed paths
    for path, frozen_path_item in frozen_paths.items():
        if path not in current_paths:
            breaking.append(f"PATH REMOVED: {path}")
            continue

        current_path_item = current_paths[path]

        for method in _HTTP_METHODS:
            if method not in frozen_path_item:
                continue
            if method not in current_path_item:
                breaking.append(f"OPERATION REMOVED: {method.upper()} {path}")
                continue
            _check_operation(
                frozen,
                current,
                frozen_path_item[method],
                current_path_item[method],
                f"{method.upper()} {path}",
                breaking,
            )

    # Added paths / operations (additive — OK)
    for path, current_path_item in current_paths.items():
        if path not in frozen_paths:
            additive.append(f"PATH ADDED: {path}")
            continue
        frozen_path_item = frozen_paths[path]
        for method in _HTTP_METHODS:
            if method in current_path_item and method not in frozen_path_item:
                additive.append(f"OPERATION ADDED: {method.upper()} {path}")

    return breaking, additive


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    repo_root = _find_repo_root()
    frozen_path = repo_root / "api-contracts" / "zroky-api-v1.openapi.json"

    if not frozen_path.exists():
        print(f"::error::Frozen spec not found: {frozen_path}")
        return 1

    print("API v1 contract freeze check (ZROKY-006)")
    print(f"  Frozen spec : {frozen_path.relative_to(repo_root).as_posix()}")

    with frozen_path.open(encoding="utf-8") as f:
        frozen_spec: dict[str, Any] = json.load(f)

    print("  Generating current spec from app code…")
    try:
        current_spec = _generate_current_spec(repo_root)
    except Exception as exc:
        print(f"::error::Failed to generate current spec: {exc}")
        return 1

    frozen_paths_count = len(frozen_spec.get("paths") or {})
    current_paths_count = len(current_spec.get("paths") or {})
    print(f"  Frozen  : {frozen_paths_count} paths")
    print(f"  Current : {current_paths_count} paths")
    print()

    breaking, additive = _diff_specs(frozen_spec, current_spec)

    if additive:
        print(f"Additive changes ({len(additive)}) — OK, no action required:")
        for msg in additive:
            print(f"  [add]  {msg}")
        print()

    if breaking:
        print(f"::error::Breaking changes detected ({len(breaking)}):")
        for msg in breaking:
            print(f"  [BREAK] {msg}")
        print()
        print("To fix: either revert the breaking change OR update the frozen spec")
        print(f"        by running:  python zroky-backend/scripts/export_openapi.py")
        print(f"        and committing {frozen_path.relative_to(repo_root).as_posix()}")
        print(f"        with a BREAKING-CHANGE note in the commit message.")
        return 1

    print(f"OK — no breaking changes detected. ({len(additive)} additive change(s) allowed.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
