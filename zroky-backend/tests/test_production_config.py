import pytest

from app.core.config import Settings, validate_runtime_settings


def _hardened_production_settings(**overrides: object) -> Settings:
    values = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://zroky:secret@db.example.com:5432/zroky",
        "REDIS_URL": "redis://redis.example.com:6379/0",
        "ALLOWED_ORIGINS": "https://app.zroky.com",
        "TRUSTED_HOSTS": "api.zroky.com",
        "FRONTEND_URL": "https://app.zroky.com",
        "ALLOW_PROJECT_HEADER_CONTEXT": False,
        "REQUIRE_PROVISIONING_TOKEN": True,
        "PROVISIONING_TOKEN": "super-secret",
        "ENABLE_READY_DB_CHECK": True,
        "ENABLE_READY_REDIS_CHECK": True,
        "BILLING_ENFORCE_QUOTA": True,
        "REPLAY_REAL_LLM_ENABLED": True,
        "REPLAY_WORKER_TOKEN": "replay-worker-secret",
        "OPENROUTER_API_KEY": "openrouter-secret-with-enough-length",
        "METRICS_TOKEN": "metrics-secret",
        "AUTH_JWT_SECRET": "auth-secret-with-enough-entropy",
        "OAUTH_STATE_SECRET": "oauth-state-secret-with-enough-entropy",
        "GITHUB_WEBHOOK_SECRET": "github-webhook-secret",
        "PROVIDER_KEY_VAULT_KEK": "x" * 32,
        "PII_ENCRYPTION_KEY": "x" * 32,
        "BILLING_PROVIDER": "razorpay",
        "RAZORPAY_KEY_ID": "rzp_live_real_key",
        "RAZORPAY_KEY_SECRET": "razorpay-live-secret-with-enough-length",
        "RAZORPAY_WEBHOOK_SECRET": "razorpay-webhook-secret-with-enough-length",
        "BILLING_CHECKOUT_SUCCESS_URL": "https://app.zroky.com/settings/billing?checkout=success",
        "BILLING_CHECKOUT_CANCEL_URL": "https://app.zroky.com/settings/billing?checkout=cancel",
        "BILLING_PORTAL_RETURN_URL": "https://app.zroky.com/settings/billing",
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
        OAUTH_STATE_SECRET=None,
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
    assert "OAUTH_STATE_SECRET" in error_text
    assert "GITHUB_WEBHOOK_SECRET" in error_text
    assert "PROVIDER_KEY_VAULT_KEK" in error_text
    assert "OPENROUTER_API_KEY or OPENAI_API_KEY" in error_text
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
        PII_ENCRYPTION_KEY="x" * 32,
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
        PII_ENCRYPTION_KEY="x" * 32,
    )

    validate_runtime_settings(settings)


def test_production_config_rejects_enabled_razorpay_billing_without_keys_direct_settings() -> None:
    settings = Settings(
        APP_ENV="production",
        ALLOW_PROJECT_HEADER_CONTEXT=False,
        REQUIRE_PROVISIONING_TOKEN=True,
        PROVISIONING_TOKEN="super-secret",
        ENABLE_READY_DB_CHECK=True,
        ENABLE_READY_REDIS_CHECK=True,
        BILLING_ENABLED=True,
        BILLING_PROVIDER="razorpay",
        RAZORPAY_KEY_ID=None,
        RAZORPAY_KEY_SECRET=None,
        RAZORPAY_WEBHOOK_SECRET=None,
        PII_ENCRYPTION_KEY="x" * 32,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    error_text = str(exc.value)
    assert "RAZORPAY_KEY_ID" in error_text
    assert "RAZORPAY_KEY_SECRET" in error_text


def test_production_config_accepts_enabled_razorpay_billing_without_webhook_secret_direct_settings() -> None:
    settings = _hardened_production_settings(
        BILLING_ENABLED=True,
        BILLING_PROVIDER="razorpay",
        RAZORPAY_KEY_ID="rzp_live_real_key",
        RAZORPAY_KEY_SECRET="razorpay-live-secret-with-enough-length",
        RAZORPAY_WEBHOOK_SECRET=None,
    )

    validate_runtime_settings(settings)


def test_production_config_rejects_razorpay_test_key_and_local_checkout_urls() -> None:
    settings = _hardened_production_settings(
        BILLING_ENABLED=True,
        BILLING_PROVIDER="razorpay",
        RAZORPAY_KEY_ID="rzp_test_not_for_paid_launch",
        BILLING_CHECKOUT_SUCCESS_URL="http://localhost:3000/settings/billing?checkout=success",
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    error_text = str(exc.value)
    assert "RAZORPAY_KEY_ID must use a live Razorpay key prefix rzp_live_" in error_text
    assert "BILLING_CHECKOUT_SUCCESS_URL" in error_text


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


def test_production_config_rejects_placeholder_secret_values() -> None:
    settings = _hardened_production_settings(
        AUTH_JWT_SECRET="__SET_IN_SECRET_MANAGER__",
        PII_ENCRYPTION_KEY="replace-with-32-char-random-secret-here",
        OPENROUTER_API_KEY="__SET_IN_SECRET_MANAGER__",
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    error_text = str(exc.value)
    assert "AUTH_JWT_SECRET" in error_text
    assert "PII_ENCRYPTION_KEY" in error_text
    assert "OPENROUTER_API_KEY or OPENAI_API_KEY" in error_text


def test_production_config_rejects_missing_github_webhook_secret() -> None:
    settings = _hardened_production_settings(
        GITHUB_WEBHOOK_SECRET=None,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    assert "GITHUB_WEBHOOK_SECRET" in str(exc.value)


def test_production_config_rejects_missing_provider_key_vault_kek() -> None:
    settings = _hardened_production_settings(
        PROVIDER_KEY_VAULT_KEK=None,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    assert "PROVIDER_KEY_VAULT_KEK" in str(exc.value)


def test_production_config_rejects_short_provider_key_vault_kek() -> None:
    settings = _hardened_production_settings(
        PROVIDER_KEY_VAULT_KEK="short",
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    assert "PROVIDER_KEY_VAULT_KEK" in str(exc.value)


def test_production_config_rejects_missing_replay_worker_token() -> None:
    settings = _hardened_production_settings(
        REPLAY_WORKER_TOKEN=None,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    assert "REPLAY_WORKER_TOKEN" in str(exc.value)


def test_production_config_rejects_missing_platform_llm_key() -> None:
    settings = _hardened_production_settings(
        OPENROUTER_API_KEY=None,
        OPENAI_API_KEY=None,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    assert "OPENROUTER_API_KEY or OPENAI_API_KEY" in str(exc.value)


def test_production_config_rejects_non_razorpay_billing_provider() -> None:
    settings = _hardened_production_settings(
        BILLING_ENABLED=True,
        BILLING_PROVIDER="paypal",
        RAZORPAY_KEY_ID="rzp_live_real_key",
        RAZORPAY_KEY_SECRET="razorpay-live-secret-with-enough-length",
        RAZORPAY_WEBHOOK_SECRET="razorpay-webhook-secret-with-enough-length",
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    assert "BILLING_PROVIDER must be razorpay" in str(exc.value)


def test_production_config_rejects_enabled_razorpay_billing_without_keys() -> None:
    settings = _hardened_production_settings(
        BILLING_ENABLED=True,
        BILLING_PROVIDER="razorpay",
        RAZORPAY_KEY_ID=None,
        RAZORPAY_KEY_SECRET=None,
        RAZORPAY_WEBHOOK_SECRET=None,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    error_text = str(exc.value)
    assert "RAZORPAY_KEY_ID" in error_text
    assert "RAZORPAY_KEY_SECRET" in error_text


def test_production_config_accepts_enabled_razorpay_billing_without_webhook_secret() -> None:
    settings = _hardened_production_settings(
        BILLING_ENABLED=True,
        BILLING_PROVIDER="razorpay",
        RAZORPAY_KEY_ID="rzp_live_real_key",
        RAZORPAY_KEY_SECRET="razorpay-live-secret-with-enough-length",
        RAZORPAY_WEBHOOK_SECRET=None,
    )

    validate_runtime_settings(settings)


def test_production_config_rejects_partial_slack_integration_config() -> None:
    settings = _hardened_production_settings(
        SLACK_CLIENT_ID="slack-client-id",
        SLACK_CLIENT_SECRET=None,
        SLACK_TOKEN_ENCRYPTION_KEY=None,
        SLACK_SIGNING_SECRET=None,
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    error_text = str(exc.value)
    assert "SLACK_CLIENT_SECRET" in error_text


def test_production_config_accepts_slack_oauth_client_pair_without_runtime_secrets() -> None:
    settings = _hardened_production_settings(
        SLACK_CLIENT_ID="slack-client-id",
        SLACK_CLIENT_SECRET="slack-client-secret",
        SLACK_TOKEN_ENCRYPTION_KEY=None,
        SLACK_SIGNING_SECRET=None,
    )

    validate_runtime_settings(settings)


def test_production_config_rejects_placeholder_optional_integration_secrets() -> None:
    settings = _hardened_production_settings(
        RAZORPAY_WEBHOOK_SECRET="fake-webhook-secret",
        SLACK_TOKEN_ENCRYPTION_KEY="dummy-slack-token-key",
        SLACK_SIGNING_SECRET="change-me-slack-signing-secret",
    )

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(settings)

    error_text = str(exc.value)
    assert "RAZORPAY_WEBHOOK_SECRET" in error_text
    assert "SLACK_TOKEN_ENCRYPTION_KEY" in error_text
    assert "SLACK_SIGNING_SECRET" in error_text
