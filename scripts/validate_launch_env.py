#!/usr/bin/env python3
"""Validate Zroky launch env files without printing secret values."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


PLACEHOLDER_MARKERS = (
    "__set_in_secret_manager__",
    "__customer_",
    "replace-with",
    "change-me",
    "changeme",
    "your-",
    "dummy",
    "fake",
    "sk-test",
    "test_",
    "proj_xxxx",
    "zk_live_xxxx",
)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
EXAMPLE_HOST_SUFFIXES = (".example.com",)
SECRET_REF_SCHEMES = (
    "railway://",
    "vercel://",
    "github-secret://",
    "secret://",
    "secretref://",
)


@dataclass(frozen=True)
class EnvValue:
    line: int
    value: str


@dataclass(frozen=True)
class SecretRule:
    name: str
    min_length: int = 16


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or data.count(b"\x00") > max(4, len(data) // 8):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def parse_env(path: Path) -> dict[str, list[EnvValue]]:
    values: dict[str, list[EnvValue]] = {}
    if not path.exists():
        return values
    for line_number, raw_line in enumerate(_read_text(path).splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values.setdefault(key, []).append(EnvValue(line_number, value))
    return values


def latest(values: dict[str, list[EnvValue]], key: str) -> EnvValue | None:
    matches = values.get(key)
    return matches[-1] if matches else None


def normalized(value: str | None) -> str:
    return (value or "").strip().lower()


def is_placeholder(value: str | None) -> bool:
    text = normalized(value)
    return any(marker in text for marker in PLACEHOLDER_MARKERS)


def is_secret_ref(value: str | None) -> bool:
    text = normalized(value)
    return any(text.startswith(prefix) for prefix in SECRET_REF_SCHEMES)


def is_true(value: str | None) -> bool:
    return normalized(value) in {"1", "true", "yes", "on"}


def is_false(value: str | None) -> bool:
    return normalized(value) in {"0", "false", "no", "off"}


def url_problem(value: str, *, allow_local: bool = False) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https", "postgresql+psycopg", "postgresql", "redis", "rediss"}:
        return "must be a URL with an expected scheme"
    host = (parsed.hostname or "").lower()
    if not host:
        return "must include a hostname"
    if not allow_local and host in LOCAL_HOSTS:
        return "must not point at localhost"
    if host.endswith(EXAMPLE_HOST_SUFFIXES):
        return "must not point at example.com"
    return None


def value_summary(value: str, *, fingerprints: bool) -> str:
    parts = [f"len={len(value)}"]
    if fingerprints:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
        parts.append(f"sha256_10={digest}")
    return " ".join(parts)


def add_missing(findings: list[str], key: str) -> None:
    findings.append(f"MISSING {key}")


def require_value(
    findings: list[str],
    values: dict[str, list[EnvValue]],
    key: str,
    *,
    min_length: int | None = None,
    exact: str | None = None,
    bool_true: bool = False,
    bool_false: bool = False,
    url: bool = False,
    allow_local_url: bool = False,
) -> None:
    item = latest(values, key)
    if item is None or not item.value:
        add_missing(findings, key)
        return
    if is_placeholder(item.value):
        findings.append(f"PLACEHOLDER {key} line={item.line}")
        return
    if is_secret_ref(item.value):
        if exact is not None or bool_true or bool_false:
            findings.append(f"INVALID {key} line={item.line}: secret reference is not allowed for literal config")
        return
    if min_length is not None and len(item.value) < min_length:
        findings.append(f"WEAK {key} line={item.line} len={len(item.value)} min={min_length}")
    if exact is not None and item.value != exact:
        findings.append(f"INVALID {key} line={item.line} expected={exact}")
    if bool_true and not is_true(item.value):
        findings.append(f"INVALID {key} line={item.line} expected=true")
    if bool_false and not is_false(item.value):
        findings.append(f"INVALID {key} line={item.line} expected=false")
    if url:
        problem = url_problem(item.value, allow_local=allow_local_url)
        if problem:
            findings.append(f"INVALID {key} line={item.line}: {problem}")


def require_prefix(
    findings: list[str],
    values: dict[str, list[EnvValue]],
    key: str,
    prefix: str,
) -> None:
    item = latest(values, key)
    if item is None or not item.value:
        return
    if is_secret_ref(item.value):
        return
    if is_placeholder(item.value) and not item.value.startswith("rzp_test_"):
        return
    if not item.value.startswith(prefix):
        findings.append(f"INVALID {key} line={item.line}: expected prefix {prefix}")


def require_one_secret(
    findings: list[str],
    values: dict[str, list[EnvValue]],
    keys: tuple[str, ...],
    *,
    min_length: int = 16,
) -> None:
    present = [item for key in keys if (item := latest(values, key)) and item.value]
    if not present:
        findings.append(f"MISSING one of {', '.join(keys)}")
        return
    if any(is_secret_ref(item.value) for item in present):
        return
    if all(is_placeholder(item.value) for item in present):
        findings.append(f"PLACEHOLDER one of {', '.join(keys)}")
        return
    if all(len(item.value) < min_length for item in present if not is_placeholder(item.value)):
        findings.append(f"WEAK one of {', '.join(keys)} min={min_length}")


def duplicate_findings(values: dict[str, list[EnvValue]]) -> list[str]:
    findings: list[str] = []
    for key, items in sorted(values.items()):
        if len(items) > 1:
            lines = ",".join(str(item.line) for item in items)
            findings.append(f"DUPLICATE {key} lines={lines}")
    return findings


def forbidden_findings(values: dict[str, list[EnvValue]], forbidden: tuple[str, ...]) -> list[str]:
    findings: list[str] = []
    for key in forbidden:
        item = latest(values, key)
        if item and item.value:
            findings.append(f"FORBIDDEN {key} line={item.line}")
    return findings


def validate_backend(values: dict[str, list[EnvValue]]) -> list[str]:
    findings = duplicate_findings(values)
    require_value(findings, values, "APP_ENV", exact="production")
    require_value(findings, values, "DATABASE_URL", url=True)
    database_url = latest(values, "DATABASE_URL")
    if database_url and normalized(database_url.value).startswith("sqlite"):
        findings.append(f"INVALID DATABASE_URL line={database_url.line}: must not use sqlite")
    require_value(findings, values, "REDIS_URL", url=True)
    require_value(findings, values, "ALLOWED_ORIGINS", url=True)
    require_value(findings, values, "TRUSTED_HOSTS")
    trusted_hosts = latest(values, "TRUSTED_HOSTS")
    if trusted_hosts and any(host.strip() in {"*", "localhost", "127.0.0.1"} for host in trusted_hosts.value.split(",")):
        findings.append(f"INVALID TRUSTED_HOSTS line={trusted_hosts.line}: must not include wildcard or localhost")
    require_value(findings, values, "FRONTEND_URL", url=True)
    require_value(findings, values, "ALLOW_PROJECT_HEADER_CONTEXT", bool_false=True)
    require_value(findings, values, "REQUIRE_PROVISIONING_TOKEN", bool_true=True)
    require_value(findings, values, "ENABLE_READY_DB_CHECK", bool_true=True)
    require_value(findings, values, "ENABLE_READY_REDIS_CHECK", bool_true=True)
    require_value(findings, values, "BILLING_ENFORCE_QUOTA", bool_true=True)
    require_value(findings, values, "BILLING_QUOTA_FAILURE_POLICY", exact="strict")
    require_value(findings, values, "REPLAY_REAL_LLM_ENABLED", bool_true=True)

    for rule in (
        SecretRule("AUTH_JWT_SECRET", 16),
        SecretRule("OAUTH_STATE_SECRET", 16),
        SecretRule("PROVIDER_KEY_VAULT_KEK", 32),
        SecretRule("PROVISIONING_TOKEN", 16),
        SecretRule("GITHUB_WEBHOOK_SECRET", 16),
        SecretRule("REPLAY_WORKER_TOKEN", 16),
    ):
        require_value(findings, values, rule.name, min_length=rule.min_length)

    metrics_enabled = latest(values, "ENABLE_METRICS_ENDPOINT")
    if metrics_enabled is None or is_true(metrics_enabled.value):
        require_value(findings, values, "METRICS_TOKEN", min_length=16)

    internal_debug = latest(values, "ENABLE_INTERNAL_DEBUG_ENDPOINT")
    if internal_debug and is_true(internal_debug.value):
        require_value(findings, values, "INTERNAL_DEBUG_TOKEN", min_length=16)

    require_one_secret(findings, values, ("PII_ENCRYPTION_KEY", "GITHUB_TOKEN_ENCRYPTION_KEY"), min_length=32)
    require_one_secret(findings, values, ("OPENROUTER_API_KEY", "OPENAI_API_KEY"), min_length=16)

    # Hosted launch requirements: these are user-facing flows, not optional
    # niceties. Keep them in the launch gate so a self-hosted runtime can still
    # boot with fewer integrations, while the paid hosted rollout fails closed.
    require_value(findings, values, "SMTP_HOST")
    require_value(findings, values, "SMTP_USER")
    require_value(findings, values, "SMTP_PASSWORD", min_length=16)
    require_value(findings, values, "ALERTS_FROM_EMAIL")

    require_value(findings, values, "GOOGLE_CLIENT_ID", min_length=8)
    require_value(findings, values, "GOOGLE_CLIENT_SECRET", min_length=16)
    require_value(findings, values, "GOOGLE_OAUTH_REDIRECT_URL", url=True)

    require_value(findings, values, "GITHUB_CLIENT_ID", min_length=8)
    require_value(findings, values, "GITHUB_CLIENT_SECRET", min_length=16)
    require_value(findings, values, "GITHUB_OAUTH_REDIRECT_URL", url=True)
    require_value(findings, values, "GITHUB_CONNECT_OAUTH_REDIRECT_URL", url=True)
    require_value(findings, values, "GITHUB_TOKEN_ENCRYPTION_KEY", min_length=32)
    require_value(findings, values, "GITHUB_PR_BOT_TOKEN", min_length=16)

    billing_enabled = latest(values, "BILLING_ENABLED")
    if billing_enabled is None or is_true(billing_enabled.value):
        provider = normalized(latest(values, "BILLING_PROVIDER").value if latest(values, "BILLING_PROVIDER") else "razorpay")
        if provider != "razorpay":
            findings.append("INVALID BILLING_PROVIDER expected=razorpay")
        require_value(findings, values, "RAZORPAY_KEY_ID", min_length=8)
        require_prefix(findings, values, "RAZORPAY_KEY_ID", "rzp_live_")
        require_value(findings, values, "RAZORPAY_KEY_SECRET", min_length=16)
        require_value(findings, values, "RAZORPAY_WEBHOOK_SECRET", min_length=16)
        require_value(findings, values, "RAZORPAY_DASHBOARD_URL", url=True)
        require_value(findings, values, "BILLING_CHECKOUT_SUCCESS_URL", url=True)
        require_value(findings, values, "BILLING_CHECKOUT_CANCEL_URL", url=True)
        require_value(findings, values, "BILLING_PORTAL_RETURN_URL", url=True)

    return findings


def validate_dashboard(values: dict[str, list[EnvValue]]) -> list[str]:
    findings = duplicate_findings(values)
    findings.extend(
        forbidden_findings(
            values,
            ("NEXTAUTH_URL", "NEXTAUTH_SECRET", "NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_API_BASE_URL"),
        )
    )
    require_value(findings, values, "ZROKY_API_BASE_URL", url=True)
    return findings


def validate_admin(values: dict[str, list[EnvValue]]) -> list[str]:
    findings = duplicate_findings(values)
    findings.extend(
        forbidden_findings(
            values,
            ("NEXTAUTH_URL", "NEXTAUTH_SECRET", "NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_API_BASE_URL"),
        )
    )
    require_value(findings, values, "ZROKY_API_BASE_URL", url=True)
    findings.extend(forbidden_findings(values, ("ZROKY_PROVISIONING_TOKEN", "ZROKY_API_KEY", "ZROKY_PROJECT_ID")))
    return findings


def validate_gateway(values: dict[str, list[EnvValue]]) -> list[str]:
    findings = duplicate_findings(values)
    require_value(findings, values, "REDIS_URL", url=True)
    require_value(findings, values, "ZROKY_API_URL", url=True)
    require_value(findings, values, "ZROKY_INGEST_URL", url=True)
    require_value(findings, values, "ZROKY_GATEWAY_API_KEY", min_length=16)
    require_value(findings, values, "ZROKY_GATEWAY_AUTH_TOKEN", min_length=16)
    require_value(findings, values, "ZROKY_ALLOWED_PROJECT_IDS")
    require_value(findings, values, "ZROKY_SPOOL_DIR")
    require_value(findings, values, "ZROKY_SPOOL_MAX_BYTES")
    require_value(findings, values, "ZROKY_SPOOL_FLUSH_INTERVAL_MS")
    require_value(findings, values, "ZROKY_CAPTURE_DURABILITY_MODE", exact="fail_closed")
    return findings


def validate_replay_worker(values: dict[str, list[EnvValue]]) -> list[str]:
    findings = duplicate_findings(values)
    require_value(findings, values, "CONTROL_PLANE_URL", url=True)
    require_value(findings, values, "WORKER_TOKEN", min_length=16)
    require_value(findings, values, "ARTIFACT_SIGNING_KEY", min_length=16)
    require_value(findings, values, "ARTIFACT_SIGNATURE_REQUIRED", bool_true=True)
    return findings


VALIDATORS = {
    "backend": validate_backend,
    "dashboard": validate_dashboard,
    "admin": validate_admin,
    "gateway": validate_gateway,
    "replay-worker": validate_replay_worker,
}

DEFAULT_FILES = {
    "backend": "zroky-backend/.env.production",
    "dashboard": "zroky-dashboard/.env.production",
    "admin": "zroky-admin/.env.local",
    "gateway": "zroky-gateway/.env",
    "replay-worker": "zroky-replay-worker/.env",
}


def tracked_secret_env_findings(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    findings: list[str] = []
    for raw in result.stdout.splitlines():
        path = raw.replace("\\", "/")
        name = Path(path).name
        if name in {".env", ".env.local", ".env.production"}:
            findings.append(f"TRACKED_SECRET_ENV {path}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--fingerprints", action="store_true", help="Print short SHA-256 fingerprints, never raw values.")
    parser.add_argument(
        "--roles",
        default=",".join(VALIDATORS),
        help="Comma-separated roles to validate. Known roles: " + ", ".join(sorted(VALIDATORS)),
    )
    parser.add_argument(
        "--require",
        default="backend,dashboard,admin",
        help="Comma-separated roles that must have env files. Known roles: "
        + ", ".join(sorted(VALIDATORS)),
    )
    for role, default in DEFAULT_FILES.items():
        parser.add_argument(f"--{role}-env", default=default, help=f"{role} env file path.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    selected_roles = {role.strip() for role in args.roles.split(",") if role.strip()}
    required_roles = {role.strip() for role in args.require.split(",") if role.strip()}
    unknown = sorted((selected_roles | required_roles) - set(VALIDATORS))
    if unknown:
        print(f"Unknown roles: {', '.join(unknown)}", file=sys.stderr)
        return 2

    all_findings: list[str] = []
    tracked_findings = tracked_secret_env_findings(root)
    if tracked_findings:
        print("[tracked-env]")
        for finding in tracked_findings:
            print(f"  {finding}")
        all_findings.extend(tracked_findings)

    for role, validator in VALIDATORS.items():
        if role not in selected_roles:
            continue
        rel_path = getattr(args, f"{role.replace('-', '_')}_env")
        path = (root / rel_path).resolve()
        print(f"[{role}] {path.relative_to(root) if path.is_relative_to(root) else path}")
        if not path.exists():
            message = "missing env file"
            print(f"  {'FAIL' if role in required_roles else 'SKIP'} {message}")
            if role in required_roles:
                all_findings.append(f"{role}: {message}")
            continue
        values = parse_env(path)
        findings = validator(values)
        if findings:
            for finding in findings:
                print(f"  FAIL {finding}")
            all_findings.extend(f"{role}: {finding}" for finding in findings)
        else:
            print("  OK")
        if args.fingerprints:
            for key in sorted(values):
                item = latest(values, key)
                if item:
                    print(f"  SEEN {key} line={item.line} {value_summary(item.value, fingerprints=True)}")

    if all_findings:
        print(f"\nlaunch env validation failed: {len(all_findings)} finding(s)")
        if "backend" in selected_roles:
            print("backend checklist: README.md final paid launch gate")
        return 1
    print("\nlaunch env validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
