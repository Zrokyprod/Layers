from __future__ import annotations

from app.api.routes._internal.owner_common import *
from app.core.config_validation import _is_local_url, _is_placeholder_secret, is_production_env


class ProductionReadinessCheck(BaseModel):
    code: str
    label: str
    status: str
    required_for_launch: bool
    detail: str


class ProductionReadinessResponse(BaseModel):
    overall_status: str
    app_env: str
    production_profile: bool
    hard_blockers: list[str]
    checks: list[ProductionReadinessCheck]
    checked_at: datetime


def _secret_configured(value: str | None, *, min_length: int | None = None) -> bool:
    clean = (value or "").strip()
    if not clean or _is_placeholder_secret(clean):
        return False
    if min_length is not None and len(clean) < min_length:
        return False
    return True


def _check(
    checks: list[ProductionReadinessCheck],
    *,
    code: str,
    label: str,
    ok: bool,
    detail: str,
    required_for_launch: bool = True,
    warn_only: bool = False,
) -> None:
    checks.append(
        ProductionReadinessCheck(
            code=code,
            label=label,
            status="pass" if ok else ("warn" if warn_only else "fail"),
            required_for_launch=required_for_launch,
            detail=detail,
        )
    )


@router.get("/production-readiness", response_model=ProductionReadinessResponse)
def owner_production_readiness(
    _: None = Depends(require_provisioning_access),
) -> ProductionReadinessResponse:
    settings = get_settings()
    checks: list[ProductionReadinessCheck] = []

    production_profile = is_production_env(settings.APP_ENV)
    _check(
        checks,
        code="app_env",
        label="Production profile",
        ok=production_profile,
        detail="APP_ENV is production/prod." if production_profile else "APP_ENV is not production/prod.",
    )
    _check(
        checks,
        code="database_url",
        label="Managed PostgreSQL",
        ok=not settings.DATABASE_URL.startswith("sqlite"),
        detail="DATABASE_URL is not SQLite." if not settings.DATABASE_URL.startswith("sqlite") else "DATABASE_URL is SQLite.",
    )
    _check(
        checks,
        code="redis_url",
        label="Managed Redis",
        ok=bool(settings.REDIS_URL) and not _is_local_url(settings.REDIS_URL),
        detail="REDIS_URL points to a non-local host." if not _is_local_url(settings.REDIS_URL) else "REDIS_URL points to localhost.",
    )

    allowed_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    origins_ok = bool(allowed_origins) and "*" not in allowed_origins and not any(_is_local_url(o) for o in allowed_origins)
    _check(
        checks,
        code="allowed_origins",
        label="Allowed origins",
        ok=origins_ok,
        detail="ALLOWED_ORIGINS is production-scoped." if origins_ok else "ALLOWED_ORIGINS is missing, wildcard, or local.",
    )

    trusted_hosts = [h.strip().lower() for h in settings.TRUSTED_HOSTS.split(",") if h.strip()]
    hosts_ok = bool(trusted_hosts) and not any(h in {"*", "localhost", "127.0.0.1", "::1"} for h in trusted_hosts)
    _check(
        checks,
        code="trusted_hosts",
        label="Trusted hosts",
        ok=hosts_ok,
        detail="TRUSTED_HOSTS is production-scoped." if hosts_ok else "TRUSTED_HOSTS is missing, wildcard, or local.",
    )

    _check(
        checks,
        code="owner_routes",
        label="Owner routes enabled",
        ok=bool(settings.FEATURE_LEGACY_OWNER),
        detail="FEATURE_LEGACY_OWNER is enabled for zroky-admin." if settings.FEATURE_LEGACY_OWNER else "FEATURE_LEGACY_OWNER is disabled; owner dashboard cannot reach backend owner APIs.",
    )
    _check(
        checks,
        code="project_header_context",
        label="Project header context locked",
        ok=not settings.ALLOW_PROJECT_HEADER_CONTEXT,
        detail="ALLOW_PROJECT_HEADER_CONTEXT is false." if not settings.ALLOW_PROJECT_HEADER_CONTEXT else "ALLOW_PROJECT_HEADER_CONTEXT lets callers claim project context.",
    )
    _check(
        checks,
        code="provisioning_token",
        label="Owner provisioning token",
        ok=settings.REQUIRE_PROVISIONING_TOKEN and _secret_configured(settings.PROVISIONING_TOKEN),
        detail="Owner token is required and configured." if settings.REQUIRE_PROVISIONING_TOKEN and _secret_configured(settings.PROVISIONING_TOKEN) else "Owner token is missing, placeholder, or not required.",
    )
    _check(
        checks,
        code="auth_jwt_secret",
        label="Dashboard session signing",
        ok=_secret_configured(settings.AUTH_JWT_SECRET, min_length=16),
        detail="AUTH_JWT_SECRET is configured." if _secret_configured(settings.AUTH_JWT_SECRET, min_length=16) else "AUTH_JWT_SECRET is missing, placeholder, or too short.",
    )
    _check(
        checks,
        code="oauth_state_secret",
        label="OAuth state secret",
        ok=_secret_configured(settings.OAUTH_STATE_SECRET, min_length=16),
        detail="OAUTH_STATE_SECRET is configured." if _secret_configured(settings.OAUTH_STATE_SECRET, min_length=16) else "OAUTH_STATE_SECRET is missing, placeholder, or too short.",
    )
    _check(
        checks,
        code="github_webhook_secret",
        label="GitHub webhook signing",
        ok=_secret_configured(settings.GITHUB_WEBHOOK_SECRET),
        detail="GITHUB_WEBHOOK_SECRET is configured." if _secret_configured(settings.GITHUB_WEBHOOK_SECRET) else "GITHUB_WEBHOOK_SECRET is missing or placeholder.",
    )
    _check(
        checks,
        code="provider_key_vault_kek",
        label="Provider key vault KEK",
        ok=_secret_configured(settings.PROVIDER_KEY_VAULT_KEK, min_length=32),
        detail="Provider key vault encryption key is configured." if _secret_configured(settings.PROVIDER_KEY_VAULT_KEK, min_length=32) else "PROVIDER_KEY_VAULT_KEK is missing, placeholder, or too short.",
    )
    _check(
        checks,
        code="platform_llm_key",
        label="Platform LLM key",
        ok=_secret_configured(settings.OPENROUTER_API_KEY, min_length=16) or _secret_configured(settings.OPENAI_API_KEY, min_length=16),
        detail="OPENROUTER_API_KEY or OPENAI_API_KEY is configured." if _secret_configured(settings.OPENROUTER_API_KEY, min_length=16) or _secret_configured(settings.OPENAI_API_KEY, min_length=16) else "OPENROUTER_API_KEY or OPENAI_API_KEY is missing, placeholder, or too short.",
    )
    _check(
        checks,
        code="replay_real_llm",
        label="Real replay enabled",
        ok=settings.REPLAY_REAL_LLM_ENABLED and _secret_configured(settings.REPLAY_WORKER_TOKEN, min_length=16),
        detail="Real replay and worker token are configured." if settings.REPLAY_REAL_LLM_ENABLED and _secret_configured(settings.REPLAY_WORKER_TOKEN, min_length=16) else "REPLAY_REAL_LLM_ENABLED or REPLAY_WORKER_TOKEN is not production-ready.",
    )
    _check(
        checks,
        code="billing_quota",
        label="Billing quota enforcement",
        ok=settings.BILLING_ENFORCE_QUOTA and str(settings.BILLING_QUOTA_FAILURE_POLICY).strip().lower() == "strict",
        detail="Billing quota enforcement is strict." if settings.BILLING_ENFORCE_QUOTA and str(settings.BILLING_QUOTA_FAILURE_POLICY).strip().lower() == "strict" else "Billing quota enforcement is disabled or not strict.",
    )

    _check(
        checks,
        code="billing_enabled",
        label="Billing enabled",
        ok=settings.BILLING_ENABLED,
        detail="Billing is enabled for paid launch." if settings.BILLING_ENABLED else "BILLING_ENABLED is false.",
    )

    billing_provider_ok = settings.BILLING_ENABLED and (
        settings.BILLING_PROVIDER.strip().lower() == "razorpay"
        and _secret_configured(settings.RAZORPAY_KEY_ID)
        and str(settings.RAZORPAY_KEY_ID).startswith("rzp_live_")
        and _secret_configured(settings.RAZORPAY_KEY_SECRET)
        and _secret_configured(settings.RAZORPAY_WEBHOOK_SECRET)
    )
    _check(
        checks,
        code="billing_provider",
        label="Billing provider",
        ok=billing_provider_ok,
        detail="Razorpay live credentials are configured." if billing_provider_ok else "Razorpay live credentials or webhook secret are missing.",
    )

    pii_ok = _secret_configured(settings.PII_ENCRYPTION_KEY) or _secret_configured(settings.GITHUB_TOKEN_ENCRYPTION_KEY)
    _check(
        checks,
        code="pii_encryption",
        label="PII encryption",
        ok=pii_ok,
        detail="PII/GitHub token encryption key is configured." if pii_ok else "PII_ENCRYPTION_KEY or GITHUB_TOKEN_ENCRYPTION_KEY is missing.",
    )

    metrics_ok = not settings.ENABLE_METRICS_ENDPOINT or _secret_configured(settings.METRICS_TOKEN)
    _check(
        checks,
        code="metrics_token",
        label="Metrics token",
        ok=metrics_ok,
        detail="Metrics endpoint is disabled or protected by token." if metrics_ok else "Metrics endpoint is enabled without METRICS_TOKEN.",
    )

    hard_blockers = [
        f"{check.code}:{check.detail}"
        for check in checks
        if check.required_for_launch and check.status == "fail"
    ]
    return ProductionReadinessResponse(
        overall_status="pass" if not hard_blockers else "blocked",
        app_env=settings.APP_ENV,
        production_profile=production_profile,
        hard_blockers=hard_blockers,
        checks=checks,
        checked_at=datetime.now(UTC),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
