import pytest

from app.core.config import Settings, validate_runtime_settings


def _hardened_production_settings(**overrides: object) -> Settings:
    values = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://zroky:secret@db.example.com:5432/zroky",
        "REDIS_URL": "redis://redis.example.com:6379/0",
        "ALLOWED_ORIGINS": "https://app.zroky.ai",
        "TRUSTED_HOSTS": "api.zroky.ai",
        "FRONTEND_URL": "https://app.zroky.ai",
        "ALLOW_PROJECT_HEADER_CONTEXT": False,
        "REQUIRE_PROVISIONING_TOKEN": True,
        "PROVISIONING_TOKEN": "super-secret",
        "ENABLE_READY_DB_CHECK": True,
        "ENABLE_READY_REDIS_CHECK": True,
        "BILLING_ENFORCE_QUOTA": True,
        "REPLAY_REAL_LLM_ENABLED": True,
        "METRICS_TOKEN": "metrics-secret",
        "AUTH_JWT_SECRET": "auth-secret-with-enough-entropy",
        "PII_ENCRYPTION_KEY": "x" * 32,
        "JWT_JWKS_URL": None,
        "JWT_SIGNING_KEY": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_production_config_rejects_insecure_defaults() -> None:
    settings = Settings(
        APP_ENV="production",
        ALLOW_PROJECT_HEADER_CONTEXT=True,
        REQUIRE_PROVISIONING_TOKEN=False,
        PROVISIONING_TOKEN=None,
        ENABLE_READY_DB_CHECK=False,
        ENABLE_READY_REDIS_CHECK=False,
        AUTH_JWT_SECRET=None,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    error_text = str(exc.value)
    assert "ALLOW_PROJECT_HEADER_CONTEXT" in error_text
    assert "REQUIRE_PROVISIONING_TOKEN" in error_text
    assert "ENABLE_READY_DB_CHECK" in error_text
    assert "ENABLE_READY_REDIS_CHECK" in error_text
    assert "DATABASE_URL" in error_text
    assert "REDIS_URL" in error_text
    assert "ALLOWED_ORIGINS" in error_text
    assert "TRUSTED_HOSTS" in error_text
    assert "FRONTEND_URL" in error_text
    assert "METRICS_TOKEN" in error_text
    assert "AUTH_JWT_SECRET" in error_text
    assert "BILLING_ENFORCE_QUOTA" in error_text
    assert "REPLAY_REAL_LLM_ENABLED" in error_text


def test_production_config_accepts_hardened_profile() -> None:
    settings = _hardened_production_settings()

    validate_runtime_settings(settings)


def test_production_config_rejects_wildcard_cors() -> None:
    settings = _hardened_production_settings(ALLOWED_ORIGINS="*")

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    assert "ALLOWED_ORIGINS" in str(exc.value)


def test_non_production_config_skips_strict_guard() -> None:
    settings = Settings(APP_ENV="development")
    validate_runtime_settings(settings)


def test_production_config_rejects_incomplete_jwt_hardening() -> None:
    settings = _hardened_production_settings(
        JWT_JWKS_URL="https://example.com/.well-known/jwks.json",
        JWT_ISSUER=None,
        JWT_AUDIENCE=None,
        ENFORCE_JWT_PROJECT_MEMBERSHIP=False,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    error_text = str(exc.value)
    assert "JWT_ISSUER" in error_text
    assert "JWT_AUDIENCE" in error_text
    assert "ENFORCE_JWT_PROJECT_MEMBERSHIP" in error_text


def test_production_config_accepts_hardened_jwt_profile() -> None:
    settings = _hardened_production_settings(
        JWT_JWKS_URL="https://example.com/.well-known/jwks.json",
        JWT_ISSUER="https://issuer.example.com/",
        JWT_AUDIENCE="zroky-api",
        ENFORCE_JWT_PROJECT_MEMBERSHIP=True,
    )

    validate_runtime_settings(settings)


def test_production_config_rejects_internal_debug_without_token() -> None:
    settings = _hardened_production_settings(
        ENABLE_INTERNAL_DEBUG_ENDPOINT=True,
        INTERNAL_DEBUG_TOKEN=None,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    assert "INTERNAL_DEBUG_TOKEN" in str(exc.value)


def test_production_config_accepts_internal_debug_with_token() -> None:
    settings = _hardened_production_settings(
        ENABLE_INTERNAL_DEBUG_ENDPOINT=True,
        INTERNAL_DEBUG_TOKEN="internal-debug-secret",
    )

    validate_runtime_settings(settings)


def test_production_config_rejects_enabled_metrics_without_token() -> None:
    settings = _hardened_production_settings(
        ENABLE_METRICS_ENDPOINT=True,
        METRICS_TOKEN=None,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    assert "METRICS_TOKEN" in str(exc.value)


def test_production_config_rejects_missing_session_secret() -> None:
    settings = _hardened_production_settings(
        AUTH_JWT_SECRET=None,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    assert "AUTH_JWT_SECRET" in str(exc.value)
