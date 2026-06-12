from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "validate_launch_env.py"


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_launch_env", VALIDATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _env_values(module: ModuleType, text: str) -> dict[str, list[object]]:
    values: dict[str, list[object]] = {}
    for line_number, raw_line in enumerate(text.strip().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values.setdefault(key.strip(), []).append(module.EnvValue(line_number, value.strip()))
    return values


def _valid_backend_env() -> str:
    return """
APP_ENV=production
DATABASE_URL=postgresql+psycopg://zroky:secret@db.zroky.ai:5432/zroky
REDIS_URL=rediss://redis.zroky.ai:6379/0
ALLOWED_ORIGINS=https://app.zroky.ai
TRUSTED_HOSTS=api.zroky.ai
FRONTEND_URL=https://app.zroky.ai
ALLOW_PROJECT_HEADER_CONTEXT=false
REQUIRE_PROVISIONING_TOKEN=true
ENABLE_READY_DB_CHECK=true
ENABLE_READY_REDIS_CHECK=true
BILLING_ENFORCE_QUOTA=true
BILLING_QUOTA_FAILURE_POLICY=strict
REPLAY_REAL_LLM_ENABLED=true
AUTH_JWT_SECRET=auth-secret-with-enough-length
OAUTH_STATE_SECRET=oauth-state-secret-with-enough-length
PROVIDER_KEY_VAULT_KEK=provider-key-vault-kek-with-32chars
PROVISIONING_TOKEN=provisioning-token-with-enough-length
GITHUB_WEBHOOK_SECRET=github-webhook-secret
REPLAY_WORKER_TOKEN=replay-worker-token
METRICS_TOKEN=metrics-token-with-enough-length
PII_ENCRYPTION_KEY=pii-encryption-key-with-32-characters
OPENROUTER_API_KEY=openrouter-platform-key
BILLING_ENABLED=true
BILLING_PROVIDER=razorpay
RAZORPAY_KEY_ID=rzp_live_launchready
RAZORPAY_KEY_SECRET=razorpay-secret-with-enough-length
RAZORPAY_WEBHOOK_SECRET=razorpay-webhook-secret-with-enough-length
RAZORPAY_DASHBOARD_URL=https://dashboard.razorpay.com/
BILLING_CHECKOUT_SUCCESS_URL=https://app.zroky.ai/settings/billing?checkout=success
BILLING_CHECKOUT_CANCEL_URL=https://app.zroky.ai/settings/billing?checkout=cancel
BILLING_PORTAL_RETURN_URL=https://app.zroky.ai/settings/billing
"""


def test_backend_launch_env_requires_live_razorpay_and_strict_quota() -> None:
    validator = _load_validator()
    values = _env_values(
        validator,
        _valid_backend_env()
        .replace("RAZORPAY_KEY_ID=rzp_live_launchready", "RAZORPAY_KEY_ID=rzp_test_launchready")
        .replace("BILLING_QUOTA_FAILURE_POLICY=strict", "BILLING_QUOTA_FAILURE_POLICY=alert_only"),
    )

    findings = validator.validate_backend(values)

    assert any("RAZORPAY_KEY_ID" in finding and "rzp_live_" in finding for finding in findings)
    assert any("BILLING_QUOTA_FAILURE_POLICY" in finding for finding in findings)


def test_backend_launch_env_accepts_razorpay_live_checkout_urls() -> None:
    validator = _load_validator()
    values = _env_values(validator, _valid_backend_env())

    assert validator.validate_backend(values) == []


def test_gateway_launch_env_requires_fail_closed_spool_config() -> None:
    validator = _load_validator()
    values = _env_values(
        validator,
        """
ZROKY_API_URL=https://api.zroky.ai
ZROKY_INGEST_URL=https://api.zroky.ai/api/v1/ingest
ZROKY_GATEWAY_API_KEY=zk_live_gateway_key
ZROKY_GATEWAY_AUTH_TOKEN=gateway-auth-token
ZROKY_ALLOWED_PROJECT_IDS=proj_launch
ZROKY_SPOOL_DIR=/var/lib/zroky/spool
ZROKY_SPOOL_MAX_BYTES=104857600
ZROKY_SPOOL_FLUSH_INTERVAL_MS=5000
ZROKY_CAPTURE_DURABILITY_MODE=best_effort
""",
    )

    findings = validator.validate_gateway(values)

    assert any("ZROKY_CAPTURE_DURABILITY_MODE" in finding for finding in findings)


def test_replay_worker_launch_env_requires_signatures_but_not_global_provider_key() -> None:
    validator = _load_validator()
    values = _env_values(
        validator,
        """
CONTROL_PLANE_URL=https://api.zroky.ai
WORKER_TOKEN=worker-token-with-enough-length
ARTIFACT_SIGNING_KEY=artifact-signing-key-with-enough-length
ARTIFACT_SIGNATURE_REQUIRED=true
""",
    )

    assert validator.validate_replay_worker(values) == []


def test_replay_worker_launch_env_rejects_unsigned_artifacts() -> None:
    validator = _load_validator()
    values = _env_values(
        validator,
        """
CONTROL_PLANE_URL=https://api.zroky.ai
WORKER_TOKEN=worker-token-with-enough-length
ARTIFACT_SIGNING_KEY=artifact-signing-key-with-enough-length
ARTIFACT_SIGNATURE_REQUIRED=false
""",
    )

    findings = validator.validate_replay_worker(values)

    assert any("ARTIFACT_SIGNATURE_REQUIRED" in finding for finding in findings)


def test_launch_env_cli_points_to_readme_not_deleted_docs() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR_PATH),
            "--root",
            str(ROOT),
            "--roles",
            "backend",
            "--require",
            "backend",
            "--backend-env",
            "missing-production.env",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "README.md final paid launch gate" in output
    assert "docs/backend-production-env-checklist.md" not in output
