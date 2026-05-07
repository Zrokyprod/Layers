import pytest

from app.core.config import Settings, validate_runtime_settings


def test_production_config_rejects_insecure_defaults() -> None:
    settings = Settings(
        APP_ENV="production",
        ALLOW_PROJECT_HEADER_CONTEXT=True,
        REQUIRE_PROVISIONING_TOKEN=False,
        PROVISIONING_TOKEN=None,
        ENABLE_READY_DB_CHECK=False,
        ENABLE_READY_REDIS_CHECK=False,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    error_text = str(exc.value)
    assert "ALLOW_PROJECT_HEADER_CONTEXT" in error_text
    assert "REQUIRE_PROVISIONING_TOKEN" in error_text
    assert "ENABLE_READY_DB_CHECK" in error_text
    assert "ENABLE_READY_REDIS_CHECK" in error_text


def test_production_config_accepts_hardened_profile() -> None:
    settings = Settings(
        APP_ENV="production",
        ALLOW_PROJECT_HEADER_CONTEXT=False,
        REQUIRE_PROVISIONING_TOKEN=True,
        PROVISIONING_TOKEN="super-secret",
        ENABLE_READY_DB_CHECK=True,
        ENABLE_READY_REDIS_CHECK=True,
    )

    validate_runtime_settings(settings)


def test_non_production_config_skips_strict_guard() -> None:
    settings = Settings(APP_ENV="development")
    validate_runtime_settings(settings)


def test_production_config_rejects_incomplete_jwt_hardening() -> None:
    settings = Settings(
        APP_ENV="production",
        ALLOW_PROJECT_HEADER_CONTEXT=False,
        REQUIRE_PROVISIONING_TOKEN=True,
        PROVISIONING_TOKEN="super-secret",
        ENABLE_READY_DB_CHECK=True,
        ENABLE_READY_REDIS_CHECK=True,
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
    settings = Settings(
        APP_ENV="production",
        ALLOW_PROJECT_HEADER_CONTEXT=False,
        REQUIRE_PROVISIONING_TOKEN=True,
        PROVISIONING_TOKEN="super-secret",
        ENABLE_READY_DB_CHECK=True,
        ENABLE_READY_REDIS_CHECK=True,
        JWT_JWKS_URL="https://example.com/.well-known/jwks.json",
        JWT_ISSUER="https://issuer.example.com/",
        JWT_AUDIENCE="zroky-api",
        ENFORCE_JWT_PROJECT_MEMBERSHIP=True,
    )

    validate_runtime_settings(settings)


def test_production_config_rejects_internal_debug_without_token() -> None:
    settings = Settings(
        APP_ENV="production",
        ALLOW_PROJECT_HEADER_CONTEXT=False,
        REQUIRE_PROVISIONING_TOKEN=True,
        PROVISIONING_TOKEN="super-secret",
        ENABLE_READY_DB_CHECK=True,
        ENABLE_READY_REDIS_CHECK=True,
        ENABLE_INTERNAL_DEBUG_ENDPOINT=True,
        INTERNAL_DEBUG_TOKEN=None,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    assert "INTERNAL_DEBUG_TOKEN" in str(exc.value)


def test_production_config_accepts_internal_debug_with_token() -> None:
    settings = Settings(
        APP_ENV="production",
        ALLOW_PROJECT_HEADER_CONTEXT=False,
        REQUIRE_PROVISIONING_TOKEN=True,
        PROVISIONING_TOKEN="super-secret",
        ENABLE_READY_DB_CHECK=True,
        ENABLE_READY_REDIS_CHECK=True,
        ENABLE_INTERNAL_DEBUG_ENDPOINT=True,
        INTERNAL_DEBUG_TOKEN="internal-debug-secret",
    )

    validate_runtime_settings(settings)
