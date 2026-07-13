from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config_validation import is_jwt_configured, is_production_env, validate_runtime_settings


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
    RATE_LIMIT_STORAGE_URI: Optional[str] = None

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
    GATEWAY_INGEST_STREAM_ENABLED: bool = False
    GATEWAY_INGEST_STREAM_NAME: str = "zroky:ingest:v2"
    GATEWAY_INGEST_CONSUMER_GROUP: str = "zroky-backend"
    GATEWAY_INGEST_CONSUMER_NAME: str = "worker-1"
    GATEWAY_INGEST_STREAM_BATCH_SIZE: int = 100
    GATEWAY_INGEST_STREAM_BLOCK_MS: int = 1000
    GATEWAY_INGEST_POLL_INTERVAL_SECONDS: int = 5
    GATEWAY_INGEST_STREAM_MAX_ATTEMPTS: int = 3
    GATEWAY_INGEST_DEAD_LETTER_STREAM_NAME: str = "zroky:ingest:v2:dead"

    PROVIDER_STATUS_FETCH_TIMEOUT_MS: int = 800
    PROVIDER_STATUS_CACHE_TTL_SECONDS: int = 300
    PROVIDER_STATUS_ENDPOINTS_JSON: str = "{}"
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # â”€â”€ OpenRouter / DeepSeek settings â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Primary model for diagnosis/fix generation (DeepSeek â€” best for code)
    OPENROUTER_PRIMARY_MODEL: str = "deepseek/deepseek-chat"
    # Fallback model when primary is down / rate-limited
    OPENROUTER_FALLBACK_MODEL: str = "deepseek/deepseek-chat-v3"
    # Assistant chat model (Gemini 2.5 Flash â€” fast, large context, reliable tool-use)
    OPENROUTER_ASSISTANT_MODEL: str = "google/gemini-2.5-flash"
    # NL analytics model (GPT-4o-mini â€” most reliable structured JSON output)
    OPENROUTER_ANALYTICS_MODEL: str = "openai/gpt-4o-mini"
    # Request timeout for OpenRouter calls
    OPENROUTER_REQUEST_TIMEOUT_SECONDS: int = 60

    TENANT_HEADER_NAME: str = "x-project-id"
    LEGACY_TENANT_HEADER_NAME: str = "x-tenant-id"
    ACCEPT_LEGACY_TENANT_HEADER: bool = True
    # SECURITY: must be False in production â€” setting True lets any caller claim owner context
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

    # SECURITY: must be True in production â€” setting False lets anyone call provisioning endpoints
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

    # Discovery engine (Discover pillar). Default-off until offline and
    # real-trace precision gates prove surfaced findings are quiet enough.
    DISCOVERY_ENABLED: bool = False
    DISCOVERY_CUSTOMER_SURFACE_ENABLED: bool = False
    DISCOVERY_WARMUP_MIN_TRACES: int = 200
    DISCOVERY_WARMUP_MIN_DAYS: int = 3
    DISCOVERY_BASELINE_WINDOW_DAYS: int = 14
    DISCOVERY_RECURRENCE_K: int = 3
    DISCOVERY_CRITICAL_TOOL_PCT: float = 0.90
    DISCOVERY_SURFACE_MIN_CONFIDENCE: float = 0.80
    DISCOVERY_Z_WEAK: float = 3.0
    DISCOVERY_SCAN_LIMIT: int = 1000
    DISCOVERY_PROJECT_LIMIT: int = 100
    DISCOVERY_REFRESH_CRON_HOUR: int = 1
    DISCOVERY_REFRESH_CRON_MINUTE: int = 17
    DISCOVERY_SCAN_INTERVAL_SECONDS: int = 300

    # â”€â”€ ClickHouse (W12) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # When unset, /cost and /issues fall back to Postgres with a banner warning.
    CLICKHOUSE_URL: Optional[str] = None
    CLICKHOUSE_DATABASE: str = "zroky"
    CLICKHOUSE_USER: str = "zroky"
    CLICKHOUSE_PASSWORD: str = "zroky_ch_pw"
    CLICKHOUSE_ENABLED: bool = False
    CLICKHOUSE_SYNC_INTERVAL_SECONDS: int = 60

    # Outcome verification connectors.
    OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS: bool = False
    OUTCOME_CONNECTOR_TIMEOUT_SECONDS: float = 5.0
    OUTCOME_CONNECTOR_MAX_ATTEMPTS: int = 2
    # New receipts use Ed25519 so customers and auditors can verify signatures
    # with only the published public key. The old HMAC secret is retained only
    # for legacy receipt verification.
    ACTION_RECEIPT_ED25519_PRIVATE_KEY: Optional[str] = None
    ACTION_RECEIPT_SIGNING_SECRET: Optional[str] = None
    ACTION_RECEIPT_SIGNING_KEY_ID: str = "zroky-action-receipt-v1"
    ACTION_POST_EXECUTION_SWEEP_INTERVAL_SECONDS: int = 10
    ACTION_POST_EXECUTION_SWEEP_LIMIT: int = 25
    ACTION_EXECUTION_ATTEMPT_STALE_SECONDS: int = 600
    ACTION_EXECUTION_ATTEMPT_SWEEP_INTERVAL_SECONDS: int = 60
    ACTION_EXECUTION_ATTEMPT_SWEEP_LIMIT: int = 50
    SOURCE_MUTATION_POLLER_ENABLED: bool = False
    SOURCE_MUTATION_POLLER_INTERVAL_SECONDS: int = 60
    SOURCE_MUTATION_POLLER_PROJECT_LIMIT: int = 100
    SOURCE_MUTATION_POLLER_PER_CONNECTOR_LIMIT: int = 50
    SOURCE_MUTATION_POLLER_TIMEOUT_SECONDS: float = 5.0

    # â”€â”€ Replay worker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Shared secret between the control plane and the customer-hosted replay worker.
    # When unset, /v1/replay/poll and /v1/replay/result always return 401.
    REPLAY_WORKER_TOKEN: Optional[str] = None
    REPLAY_JOB_LEASE_SECONDS: int = 600

    # â”€â”€ Replay execution mode â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # When False (default), the replay executor's default resolver re-grades
    # each golden trace against the source Call's *recorded response* â€” this
    # is "stub-mode" replay and CANNOT detect regressions caused by prompt
    # edits, model swaps, or RAG-config changes, because no real LLM call is
    # ever issued.
    #
    # When True, dispatch_replay_run() accepts `candidate_prompt_override`
    # and `candidate_model_override`, and the executor uses LiveLlmResolver
    # (Option B) to issue a real LLM call per trace and grade the actual
    # output. Stub-mode requests that pass overrides are rejected at the
    # dispatch layer to prevent silent no-ops.
    #
    # Honest framing for the dashboard: when False, the run-detail response
    # carries `replay_mode="stub"` plus a human-readable warning so the UI
    # can show a banner instead of pretending the prompt edit was tested.
    REPLAY_REAL_LLM_ENABLED: bool = False
    # Per-run hard budget cap (USD) for real-LLM replay. Aborts the run
    # before issuing more provider calls once cumulative spend crosses
    # this number. Stub-mode runs ignore the cap entirely (no LLM cost).
    REPLAY_REAL_LLM_BUDGET_USD: float = 1.0
    # Optional customer-hosted sandbox executor for live-sandbox replay.
    # When unset, live-sandbox requests fail closed instead of pretending
    # captured tool snapshots are equivalent to real sandbox execution.
    REPLAY_SANDBOX_WORKER_URL: Optional[str] = None
    REPLAY_SANDBOX_WORKER_TOKEN: Optional[str] = None
    REPLAY_SANDBOX_TIMEOUT_SECONDS: float = 30.0

    # â”€â”€ Billing quota enforcement â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # When True, ingest returns HTTP 429 once a tenant exceeds their plan's
    # max_calls_per_month.  Disable during trials / grace periods via this flag
    # or the per-project feature flag `billing_quota_enforcement`.
    BILLING_ENFORCE_QUOTA: bool = False
    BILLING_QUOTA_FAILURE_POLICY: str = "strict"  # strict | alert_only

    # Connection pool sizing (Postgres only â€” SQLite uses default StaticPool).
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT_SECONDS: int = 30
    DB_POOL_RECYCLE_SECONDS: int = 1800
    DB_STATEMENT_TIMEOUT_MS: int = 30_000

    # Responsible-disclosure contact (security.txt / /.well-known/security.txt)
    SECURITY_CONTACT_EMAIL: str = "security@zroky.com"
    SECURITY_PGP_KEY_URL: str = "https://zroky.com/pgp-key.txt"

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

    # â”€â”€ Provider key vault (Module 4.5; plan Â§14.2 / migration 0058) â”€â”€â”€â”€â”€
    # Master KEK for the AES-256-GCM envelope used by `provider_keys_vault`.
    # Production: drive from KMS-resolved KEK (e.g. AWS KMS GenerateDataKey).
    # Local/dev/test: any string â‰¥ 32 chars; HKDF-SHA256 derives a per-project
    # KEK so cross-tenant ciphertext decryption is impossible even with the
    # master KEK in hand. When unset, the vault routes return 503 to surface
    # the misconfiguration loudly rather than silently storing plaintext.
    PROVIDER_KEY_VAULT_KEK: Optional[str] = None
    # Identifier recorded in `provider_keys_vault.kms_key_id` so periodic
    # re-wrap rotation can find rows still encrypted under the previous KEK.
    PROVIDER_KEY_VAULT_KEY_ID: str = "local-dev-kek-v1"

    # Hosted billing uses Razorpay. When disabled, paid checkout/verification
    # endpoints return 503; self-host profiles keep billing disabled by default.
    BILLING_ENABLED: bool = False
    BILLING_PROVIDER: str = "razorpay"
    RAZORPAY_KEY_ID: Optional[str] = None
    RAZORPAY_KEY_SECRET: Optional[str] = None
    RAZORPAY_WEBHOOK_SECRET: Optional[str] = None
    RAZORPAY_DASHBOARD_URL: str = "https://dashboard.razorpay.com/"
    ZROKY_EXCHANGE_RATE_USD_TO_INR: float = 83.00
    # Legacy redirect URLs retained for older clients.
    BILLING_CHECKOUT_SUCCESS_URL: str = (
        "http://localhost:3000/settings/billing?status=success"
    )
    BILLING_CHECKOUT_CANCEL_URL: str = (
        "http://localhost:3000/settings/billing?status=cancel"
    )
    BILLING_PORTAL_RETURN_URL: str = "http://localhost:3000/settings/billing"

    # â”€â”€ Subscription lifecycle automation (Module 12; plan Â§11.4) â”€â”€â”€â”€â”€â”€â”€â”€
    # Master switch for the trial-expiry + past-due-grace sweeps. When
    # false the Celery tasks short-circuit (used during incident
    # response if a billing bug is auto-downgrading customers wrongly).
    BILLING_LIFECYCLE_SWEEP_ENABLED: bool = True
    # Grace period (days) between a subscription entering `past_due`
    # and the hard-downgrade to free. Section 11.4 binds 7 days; this
    # is configurable so contract-specific deals (Enterprise) can
    # negotiate a longer grace without a code change.
    BILLING_PAST_DUE_GRACE_DAYS: int = 7
    # Per-tick row cap for both sweep tasks. Bounds the worst-case
    # execution time (one DB transaction per row) â€” at 500 the task
    # finishes well within Celery's visibility timeout. Increase for
    # backfills, never decrease below 100 (a backed-up sweep would
    # take many beat ticks to drain).
    BILLING_LIFECYCLE_SWEEP_LIMIT: int = 500
    # Cron minute for both lifecycle sweeps (hourly). Offset from :00
    # to dodge the top-of-hour herd from other systems. The two
    # sweeps share the minute because they query disjoint row sets
    # (status='trialing' vs status='past_due') and never contend.
    BILLING_LIFECYCLE_SWEEP_MINUTE: int = 7
    # Recover Razorpay orders that are paid at the provider but still
    # pending locally because the browser callback or webhook was missed.
    BILLING_RAZORPAY_RECONCILE_ENABLED: bool = True
    BILLING_RAZORPAY_RECONCILE_INTERVAL_SECONDS: int = 300
    BILLING_RAZORPAY_RECONCILE_LIMIT: int = 100

    # â”€â”€ Entitlements resolver (Module 6; plan Â§11.2) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Redis cache TTL for the merged (override > trial > plan) entitlement
    # dict per org_id. Plan Â§11.2 binds 60s. Lower = fresher reads after
    # plan changes; higher = less DB load. 60s is the bound write
    # invalidations (services/entitlements.py) cap to.
    ENTITLEMENT_CACHE_TTL_SECONDS: int = 60

    # â”€â”€ Judge engine (Module 7; plan Â§4.2 + Â§17.2 decision #4) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Master kill-switch. When false, get_evaluator() returns the
    # deterministic stub regardless of plan â€” useful for incident response
    # if a judge model misbehaves at scale.
    JUDGE_ENABLED: bool = True
    # Single-judge model. claude-haiku-4 per locked decision (cheap, fast,
    # good calibration vs. anthropic ground truth).
    JUDGE_SINGLE_MODEL: str = "anthropic/claude-haiku-4"
    # Ensemble members (Plus/Enterprise). JSON array of OpenRouter model
    # slugs. Median vote â†’ final verdict. Per decision #4: Haiku-4 +
    # GPT-4.5-mini. Stored as a string so 12-factor env-var deploys keep
    # working.
    JUDGE_ENSEMBLE_MODELS_JSON: str = (
        '["anthropic/claude-haiku-4","openai/gpt-4o-mini"]'
    )
    # Max response tokens per judge call. The judge only emits a tiny JSON
    # object so 256 is generous.
    JUDGE_MAX_TOKENS: int = 256
    # Sampling temperature. 0.0 = deterministic, which is what we want
    # for graders. Bump only if a calibration study justifies it.
    JUDGE_TEMPERATURE: float = 0.0
    # Calibration drift alarm threshold. Plan Â§17.2 decision #4 binds 5%.
    # When the rolling judge-vs-ground-truth disagreement rate over
    # JUDGE_CALIBRATION_WINDOW_HOURS exceeds this, an anomaly is emitted.
    JUDGE_CALIBRATION_DRIFT_THRESHOLD: float = 0.05
    # Rolling window used by the calibration tracker. 168h = 7 days.
    JUDGE_CALIBRATION_WINDOW_HOURS: int = 168
    # Minimum sample count before drift is computed. Smaller windows are
    # too noisy to alarm on; 20 is the floor below which we skip.
    JUDGE_CALIBRATION_MIN_SAMPLES: int = 20
    # Multi-dimensional evaluator (Module 7 extension; plan Â§9 accuracy+faithfulness+
    # relevance+coherence breakdown). Kill-switch mirrors JUDGE_ENABLED pattern.
    JUDGE_MULTIDIM_ENABLED: bool = True
    # Override model for multi-dim calls. Empty string â†’ falls back to JUDGE_SINGLE_MODEL.
    JUDGE_MULTIDIM_MODEL: str = ""
    # Reference-free evaluator â€” no golden output needed. Dimensions: relevance,
    # coherence, groundedness (hallucination proxy), completeness. Useful for
    # cold-start projects that have not yet labelled any golden sets.
    JUDGE_REFERENCE_FREE_ENABLED: bool = True
    # Override model for reference-free calls. Empty string â†’ falls back to JUDGE_SINGLE_MODEL.
    JUDGE_REFERENCE_FREE_MODEL: str = ""

    # â”€â”€ Module 10: Pilot Tier-2 auto-PR backend â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Plan Â§17.3 #2 (GitHub App vs OAuth) is still open. Until that
    # decision lands, the dispatch pipeline ships behind a protocol
    # seam with three implementations (dry_run / recording / a future
    # github_app or github_oauth). `dry_run` is the safe default for
    # tests + dev â€” fail-CLOSED: a typo in this env var produces a
    # dry-run client, never a live PR-opening client.
    PILOT_PR_CLIENT_BACKEND: str = "dry_run"
    # Replay-pass gate threshold for Tier-2 dispatch (plan Â§17.1 risk #1).
    # A ReplayRun must report `pass_count / trace_count_at_dispatch >= this`
    # to clear the gate. 0.95 mirrors `policy_json.tier1_min_confidence`
    # default but is intentionally a separate knob â€” Tier-2 PRs are
    # human-reviewed, so a customer might choose a lower gate for them.
    PILOT_TIER2_REPLAY_PASS_GATE: float = 0.95
    # Daily cap on Tier-2 PR creations per project. Sized for "noisy
    # detector wakes up at 3am" scenarios â€” at 10/day a runaway loop
    # produces tractable review load instead of paging cost. Override
    # via env var; per-project override lives in policy_json (later).
    PILOT_TIER2_DAILY_PR_CAP: int = 10

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
    # State HMAC key for CSRF protection â€” defaults to AUTH_JWT_SECRET if not set
    OAUTH_STATE_SECRET: Optional[str] = None

    # SMTP / email notifications
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    ALERTS_FROM_EMAIL: str = "noreply@zroky.com"

    # Slack Incoming Webhook for alert notifications
    SLACK_WEBHOOK_URL: Optional[str] = None
    SLACK_CLIENT_ID: Optional[str] = None
    SLACK_CLIENT_SECRET: Optional[str] = None
    SLACK_OAUTH_REDIRECT_URL: str = "http://localhost:8000/v1/integrations/slack/callback"
    SLACK_OAUTH_SCOPES: str = "incoming-webhook,chat:write,commands,channels:read,groups:read"
    SLACK_TOKEN_ENCRYPTION_KEY: Optional[str] = None
    SLACK_SIGNING_SECRET: Optional[str] = None
    MS_TEAMS_WEBHOOK_ENCRYPTION_KEY: Optional[str] = None

    # Zoho CRM OAuth for system-of-record verification.  The accounts/API
    # domains are configurable because Zoho regions use different hosts
    # (for example .com, .in, .eu).
    ZOHO_CLIENT_ID: Optional[str] = None
    ZOHO_CLIENT_SECRET: Optional[str] = None
    ZOHO_ACCOUNTS_BASE_URL: str = "https://accounts.zoho.com"
    ZOHO_DEFAULT_API_BASE_URL: str = "https://www.zohoapis.com"
    ZOHO_OAUTH_REDIRECT_URL: str = (
        "http://localhost:8000/v1/integrations/system-of-record/zoho-crm/oauth/callback"
    )
    ZOHO_OAUTH_SCOPES: str = "ZohoCRM.modules.READ"

    # Atlassian OAuth 2.0 (3LO) for Jira system-of-record verification.
    ATLASSIAN_CLIENT_ID: Optional[str] = None
    ATLASSIAN_CLIENT_SECRET: Optional[str] = None
    ATLASSIAN_OAUTH_REDIRECT_URL: str = (
        "http://localhost:8000/v1/integrations/system-of-record/jira-issue/oauth/callback"
    )
    ATLASSIAN_OAUTH_SCOPES: str = "read:jira-work read:jira-user offline_access"


    # Weekly digest pipeline.
    DIGEST_ENABLED: bool = False
    DIGEST_SEND_BATCH_SIZE: int = 100
    DIGEST_GENERATE_CRON_DAY_OF_WEEK: int = 1  # 1 = Monday (0=Sunday ... 6=Saturday)
    DIGEST_GENERATE_CRON_HOUR: int = 2

    # â”€â”€ Legacy-surface feature flags (ZROKY-TECHNICAL-PLAN-V2.md Â§1.3) â”€â”€â”€â”€â”€â”€â”€â”€
    # These gate routes whose UI is being cut in Module 1 or whose replacement
    # ships in a later module. When `False` the route is NOT registered with
    # the API router, so OpenAPI no longer advertises it.
    #
    # Launch policy: old observability/replay/issue APIs are default-off so the
    # customer product surface stays focused on protected actions, outcomes, and
    # evidence. Internal dependencies that still feed the control plane
    # (calls/traces and alerts/notifications) remain mounted separately.
    FEATURE_LEGACY_OWNER: bool = True              # Customer production env sets False. Admin-only deployments may enable for zroky-admin.
    FEATURE_LEGACY_OBSERVABILITY_API: bool = False
    FEATURE_LEGACY_REPLAY_API: bool = False
    FEATURE_LEGACY_DIAGNOSIS_API: bool = False
    FEATURE_LEGACY_ISSUES_API: bool = False
    # FEATURE_LEGACY_BILLING removed after M12; deprecated /plans and
    # GET/PUT /subscription routes are deleted.
    FEATURE_LEGACY_INVITATIONS: bool = True        # M8 will reduce. Replacement: /v1/invitations/accept only.
    FEATURE_LEGACY_DIAGNOSIS_ALIAS: bool = False

    # â”€â”€ Calibrated Judge (Wedge 3 â€” judge calibration + auto-downgrade) â”€â”€â”€â”€â”€
    # Master switch for the daily golden-set calibration runner.
    JUDGE_CALIBRATION_ENABLED: bool = True
    # Cron hour/minute (UTC) for the daily per-project calibration sweep.
    JUDGE_CALIBRATION_CRON_HOUR: int = 3
    JUDGE_CALIBRATION_CRON_MINUTE: int = 30
    # Minimum labeled golden traces required before a run is attempted.
    JUDGE_CALIBRATION_MIN_SAMPLES: int = 50
    # Accuracy thresholds with hysteresis (decision #4: Â§17.2).
    JUDGE_CALIBRATION_DOWNGRADE_BELOW: float = 0.90
    JUDGE_CALIBRATION_RESTORE_ABOVE: float = 0.93

    # â”€â”€ Provider Drift Watch (Wedge 2) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Master switch for the daily provider-silent-update detector.
    # When false the Celery beat task short-circuits and the public
    # endpoints return empty arrays (no banners, no RSS items).
    PROVIDER_DRIFT_WATCH_ENABLED: bool = True
    # Hour at which the daily probe suite is dispatched (UTC).
    PROVIDER_DRIFT_WATCH_CRON_HOUR: int = 4
    PROVIDER_DRIFT_WATCH_CRON_MINUTE: int = 0
    # Per-run budget cap (USD). At ~240 probes Ã— 8 models with average
    # ~$0.001/call this lands around $2/day; we keep a 5x safety
    # multiplier so a model whose pricing rises (or one that produces
    # unusually long outputs) doesn't silently kill the run.
    PROVIDER_DRIFT_WATCH_BUDGET_USD: float = 10.0
    # Z-score thresholds for the aggregator (mirror drift_detector.py).
    PROVIDER_DRIFT_WATCH_Z_INFO: float = 2.0
    PROVIDER_DRIFT_WATCH_Z_WARN: float = 3.0
    PROVIDER_DRIFT_WATCH_Z_CRITICAL: float = 4.0

    @property
    def effective_celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def effective_celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

@lru_cache
def get_settings() -> Settings:
    return Settings()
