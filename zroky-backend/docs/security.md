# Security

## Authentication

ZROKY supports two auth mechanisms:

1. **JWT (browser)** — issued after GitHub OAuth or email/password sign-in. JWTs are
   signed with `AUTH_JWT_SECRET` (HS256) and carry `sub` + `role` claims.
2. **API key (SDK / programmatic)** — SHA-256 hashed (`key_hash`) stored in the
   `api_keys` table. Keys are scoped to a single project and can be revoked.

## Tenant isolation (Row-Level Security)

On Postgres every tenant-scoped table has RLS enabled. A `tenant_id` context
variable is set per connection via `set_config('app.current_tenant_id', ...)`.
Policies ensure users only see rows matching their project membership.

## PII encryption at rest

- **User email** — stored as `EncryptedSearchableString` (Fernet encryption +
  HMAC-SHA256 hash for deterministic lookups). The `email_hash` column powers
  login and unique-constraint checks.
- **GitHub access tokens** — encrypted with the same Fernet backend.
- **Sensitive payload fields** — masked before storage (`zroky._internal.pii`).

## Keys

| Secret | Used for |
|--------|----------|
| `ENCRYPTION_SECRET_KEY` | General-purpose Fernet encryption |
| `PII_ENCRYPTION_KEY` | Dedicated key for user PII |
| `PII_HMAC_KEY` | Deterministic hash of emails for lookups |
| `GITHUB_TOKEN_ENCRYPTION_KEY` | GitHub OAuth token encryption |
| `AUTH_JWT_SECRET` | JWT signing / verification |

All Fernet keys must be 32-byte URL-safe base64-encoded strings.

## Rate limiting

- API key creation / deletion: 10 per minute
- Ingest endpoint: 1 000 per minute per project
- Email verification resend: 3 per hour
- Password reset: 5 per hour

## Responsible disclosure

- **Contact:** See `/.well-known/security.txt` (RFC 9116 compliant)
- **Policy:** `/security` returns JSON with safe-harbor and scope details
- **PGP key:** Configured via `SECURITY_PGP_KEY_URL`

We aim to acknowledge vulnerability reports within 48 hours.

## Correlation IDs

Every HTTP request is tagged with a `X-Correlation-Id` header that propagates
through the backend, Celery jobs, and outgoing HTTP calls. The same ID appears
in all structured logs and error responses, making distributed tracing trivial.

## Scanning

The codebase is scanned automatically with `bandit` and `ruff` security lints
in CI. No hardcoded secrets or known-vulnerable dependencies are permitted.
