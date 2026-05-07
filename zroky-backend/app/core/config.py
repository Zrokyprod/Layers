from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "zroky-backend"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    PORT: int = 8000

    DATABASE_URL: str = "sqlite:///./.data/zroky.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    OPENROUTER_API_KEY: Optional[str] = None

    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None

    ENABLE_READY_DB_CHECK: bool = True
    ENABLE_READY_REDIS_CHECK: bool = True
    ENABLE_METRICS_ENDPOINT: bool = True
    METRICS_TOKEN_HEADER_NAME: str = "x-zroky-metrics-token"
    METRICS_TOKEN: Optional[str] = None
    ENABLE_INTERNAL_DEBUG_ENDPOINT: bool = False
    INTERNAL_DEBUG_TOKEN_HEADER_NAME: str = "x-zroky-internal-token"
    INTERNAL_DEBUG_TOKEN: Optional[str] = None

    IDEMPOTENCY_TTL_SECONDS: int = 600
    DIAGNOSIS_TASK_MAX_RETRIES: int = 3
    DIAGNOSIS_TASK_RETRY_BASE_SECONDS: int = 2
    DIAGNOSIS_TASK_RETRY_MAX_SECONDS: int = 30
    READ_ONLY_SHARE_TOKEN_TTL_SECONDS: int = 86400
    RETENTION_ENFORCEMENT_ENABLED: bool = True
    RETENTION_ENFORCEMENT_CRON_MINUTE: int = 0
    RETENTION_ENFORCEMENT_CRON_HOUR: int = 3
    RETENTION_PURGE_BATCH_SIZE: int = 500
    RETENTION_PURGE_DRY_RUN: bool = False

    INGEST_ENFORCE_RATE_LIMIT: bool = True
    INGEST_SOFT_LIMIT_RPM: int = 120
    INGEST_BURST_LIMIT_RPM: int = 240
    INGEST_RATE_LIMIT_WINDOW_SECONDS: int = 60
    INGEST_SUSTAINED_BREACH_THRESHOLD: int = 3
    INGEST_BACKPRESSURE_TTL_SECONDS: int = 300

    PROVIDER_STATUS_FETCH_TIMEOUT_MS: int = 800
    PROVIDER_STATUS_CACHE_TTL_SECONDS: int = 300
    PROVIDER_STATUS_ENDPOINTS_JSON: str = "{}"
    EXCHANGE_RATE_ENABLE_LIVE_FETCH: bool = True
    EXCHANGE_RATE_PROVIDER_URL: str = "https://api.exchangerate.host/latest?base=USD&symbols=INR"
    EXCHANGE_RATE_PROVIDER_SOURCE: str = "live_exchangerate_host"
    EXCHANGE_RATE_FETCH_TIMEOUT_MS: int = 800
    EXCHANGE_RATE_REFRESH_INTERVAL_MINUTES: int = 30
    EXCHANGE_RATE_CACHE_TTL_SECONDS: int = 3600
    EXCHANGE_RATE_FAILURE_CACHE_TTL_SECONDS: int = 300
    EXCHANGE_RATE_MAX_STALE_SECONDS: int = 86400
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # ── OpenRouter / DeepSeek settings ─────────────────────
    # Primary model for diagnosis/fix generation (DeepSeek — best for code)
    OPENROUTER_PRIMARY_MODEL: str = "deepseek/deepseek-chat"
    # Fallback model when primary is down / rate-limited
    OPENROUTER_FALLBACK_MODEL: str = "deepseek/deepseek-chat-v3"
    # Assistant chat model (Gemini 2.5 Flash — fast, large context, reliable tool-use)
    OPENROUTER_ASSISTANT_MODEL: str = "google/gemini-2.5-flash"
    # NL analytics model (GPT-4o-mini — most reliable structured JSON output)
    OPENROUTER_ANALYTICS_MODEL: str = "openai/gpt-4o-mini"
    # Request timeout for OpenRouter calls
    OPENROUTER_REQUEST_TIMEOUT_SECONDS: int = 60

    TENANT_HEADER_NAME: str = "x-project-id"
    LEGACY_TENANT_HEADER_NAME: str = "x-tenant-id"
    ACCEPT_LEGACY_TENANT_HEADER: bool = True
    # SECURITY: must be False in production — setting True lets any caller claim owner context
    ALLOW_PROJECT_HEADER_CONTEXT: bool = False
    API_KEY_HEADER_NAME: str = "x-api-key"
    ACCEPT_BEARER_AS_API_KEY: bool = True

    JWT_ISSUER: Optional[str] = None
    JWT_AUDIENCE: Optional[str] = None
    JWT_JWKS_URL: Optional[str] = None
    JWT_SIGNING_KEY: Optional[str] = None
    JWT_ALGORITHMS: str = "RS256"
    JWT_PROJECT_CLAIM: str = "project_id"
    JWT_PROJECTS_CLAIM: str = "projects"
    JWT_ROLES_CLAIM: str = "roles"
    JWT_ADMIN_ROLE: str = "zroky_admin"
    ALLOW_JWT_PROVISIONING_ACCESS: bool = True
    ENFORCE_JWT_PROJECT_MEMBERSHIP: bool = False

    # SECURITY: must be True in production — setting False lets anyone call provisioning endpoints
    REQUIRE_PROVISIONING_TOKEN: bool = True
    PROVISIONING_TOKEN_HEADER_NAME: str = "x-zroky-admin-token"
    PROVISIONING_TOKEN: Optional[str] = None

    # Comma-separated list of allowed CORS origins (required in production)
    ALLOWED_ORIGINS: str = ""
    # Comma-separated list of trusted Host header values (required in production)
    TRUSTED_HOSTS: str = ""

    # Optional read-replica URL (e.g. read-only Postgres replica).
    # When unset, reads fall back to the primary DATABASE_URL.
    DATABASE_READ_REPLICA_URL: Optional[str] = None

    # Connection pool sizing (Postgres only — SQLite uses default StaticPool).
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT_SECONDS: int = 30
    DB_POOL_RECYCLE_SECONDS: int = 1800
    DB_STATEMENT_TIMEOUT_MS: int = 30_000

    # Responsible-disclosure contact (security.txt / /.well-known/security.txt)
    SECURITY_CONTACT_EMAIL: str = "security@zroky.ai"
    SECURITY_PGP_KEY_URL: str = "https://zroky.ai/pgp-key.txt"

    DEPLOY_TARGET: str = "railway"
    APP_DOMAIN: Optional[str] = None
    GCP_PROJECT_ID: Optional[str] = None
    GCP_REGION: str = "us-central1"

    # Email/password auth
    AUTH_JWT_SECRET: Optional[str] = None
    AUTH_JWT_EXPIRE_HOURS: int = 72
    AUTH_REFRESH_TOKEN_EXPIRE_HOURS: int = 24 * 30
    AUTH_BCRYPT_ROUNDS: int = 12

    # GitHub OAuth
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GITHUB_OAUTH_REDIRECT_URL: str = "http://localhost:3000/auth/github/callback"
    GITHUB_CONNECT_OAUTH_REDIRECT_URL: str = "http://localhost:3000/auth/github/connect/callback"
    GITHUB_REPO_OAUTH_SCOPES: str = "repo read:user user:email"
    GITHUB_TOKEN_ENCRYPTION_KEY: Optional[str] = None
    # Column-level encryption for PII fields (emails, tokens)
    # Can reuse GITHUB_TOKEN_ENCRYPTION_KEY if not set separately
    PII_ENCRYPTION_KEY: Optional[str] = None
    # Separate HMAC key for searchable encrypted fields (deterministic hashing)
    # If not set, falls back to PII_ENCRYPTION_KEY or GITHUB_TOKEN_ENCRYPTION_KEY
    PII_HMAC_KEY: Optional[str] = None
    GITHUB_PR_BOT_TOKEN: Optional[str] = None
    GITHUB_PR_DEFAULT_OWNER: Optional[str] = None
    GITHUB_PR_DEFAULT_REPO: Optional[str] = None
    GITHUB_PR_DEFAULT_BASE_BRANCH: str = "main"
    GITHUB_WEBHOOK_SECRET: Optional[str] = None

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_OAUTH_REDIRECT_URL: str = "http://localhost:3000/auth/google/callback"

    # Frontend Settings
    FRONTEND_URL: str = "http://localhost:3000"
    # State HMAC key for CSRF protection — defaults to AUTH_JWT_SECRET if not set
    OAUTH_STATE_SECRET: Optional[str] = None

    # SMTP / email notifications
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    ALERTS_FROM_EMAIL: str = "noreply@zroky.ai"

    # Slack Incoming Webhook for alert notifications
    SLACK_WEBHOOK_URL: Optional[str] = None

    # Weekly developer impact email (Celery beat)
    WEEKLY_IMPACT_EMAIL_ENABLED: bool = False
    WEEKLY_IMPACT_EMAIL_CRON_DAY_OF_WEEK: int = 1  # 1 = Monday (0=Sunday … 6=Saturday)
    WEEKLY_IMPACT_EMAIL_CRON_HOUR: int = 8

    @property
    def effective_celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def effective_celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL


def is_production_env(app_env: str) -> bool:
    return app_env.strip().lower() in {"prod", "production"}


def validate_runtime_settings(settings: Settings) -> None:
    if not is_production_env(settings.APP_ENV):
        return

    failures: list[str] = []

    if settings.ALLOW_PROJECT_HEADER_CONTEXT:
        failures.append("ALLOW_PROJECT_HEADER_CONTEXT must be false in production")

    if not settings.REQUIRE_PROVISIONING_TOKEN:
        failures.append("REQUIRE_PROVISIONING_TOKEN must be true in production")

    if settings.REQUIRE_PROVISIONING_TOKEN and not settings.PROVISIONING_TOKEN:
        failures.append("PROVISIONING_TOKEN must be configured when provisioning token is required")

    if not settings.ENABLE_READY_DB_CHECK:
        failures.append("ENABLE_READY_DB_CHECK must be true in production")

    if not settings.ENABLE_READY_REDIS_CHECK:
        failures.append("ENABLE_READY_REDIS_CHECK must be true in production")

    if settings.EXCHANGE_RATE_ENABLE_LIVE_FETCH and not settings.EXCHANGE_RATE_PROVIDER_URL.strip():
        failures.append("EXCHANGE_RATE_PROVIDER_URL must be configured when live FX fetch is enabled")

    if settings.ENABLE_INTERNAL_DEBUG_ENDPOINT and not (settings.INTERNAL_DEBUG_TOKEN or "").strip():
        failures.append("INTERNAL_DEBUG_TOKEN must be configured when internal debug endpoint is enabled")

    if is_jwt_configured(settings):
        if not settings.JWT_ISSUER:
            failures.append("JWT_ISSUER must be configured when JWT auth is enabled in production")
        if not settings.JWT_AUDIENCE:
            failures.append("JWT_AUDIENCE must be configured when JWT auth is enabled in production")
        if not settings.ENFORCE_JWT_PROJECT_MEMBERSHIP:
            failures.append(
                "ENFORCE_JWT_PROJECT_MEMBERSHIP must be true when JWT auth is enabled in production"
            )

    # PII encryption should be configured in production
    if not (settings.PII_ENCRYPTION_KEY or settings.GITHUB_TOKEN_ENCRYPTION_KEY):
        failures.append("PII_ENCRYPTION_KEY or GITHUB_TOKEN_ENCRYPTION_KEY must be configured in production for PII protection")

    if failures:
        raise RuntimeError("Invalid production configuration: " + "; ".join(failures))


def is_jwt_configured(settings: Settings) -> bool:
    return bool(settings.JWT_JWKS_URL or settings.JWT_SIGNING_KEY)


@lru_cache
def get_settings() -> Settings:
    return Settings()
