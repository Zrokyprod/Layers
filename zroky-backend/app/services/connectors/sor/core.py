"""System-of-record connectors for outcome verification.

The first production connector is intentionally narrow: read one refund row
from a customer's ledger/refund API, then let outcome_reconciliation compare
claimed-vs-actual. Connector failures never become a false pass.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from base64 import b64encode
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from sqlalchemy import create_engine, text as sql_text
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError

from app.services.outcome_reconciliation import SourceRecord


class ConnectorConfigError(ValueError):
    """Raised when connector config is unsafe or incomplete."""


_TEMPLATE_RE = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*)}")
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}
_AUTH_FAILED_HTTP_STATUSES = {401, 403}
_RETRYABLE_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_MAX_CONNECTOR_ATTEMPTS = 4
_POSTGRES_SCHEMES = {"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"}
_SQL_PARAM_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_BLOCKED_SQL_RE = re.compile(
    r"\b("
    r"alter|analyze|call|cluster|copy|create|delete|do|drop|execute|grant|"
    r"insert|listen|lock|merge|notify|refresh|reindex|reset|revoke|set|"
    r"truncate|update|vacuum"
    r")\b",
    re.IGNORECASE,
)


def _clean_text(value: Any) -> str:
    return str(value).strip()


def _is_blocked_host(host: str) -> bool:
    normalized = host.strip().lower().strip("[]")
    if normalized in _BLOCKED_HOSTS:
        return True
    try:
        parsed = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return (
        parsed.is_loopback
        or parsed.is_private
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    )


def _safe_base_url(base_url: str, *, allow_private_hosts: bool = False) -> str:
    cleaned = _clean_text(base_url).rstrip("/") + "/"
    parsed = urlsplit(cleaned)
    if parsed.scheme != "https":
        raise ConnectorConfigError("ledger connector base_url must use https")
    if not parsed.netloc or not parsed.hostname:
        raise ConnectorConfigError("ledger connector base_url must include a host")
    if parsed.username or parsed.password:
        raise ConnectorConfigError(
            "ledger connector base_url must not include credentials"
        )
    if parsed.query or parsed.fragment:
        raise ConnectorConfigError(
            "ledger connector base_url must not include query or fragment values"
        )
    if not allow_private_hosts and _is_blocked_host(parsed.hostname):
        raise ConnectorConfigError(
            "ledger connector base_url must not target a private or local host"
        )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _render_path_template(template: str, values: Mapping[str, Any]) -> str:
    cleaned = _clean_text(template)
    if not cleaned.startswith("/"):
        raise ConnectorConfigError("ledger connector path_template must start with '/'")
    if "\\" in cleaned:
        raise ConnectorConfigError(
            "ledger connector path_template must not include backslashes"
        )
    if "://" in cleaned:
        raise ConnectorConfigError(
            "ledger connector path_template must be a relative path"
        )
    if "?" in cleaned or "#" in cleaned:
        raise ConnectorConfigError(
            "ledger connector path_template must not include query or fragment values"
        )

    decoded_template = unquote(cleaned).replace("\\", "/")
    if any(segment == ".." for segment in decoded_template.split("/")):
        raise ConnectorConfigError(
            "ledger connector path_template must not include path traversal segments"
        )

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = values.get(key)
        if value is None or _clean_text(value) == "":
            raise ConnectorConfigError(
                f"ledger connector path_template missing value for {key}"
            )
        return quote(_clean_text(value), safe="")

    rendered = _TEMPLATE_RE.sub(replace, cleaned)
    if "{" in rendered or "}" in rendered:
        raise ConnectorConfigError(
            "ledger connector path_template contains an invalid placeholder"
        )
    decoded_rendered = unquote(rendered).replace("\\", "/")
    if any(segment == ".." for segment in decoded_rendered.split("/")):
        raise ConnectorConfigError(
            "ledger connector path_template must not include path traversal segments"
        )
    return rendered


def _select_record(payload: Any, record_path: str | None) -> dict[str, Any] | None:
    current = payload
    if record_path:
        for part in [item.strip() for item in record_path.split(".") if item.strip()]:
            if isinstance(current, Mapping):
                if part not in current:
                    return None
                current = current[part]
                continue
            if isinstance(current, list) and part.isdigit():
                index = int(part)
                if index >= len(current):
                    return None
                current = current[index]
                continue
            return None
    if isinstance(current, Mapping):
        return dict(current)
    return None


def _without_query(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _bounded_max_attempts(value: int | None) -> int:
    try:
        attempts = int(value or 1)
    except (TypeError, ValueError):
        attempts = 1
    return min(_MAX_CONNECTOR_ATTEMPTS, max(1, attempts))


def _request_error_code(exc: httpx.RequestError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "connector_timeout"
    return "connector_request_error"


def _http_error_taxonomy(status: int) -> tuple[str, str, bool]:
    if status in _AUTH_FAILED_HTTP_STATUSES:
        return "http_error", "auth_failed", False
    if status == 429:
        return "http_error", "rate_limited", True
    if status in _RETRYABLE_HTTP_STATUSES:
        return "http_error", "upstream_retryable_http_error", True
    return "http_error", "upstream_http_error", False


def _query_digest(query: str) -> str:
    return hashlib.sha256(query.strip().encode("utf-8")).hexdigest()


def _safe_database_url(
    database_url: str,
    *,
    allow_private_hosts: bool = False,
    allow_sqlite_for_tests: bool = False,
) -> str:
    cleaned = _clean_text(database_url)
    if not cleaned:
        raise ConnectorConfigError("postgres connector database_url is required")
    parsed = urlsplit(cleaned)
    if allow_sqlite_for_tests and parsed.scheme.startswith("sqlite"):
        return cleaned
    if parsed.scheme not in _POSTGRES_SCHEMES:
        raise ConnectorConfigError(
            "postgres connector database_url must use a PostgreSQL scheme"
        )
    if parsed.scheme == "postgres":
        cleaned = urlunsplit(
            ("postgresql", parsed.netloc, parsed.path, parsed.query, parsed.fragment)
        )
        parsed = urlsplit(cleaned)
    if not parsed.netloc or not parsed.hostname:
        raise ConnectorConfigError("postgres connector database_url must include a host")
    if not allow_private_hosts and _is_blocked_host(parsed.hostname):
        raise ConnectorConfigError(
            "postgres connector database_url must not target a private or local host"
        )
    return cleaned


def validate_postgres_read_query(query: str) -> str:
    cleaned = _clean_text(query)
    if not cleaned:
        raise ConnectorConfigError("postgres connector query is required")
    if len(cleaned) > 8000:
        raise ConnectorConfigError("postgres connector query must be at most 8000 characters")
    if ";" in cleaned:
        raise ConnectorConfigError("postgres connector query must contain one statement")
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise ConnectorConfigError("postgres connector query must not include comments")
    lowered = cleaned.lstrip().lower()
    if not (lowered.startswith("select ") or lowered.startswith("with ")):
        raise ConnectorConfigError(
            "postgres connector query must be a SELECT or read-only WITH query"
        )
    if _BLOCKED_SQL_RE.search(cleaned):
        raise ConnectorConfigError(
            "postgres connector query contains a non-read-only SQL keyword"
        )
    if re.search(r"\bfor\s+(update|share|no\s+key\s+update|key\s+share)\b", cleaned, re.IGNORECASE):
        raise ConnectorConfigError(
            "postgres connector query must not acquire row locks"
        )
    return cleaned


def _public_database_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    if parsed.scheme not in _POSTGRES_SCHEMES:
        return "postgresql://source-record"
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    return urlunsplit((parsed.scheme, netloc, parsed.path or "", "", ""))


def validate_postgres_read_config(
    *,
    database_url: str,
    read_query: str,
    allow_private_hosts: bool = False,
) -> dict[str, str]:
    """Validate a saved PostgreSQL verifier config without exposing credentials."""
    normalized_database_url = _safe_database_url(
        database_url,
        allow_private_hosts=allow_private_hosts,
    )
    normalized_query = validate_postgres_read_query(read_query)
    return {
        "database_url": normalized_database_url,
        "public_database_url": _public_database_url(normalized_database_url),
        "read_query": normalized_query,
    }


def _normalize_sql_params(
    params: Mapping[str, Any] | None,
) -> dict[str, str | int | float | bool | None]:
    if not params:
        return {}
    if len(params) > 100:
        raise ConnectorConfigError("postgres connector params must include at most 100 keys")
    normalized: dict[str, str | int | float | bool | None] = {}
    for raw_key, value in params.items():
        key = str(raw_key).strip()
        if not _SQL_PARAM_RE.fullmatch(key):
            raise ConnectorConfigError(
                "postgres connector param names must be SQL bind identifiers"
            )
        if value is None or isinstance(value, (str, int, float, bool)):
            normalized[key] = value
            continue
        raise ConnectorConfigError(
            "postgres connector param values must be strings, numbers, booleans, or null"
        )
    return normalized


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _database_metadata(
    *,
    connector_type: str,
    database_url: str,
    query: str,
    adapter: str = "postgresql_readonly",
    error: str | None = None,
    error_code: str | None = None,
    attempts: int = 1,
    timeout_seconds: float | None = None,
    retryable: bool | None = None,
    record_found: bool | None = None,
) -> dict[str, Any]:
    parsed = urlsplit(database_url)
    payload: dict[str, Any] = {
        "connector_type": connector_type,
        "adapter": adapter,
        "database_scheme": parsed.scheme,
        "query_digest": _query_digest(query),
        "attempts": attempts,
        "retry_count": max(0, attempts - 1),
        "read_only": True,
    }
    if parsed.hostname:
        payload["database_host"] = parsed.hostname
    if parsed.scheme in _POSTGRES_SCHEMES and parsed.path and parsed.path != "/":
        payload["database_name"] = parsed.path.lstrip("/")
    if timeout_seconds is not None:
        payload["timeout_seconds"] = timeout_seconds
    if record_found is not None:
        payload["record_found"] = record_found
    if error:
        payload["error"] = error
    if error_code:
        payload["error_code"] = error_code
    if retryable is not None:
        payload["retryable"] = retryable
    return payload


def _sql_error_code(exc: SQLAlchemyError) -> str:
    if isinstance(exc, OperationalError):
        return "database_unavailable"
    if isinstance(exc, DBAPIError):
        return "database_query_error"
    return "database_error"


def _sql_error_retryable(exc: SQLAlchemyError) -> bool:
    if isinstance(exc, OperationalError):
        return True
    if isinstance(exc, DBAPIError):
        return bool(getattr(exc, "connection_invalidated", False))
    return False


def _metadata(
    *,
    connector_type: str,
    request_url: str,
    adapter: str = "https_json_record",
    http_status: int | None = None,
    record_path: str | None = None,
    error: str | None = None,
    error_code: str | None = None,
    attempts: int | None = None,
    max_attempts: int | None = None,
    timeout_seconds: float | None = None,
    retryable: bool | None = None,
    transient_errors: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "connector_type": connector_type,
        "adapter": adapter,
        "request_url": _without_query(request_url),
    }
    if http_status is not None:
        payload["http_status"] = http_status
    if record_path:
        payload["record_path"] = record_path
    if error:
        payload["error"] = error
    if error_code:
        payload["error_code"] = error_code
    if attempts is not None:
        payload["attempts"] = attempts
        payload["retry_count"] = max(0, attempts - 1)
    if max_attempts is not None:
        payload["max_attempts"] = max_attempts
    if timeout_seconds is not None:
        payload["timeout_seconds"] = timeout_seconds
    if retryable is not None:
        payload["retryable"] = retryable
    if transient_errors:
        payload["transient_errors"] = transient_errors[:_MAX_CONNECTOR_ATTEMPTS]
    return payload


def validate_ledger_refund_api_config(
    *,
    base_url: str,
    path_template: str = "/refunds/{refund_id}",
    record_path: str | None = None,
    allow_private_hosts: bool = False,
) -> dict[str, str | None]:
    """Validate and normalize a ledger refund connector without issuing I/O."""
    normalized_base_url = _safe_base_url(
        base_url, allow_private_hosts=allow_private_hosts
    ).rstrip("/")
    normalized_path_template = _clean_text(path_template) or "/refunds/{refund_id}"
    _render_path_template(normalized_path_template, {"refund_id": "zroky_config_check"})
    normalized_record_path = _clean_text(record_path) if record_path else None
    if normalized_record_path:
        if ".." in normalized_record_path or "\\" in normalized_record_path:
            raise ConnectorConfigError(
                "ledger connector record_path must not include traversal segments"
            )
        if len(normalized_record_path) > 255:
            raise ConnectorConfigError(
                "ledger connector record_path must be at most 255 characters"
            )
    return {
        "base_url": normalized_base_url,
        "path_template": normalized_path_template,
        "record_path": normalized_record_path or None,
    }


def validate_stripe_refund_config(
    *,
    base_url: str = "https://api.stripe.com",
    path_template: str = "/v1/refunds/{refund_id}",
    record_path: str | None = None,
    allow_private_hosts: bool = False,
) -> dict[str, str | None]:
    """Validate and normalize a Stripe refund verifier config without issuing I/O."""
    normalized_base_url = _safe_base_url(
        base_url, allow_private_hosts=allow_private_hosts
    ).rstrip("/")
    normalized_path_template = _clean_text(path_template) or "/v1/refunds/{refund_id}"
    _render_path_template(normalized_path_template, {"refund_id": "re_123"})
    normalized_record_path = _clean_text(record_path) if record_path else None
    if normalized_record_path:
        if ".." in normalized_record_path or "\\" in normalized_record_path:
            raise ConnectorConfigError(
                "Stripe connector record_path must not include traversal segments"
            )
        if len(normalized_record_path) > 255:
            raise ConnectorConfigError(
                "Stripe connector record_path must be at most 255 characters"
            )
    return {
        "base_url": normalized_base_url,
        "path_template": normalized_path_template,
        "record_path": normalized_record_path or None,
    }


def validate_razorpay_refund_config(
    *,
    base_url: str = "https://api.razorpay.com",
    path_template: str = "/v1/refunds/{refund_id}",
    record_path: str | None = None,
    allow_private_hosts: bool = False,
) -> dict[str, str | None]:
    """Validate and normalize a Razorpay refund verifier config without issuing I/O."""
    normalized_base_url = _safe_base_url(
        base_url, allow_private_hosts=allow_private_hosts
    ).rstrip("/")
    normalized_path_template = _clean_text(path_template) or "/v1/refunds/{refund_id}"
    _render_path_template(normalized_path_template, {"refund_id": "rfnd_Foo123"})
    normalized_record_path = _clean_text(record_path) if record_path else None
    if normalized_record_path:
        if ".." in normalized_record_path or "\\" in normalized_record_path:
            raise ConnectorConfigError(
                "Razorpay connector record_path must not include traversal segments"
            )
        if len(normalized_record_path) > 255:
            raise ConnectorConfigError(
                "Razorpay connector record_path must be at most 255 characters"
            )
    return {
        "base_url": normalized_base_url,
        "path_template": normalized_path_template,
        "record_path": normalized_record_path or None,
    }


def validate_customer_record_api_config(
    *,
    base_url: str,
    path_template: str = "/customers/{customer_id}",
    record_path: str | None = None,
    allow_private_hosts: bool = False,
) -> dict[str, str | None]:
    """Validate and normalize a CRM/customer-record connector without issuing I/O."""
    normalized_base_url = _safe_base_url(
        base_url, allow_private_hosts=allow_private_hosts
    ).rstrip("/")
    normalized_path_template = _clean_text(path_template) or "/customers/{customer_id}"
    _render_path_template(
        normalized_path_template, {"customer_id": "zroky_config_check"}
    )
    normalized_record_path = _clean_text(record_path) if record_path else None
    if normalized_record_path:
        if ".." in normalized_record_path or "\\" in normalized_record_path:
            raise ConnectorConfigError(
                "customer record connector record_path must not include traversal segments"
            )
        if len(normalized_record_path) > 255:
            raise ConnectorConfigError(
                "customer record connector record_path must be at most 255 characters"
            )
    return {
        "base_url": normalized_base_url,
        "path_template": normalized_path_template,
        "record_path": normalized_record_path or None,
    }


def validate_generic_rest_api_config(
    *,
    base_url: str,
    path_template: str = "/records/{record_ref}",
    record_path: str | None = None,
    allow_private_hosts: bool = False,
) -> dict[str, str | None]:
    """Validate and normalize a generic REST/OpenAPI verifier config."""
    normalized_base_url = _safe_base_url(
        base_url, allow_private_hosts=allow_private_hosts
    ).rstrip("/")
    normalized_path_template = _clean_text(path_template) or "/records/{record_ref}"
    _render_path_template(
        normalized_path_template, {"record_ref": "zroky_config_check"}
    )
    normalized_record_path = _clean_text(record_path) if record_path else None
    if normalized_record_path:
        if ".." in normalized_record_path or "\\" in normalized_record_path:
            raise ConnectorConfigError(
                "generic REST connector record_path must not include traversal segments"
            )
        if len(normalized_record_path) > 255:
            raise ConnectorConfigError(
                "generic REST connector record_path must be at most 255 characters"
            )
    return {
        "base_url": normalized_base_url,
        "path_template": normalized_path_template,
        "record_path": normalized_record_path or None,
    }


def validate_hubspot_crm_config(
    *,
    path_template: str = "/crm/v3/objects/contacts/{record_ref}",
    record_path: str | None = None,
) -> dict[str, str | None]:
    """Validate the native HubSpot CRM verifier config without issuing I/O."""
    normalized_path_template = (
        _clean_text(path_template) or "/crm/v3/objects/contacts/{record_ref}"
    )
    _render_path_template(normalized_path_template, {"record_ref": "zroky_config_check"})
    normalized_record_path = _clean_text(record_path) if record_path else None
    if normalized_record_path:
        if ".." in normalized_record_path or "\\" in normalized_record_path:
            raise ConnectorConfigError(
                "HubSpot connector record_path must not include traversal segments"
            )
        if len(normalized_record_path) > 255:
            raise ConnectorConfigError(
                "HubSpot connector record_path must be at most 255 characters"
            )
    return {
        "base_url": "https://api.hubapi.com",
        "path_template": normalized_path_template,
        "record_path": normalized_record_path or None,
    }


def validate_zendesk_ticket_config(
    *,
    base_url: str,
    path_template: str = "/api/v2/tickets/{record_ref}.json",
    record_path: str | None = "ticket",
    allow_private_hosts: bool = False,
) -> dict[str, str | None]:
    """Validate and normalize a Zendesk ticket verifier config without issuing I/O."""
    normalized_base_url = _safe_base_url(
        base_url, allow_private_hosts=allow_private_hosts
    ).rstrip("/")
    normalized_path_template = (
        _clean_text(path_template) or "/api/v2/tickets/{record_ref}.json"
    )
    _render_path_template(normalized_path_template, {"record_ref": "123"})
    normalized_record_path = _clean_text(record_path) if record_path else "ticket"
    if normalized_record_path:
        if ".." in normalized_record_path or "\\" in normalized_record_path:
            raise ConnectorConfigError(
                "Zendesk connector record_path must not include traversal segments"
            )
        if len(normalized_record_path) > 255:
            raise ConnectorConfigError(
                "Zendesk connector record_path must be at most 255 characters"
            )
    return {
        "base_url": normalized_base_url,
        "path_template": normalized_path_template,
        "record_path": normalized_record_path or None,
    }


def validate_jira_issue_config(
    *,
    base_url: str,
    path_template: str = "/rest/api/3/issue/{record_ref}",
    record_path: str | None = None,
    allow_private_hosts: bool = False,
) -> dict[str, str | None]:
    """Validate and normalize a Jira/JSM issue verifier config without issuing I/O."""
    normalized_base_url = _safe_base_url(
        base_url, allow_private_hosts=allow_private_hosts
    ).rstrip("/")
    normalized_path_template = (
        _clean_text(path_template) or "/rest/api/3/issue/{record_ref}"
    )
    _render_path_template(normalized_path_template, {"record_ref": "JSM-123"})
    normalized_record_path = _clean_text(record_path) if record_path else None
    if normalized_record_path:
        if ".." in normalized_record_path or "\\" in normalized_record_path:
            raise ConnectorConfigError(
                "Jira connector record_path must not include traversal segments"
            )
        if len(normalized_record_path) > 255:
            raise ConnectorConfigError(
                "Jira connector record_path must be at most 255 characters"
            )
    return {
        "base_url": normalized_base_url,
        "path_template": normalized_path_template,
        "record_path": normalized_record_path or None,
    }


def validate_salesforce_crm_config(
    *,
    base_url: str,
    path_template: str = "/services/data/v60.0/sobjects/{object_type}/{record_ref}",
    record_path: str | None = None,
    allow_private_hosts: bool = False,
) -> dict[str, str | None]:
    """Validate and normalize a Salesforce CRM verifier config without issuing I/O."""
    normalized_base_url = _safe_base_url(
        base_url, allow_private_hosts=allow_private_hosts
    ).rstrip("/")
    normalized_path_template = (
        _clean_text(path_template)
        or "/services/data/v60.0/sobjects/{object_type}/{record_ref}"
    )
    _render_path_template(
        normalized_path_template,
        {"object_type": "Account", "record_ref": "001000000000000AAA"},
    )
    normalized_record_path = _clean_text(record_path) if record_path else None
    if normalized_record_path:
        if ".." in normalized_record_path or "\\" in normalized_record_path:
            raise ConnectorConfigError(
                "Salesforce connector record_path must not include traversal segments"
            )
        if len(normalized_record_path) > 255:
            raise ConnectorConfigError(
                "Salesforce connector record_path must be at most 255 characters"
            )
    return {
        "base_url": normalized_base_url,
        "path_template": normalized_path_template,
        "record_path": normalized_record_path or None,
    }


def validate_zoho_crm_config(
    *,
    base_url: str = "https://www.zohoapis.com",
    path_template: str = "/crm/v8/{module_name}/{record_ref}",
    record_path: str | None = "data.0",
    allow_private_hosts: bool = False,
) -> dict[str, str | None]:
    """Validate and normalize a Zoho CRM verifier config without issuing I/O."""
    normalized_base_url = _safe_base_url(
        base_url, allow_private_hosts=allow_private_hosts
    ).rstrip("/")
    normalized_path_template = (
        _clean_text(path_template) or "/crm/v8/{module_name}/{record_ref}"
    )
    _render_path_template(
        normalized_path_template,
        {"module_name": "Contacts", "record_ref": "1234567890000000001"},
    )
    normalized_record_path = _clean_text(record_path) if record_path else "data.0"
    if normalized_record_path:
        if ".." in normalized_record_path or "\\" in normalized_record_path:
            raise ConnectorConfigError(
                "Zoho CRM connector record_path must not include traversal segments"
            )
        if len(normalized_record_path) > 255:
            raise ConnectorConfigError(
                "Zoho CRM connector record_path must be at most 255 characters"
            )
    return {
        "base_url": normalized_base_url,
        "path_template": normalized_path_template,
        "record_path": normalized_record_path or None,
    }


def validate_netsuite_finance_config(
    *,
    base_url: str,
    path_template: str = "/services/rest/record/v1/{record_type}/{record_ref}",
    record_path: str | None = None,
    allow_private_hosts: bool = False,
) -> dict[str, str | None]:
    """Validate and normalize a NetSuite finance record verifier config without issuing I/O."""
    normalized_base_url = _safe_base_url(
        base_url, allow_private_hosts=allow_private_hosts
    ).rstrip("/")
    normalized_path_template = (
        _clean_text(path_template)
        or "/services/rest/record/v1/{record_type}/{record_ref}"
    )
    _render_path_template(
        normalized_path_template,
        {"record_type": "vendorBill", "record_ref": "12345"},
    )
    normalized_record_path = _clean_text(record_path) if record_path else None
    if normalized_record_path:
        if ".." in normalized_record_path or "\\" in normalized_record_path:
            raise ConnectorConfigError(
                "NetSuite connector record_path must not include traversal segments"
            )
        if len(normalized_record_path) > 255:
            raise ConnectorConfigError(
                "NetSuite connector record_path must be at most 255 characters"
            )
    return {
        "base_url": normalized_base_url,
        "path_template": normalized_path_template,
        "record_path": normalized_record_path or None,
    }


_ZERO_DECIMAL_CURRENCIES = frozenset({"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"})
_THREE_DECIMAL_CURRENCIES = frozenset({"BHD", "JOD", "KWD", "OMR", "TND"})


__all__ = [name for name in globals() if not name.startswith("__")]
