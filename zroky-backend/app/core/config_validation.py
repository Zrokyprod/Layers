from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def is_production_env(app_env: str) -> bool:
    return app_env.strip().lower() in {"prod", "production"}


def _hostname(value: str | None) -> str:
    if not value:
        return ""
    return (urlparse(value).hostname or "").lower()


def _is_local_url(value: str | None) -> bool:
    return _hostname(value) in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _is_placeholder_secret(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return any(
        marker in normalized
        for marker in (
            "__set_in_secret_manager__",
            "replace-with",
            "change-me",
            "changeme",
            "dummy",
            "fake",
        )
    )


def validate_runtime_settings(settings: Any) -> None:
    if not is_production_env(settings.APP_ENV):
        return

    failures: list[str] = []

    def require_secret(name: str, message: str, *, min_length: int | None = None) -> str:
        value = (getattr(settings, name, None) or "").strip()
        if not value:
            failures.append(message)
            return ""
        if _is_placeholder_secret(value):
            failures.append(f"{name} must be set to a real production secret, not a placeholder")
            return value
        if min_length is not None and len(value) < min_length:
            failures.append(f"{name} must be at least {min_length} characters in production")
        return value

    def validate_optional_secret(name: str, *, min_length: int | None = None) -> str:
        value = (getattr(settings, name, None) or "").strip()
        if not value:
            return ""
        if _is_placeholder_secret(value):
            failures.append(f"{name} must be set to a real production secret, not a placeholder")
            return value
        if min_length is not None and len(value) < min_length:
            failures.append(f"{name} must be at least {min_length} characters in production")
        return value

    if settings.DATABASE_URL.startswith("sqlite"):
        failures.append("DATABASE_URL must point to managed PostgreSQL in production")

    if _is_local_url(settings.REDIS_URL):
        failures.append("REDIS_URL must point to managed Redis in production")

    allowed_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    if not allowed_origins:
        failures.append("ALLOWED_ORIGINS must be configured in production")
    elif any(origin == "*" for origin in allowed_origins):
        failures.append("ALLOWED_ORIGINS cannot use wildcard in production")
    elif any(_is_local_url(origin) for origin in allowed_origins):
        failures.append("ALLOWED_ORIGINS cannot include localhost in production")

    trusted_hosts = [h.strip().lower() for h in settings.TRUSTED_HOSTS.split(",") if h.strip()]
    if not trusted_hosts:
        failures.append("TRUSTED_HOSTS must be configured in production")
    elif any(host in {"*", "localhost", "127.0.0.1", "::1"} for host in trusted_hosts):
        failures.append("TRUSTED_HOSTS cannot use wildcard or localhost in production")

    if _is_local_url(settings.FRONTEND_URL):
        failures.append("FRONTEND_URL must point to the production dashboard URL")

    if settings.ALLOW_PROJECT_HEADER_CONTEXT:
        failures.append("ALLOW_PROJECT_HEADER_CONTEXT must be false in production")

    if not settings.REQUIRE_PROVISIONING_TOKEN:
        failures.append("REQUIRE_PROVISIONING_TOKEN must be true in production")

    if settings.REQUIRE_PROVISIONING_TOKEN:
        require_secret(
            "PROVISIONING_TOKEN",
            "PROVISIONING_TOKEN must be configured when provisioning token is required",
        )

    if not settings.ENABLE_READY_DB_CHECK:
        failures.append("ENABLE_READY_DB_CHECK must be true in production")

    if not settings.ENABLE_READY_REDIS_CHECK:
        failures.append("ENABLE_READY_REDIS_CHECK must be true in production")

    if not settings.BILLING_ENFORCE_QUOTA:
        failures.append("BILLING_ENFORCE_QUOTA must be true in production")
    if str(settings.BILLING_QUOTA_FAILURE_POLICY).strip().lower() != "strict":
        failures.append("BILLING_QUOTA_FAILURE_POLICY must be strict in production")

    if not settings.REPLAY_REAL_LLM_ENABLED:
        failures.append("REPLAY_REAL_LLM_ENABLED must be true in production")
    else:
        require_secret(
            "REPLAY_WORKER_TOKEN",
            "REPLAY_WORKER_TOKEN must be configured when real replay is enabled in production",
            min_length=16,
        )

    if settings.ENABLE_METRICS_ENDPOINT:
        require_secret(
            "METRICS_TOKEN",
            "METRICS_TOKEN must be configured when metrics endpoint is enabled in production",
        )

    if settings.ENABLE_INTERNAL_DEBUG_ENDPOINT:
        require_secret(
            "INTERNAL_DEBUG_TOKEN",
            "INTERNAL_DEBUG_TOKEN must be configured when internal debug endpoint is enabled",
        )

    require_secret("AUTH_JWT_SECRET", "AUTH_JWT_SECRET must be configured in production for dashboard session tokens")

    require_secret("OAUTH_STATE_SECRET", "OAUTH_STATE_SECRET must be configured in production for OAuth CSRF protection")

    require_secret(
        "GITHUB_WEBHOOK_SECRET",
        "GITHUB_WEBHOOK_SECRET must be configured in production for signed GitHub webhooks",
    )

    require_secret(
        "PROVIDER_KEY_VAULT_KEK",
        "PROVIDER_KEY_VAULT_KEK must be configured in production for provider key vault encryption",
        min_length=32,
    )

    platform_llm_key = (settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY or "").strip()
    if not platform_llm_key:
        failures.append("OPENROUTER_API_KEY or OPENAI_API_KEY must be configured in production for AI diagnosis and judgment")
    elif _is_placeholder_secret(platform_llm_key):
        failures.append("OPENROUTER_API_KEY or OPENAI_API_KEY must be set to a real production secret, not a placeholder")
    elif len(platform_llm_key) < 16:
        failures.append("OPENROUTER_API_KEY or OPENAI_API_KEY must be at least 16 characters in production")

    validate_optional_secret("RAZORPAY_WEBHOOK_SECRET")

    if settings.BILLING_ENABLED:
        if (settings.BILLING_PROVIDER or "").strip().lower() != "razorpay":
            failures.append("BILLING_PROVIDER must be razorpay in production")
        razorpay_key_id = require_secret(
            "RAZORPAY_KEY_ID",
            "RAZORPAY_KEY_ID must be configured when Razorpay billing is enabled in production",
        )
        if razorpay_key_id and not razorpay_key_id.startswith("rzp_live_"):
            failures.append("RAZORPAY_KEY_ID must use a live Razorpay key prefix rzp_live_ in production")
        require_secret(
            "RAZORPAY_KEY_SECRET",
            "RAZORPAY_KEY_SECRET must be configured when Razorpay billing is enabled in production",
        )
        for name in (
            "RAZORPAY_DASHBOARD_URL",
            "BILLING_CHECKOUT_SUCCESS_URL",
            "BILLING_CHECKOUT_CANCEL_URL",
            "BILLING_PORTAL_RETURN_URL",
        ):
            value = (getattr(settings, name, "") or "").strip()
            if not value:
                failures.append(f"{name} must be configured when Razorpay billing is enabled in production")
            elif _is_local_url(value):
                failures.append(f"{name} must point to a production URL when Razorpay billing is enabled")

    validate_optional_secret("SLACK_TOKEN_ENCRYPTION_KEY")
    validate_optional_secret("SLACK_SIGNING_SECRET")

    slack_configured = bool((settings.SLACK_CLIENT_ID or "").strip() or (settings.SLACK_CLIENT_SECRET or "").strip())
    if slack_configured:
        require_secret(
            "SLACK_CLIENT_ID",
            "SLACK_CLIENT_ID must be configured with Slack integration in production",
        )
        require_secret(
            "SLACK_CLIENT_SECRET",
            "SLACK_CLIENT_SECRET must be configured with Slack integration in production",
        )

    if is_jwt_configured(settings):
        if not settings.JWT_ISSUER:
            failures.append("JWT_ISSUER must be configured when JWT auth is enabled in production")
        if not settings.JWT_AUDIENCE:
            failures.append("JWT_AUDIENCE must be configured when JWT auth is enabled in production")
        if not settings.ENFORCE_JWT_PROJECT_MEMBERSHIP:
            failures.append(
                "ENFORCE_JWT_PROJECT_MEMBERSHIP must be true when JWT auth is enabled in production"
            )

    pii_encryption_key = (settings.PII_ENCRYPTION_KEY or "").strip()
    github_token_encryption_key = (settings.GITHUB_TOKEN_ENCRYPTION_KEY or "").strip()
    if not (pii_encryption_key or github_token_encryption_key):
        failures.append("PII_ENCRYPTION_KEY or GITHUB_TOKEN_ENCRYPTION_KEY must be configured in production for PII protection")
    if pii_encryption_key and _is_placeholder_secret(pii_encryption_key):
        failures.append("PII_ENCRYPTION_KEY must be set to a real production secret, not a placeholder")
    if github_token_encryption_key and _is_placeholder_secret(github_token_encryption_key):
        failures.append("GITHUB_TOKEN_ENCRYPTION_KEY must be set to a real production secret, not a placeholder")

    if failures:
        raise RuntimeError("Invalid production configuration: " + "; ".join(failures))


def is_jwt_configured(settings: Any) -> bool:
    return bool(settings.JWT_JWKS_URL or settings.JWT_SIGNING_KEY)
