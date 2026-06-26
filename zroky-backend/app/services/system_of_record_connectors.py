"""System-of-record connectors for outcome verification.

The first production connector is intentionally narrow: read one refund row
from a customer's ledger/refund API, then let outcome_reconciliation compare
claimed-vs-actual. Connector failures never become a false pass.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
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


def _cents_to_usd(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite():
            return None
        return float(amount / Decimal("100"))
    except (InvalidOperation, OverflowError, ValueError):
        return None


@dataclass(frozen=True)
class HttpJsonRecordConnector:
    """Fetch a JSON record from a customer-hosted system-of-record adapter."""

    base_url: str
    path_template: str
    path_values: Mapping[str, Any]
    query: Mapping[str, Any] | None = None
    bearer_token: str | None = None
    record_path: str | None = None
    connector_type: str = "http_json_record"
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    allow_private_hosts: bool = False
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)

    def _url(self) -> str:
        base_url = _safe_base_url(
            self.base_url, allow_private_hosts=self.allow_private_hosts
        )
        path = _render_path_template(self.path_template, self.path_values)
        url = urljoin(base_url, path.lstrip("/"))
        query = {
            str(key): str(value)
            for key, value in (self.query or {}).items()
            if value is not None and str(key).strip()
        }
        if query:
            url = f"{url}?{urlencode(query)}"
        return url

    def fetch(self) -> SourceRecord:
        try:
            url = self._url()
        except ConnectorConfigError:
            if not self.fail_closed_config_errors:
                raise
            return SourceRecord(
                record=None,
                record_found=None,
                metadata=_metadata(
                    connector_type=self.connector_type,
                    request_url="connector_url_unavailable",
                    record_path=self.record_path,
                    error="connector_config_error",
                    error_code="connector_config_invalid",
                    attempts=0,
                    max_attempts=_bounded_max_attempts(self.max_attempts),
                    timeout_seconds=self.timeout_seconds,
                    retryable=False,
                ),
            )

        headers = {"Accept": "application/json"}
        if self.bearer_token and self.bearer_token.strip():
            headers["Authorization"] = f"Bearer {self.bearer_token.strip()}"
        max_attempts = _bounded_max_attempts(self.max_attempts)
        attempts = 0
        transient_errors: list[str] = []
        response: httpx.Response | None = None

        try:
            with httpx.Client(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                for attempt in range(1, max_attempts + 1):
                    attempts = attempt
                    try:
                        response = client.get(url, headers=headers)
                    except httpx.RequestError as exc:
                        error_name = exc.__class__.__name__
                        error_code = _request_error_code(exc)
                        transient_errors.append(error_name)
                        if attempt < max_attempts:
                            continue
                        return SourceRecord(
                            record=None,
                            record_found=None,
                            metadata=_metadata(
                                connector_type=self.connector_type,
                                request_url=url,
                                record_path=self.record_path,
                                error=error_name,
                                error_code=error_code,
                                attempts=attempts,
                                max_attempts=max_attempts,
                                timeout_seconds=self.timeout_seconds,
                                retryable=True,
                                transient_errors=transient_errors,
                            ),
                        )

                    if response.status_code in _RETRYABLE_HTTP_STATUSES:
                        transient_errors.append(f"http_{response.status_code}")
                        if attempt < max_attempts:
                            continue
                    break
        except httpx.RequestError as exc:
            error_name = exc.__class__.__name__
            return SourceRecord(
                record=None,
                record_found=None,
                metadata=_metadata(
                    connector_type=self.connector_type,
                    request_url=url,
                    record_path=self.record_path,
                    error=error_name,
                    error_code=_request_error_code(exc),
                    attempts=attempts or 1,
                    max_attempts=max_attempts,
                    timeout_seconds=self.timeout_seconds,
                    retryable=True,
                    transient_errors=transient_errors or [error_name],
                ),
            )

        if response is None:
            return SourceRecord(
                record=None,
                record_found=None,
                metadata=_metadata(
                    connector_type=self.connector_type,
                    request_url=url,
                    record_path=self.record_path,
                    error="request_not_attempted",
                    attempts=attempts,
                    max_attempts=max_attempts,
                    timeout_seconds=self.timeout_seconds,
                    retryable=False,
                ),
            )

        status = response.status_code
        if status == 404:
            return SourceRecord(
                record=None,
                record_found=False,
                metadata=_metadata(
                    connector_type=self.connector_type,
                    request_url=url,
                    http_status=status,
                    record_path=self.record_path,
                    error_code="system_record_missing",
                    attempts=attempts,
                    max_attempts=max_attempts,
                    timeout_seconds=self.timeout_seconds,
                    retryable=False,
                    transient_errors=transient_errors,
                ),
            )
        if status < 200 or status >= 300:
            error, error_code, retryable = _http_error_taxonomy(status)
            return SourceRecord(
                record=None,
                record_found=None,
                metadata=_metadata(
                    connector_type=self.connector_type,
                    request_url=url,
                    http_status=status,
                    record_path=self.record_path,
                    error=error,
                    error_code=error_code,
                    attempts=attempts,
                    max_attempts=max_attempts,
                    timeout_seconds=self.timeout_seconds,
                    retryable=retryable,
                    transient_errors=transient_errors,
                ),
            )
        if not response.content:
            return SourceRecord(
                record=None,
                record_found=None,
                metadata=_metadata(
                    connector_type=self.connector_type,
                    request_url=url,
                    http_status=status,
                    record_path=self.record_path,
                    error="empty_response",
                    error_code="empty_response",
                    attempts=attempts,
                    max_attempts=max_attempts,
                    timeout_seconds=self.timeout_seconds,
                    retryable=False,
                    transient_errors=transient_errors,
                ),
            )
        try:
            payload = response.json()
        except ValueError:
            return SourceRecord(
                record=None,
                record_found=None,
                metadata=_metadata(
                    connector_type=self.connector_type,
                    request_url=url,
                    http_status=status,
                    record_path=self.record_path,
                    error="invalid_json",
                    error_code="invalid_json",
                    attempts=attempts,
                    max_attempts=max_attempts,
                    timeout_seconds=self.timeout_seconds,
                    retryable=False,
                    transient_errors=transient_errors,
                ),
            )

        record = _select_record(payload, self.record_path)
        return SourceRecord(
            record=record,
            record_found=True if record is not None else None,
            metadata=_metadata(
                connector_type=self.connector_type,
                request_url=url,
                http_status=status,
                record_path=self.record_path,
                error=None if record is not None else "record_path_missing",
                error_code=None if record is not None else "record_path_missing",
                attempts=attempts,
                max_attempts=max_attempts,
                timeout_seconds=self.timeout_seconds,
                retryable=False,
                transient_errors=transient_errors,
            ),
        )


def _normalise_refund_record(
    record: Mapping[str, Any], *, refund_id: str
) -> dict[str, Any]:
    normalized = dict(record)
    if "refund_id" not in normalized:
        for candidate in ("id", "refundId", "refundID", "external_id"):
            value = normalized.get(candidate)
            if value is not None and _clean_text(value):
                normalized["refund_id"] = value
                break
    if "refund_id" not in normalized and refund_id:
        normalized["refund_id"] = refund_id
    if "amount_usd" not in normalized:
        for candidate in (
            "amount",
            "amountUSD",
            "amountUsd",
            "amount_usd_cents",
            "amount_cents",
            "amountCents",
        ):
            value = normalized.get(candidate)
            if value is None:
                continue
            if candidate in {"amount_usd_cents", "amount_cents", "amountCents"}:
                cents_value = _cents_to_usd(value)
                if cents_value is None:
                    continue
                normalized["amount_usd"] = cents_value
            else:
                normalized["amount_usd"] = value
            break
    if isinstance(normalized.get("currency"), str):
        normalized["currency"] = normalized["currency"].upper()
    if "status" not in normalized:
        for candidate in ("state", "refund_status", "refundStatus"):
            value = normalized.get(candidate)
            if value is not None and _clean_text(value):
                normalized["status"] = value
                break
    return normalized


def _normalise_customer_record(
    record: Mapping[str, Any], *, customer_id: str
) -> dict[str, Any]:
    normalized = dict(record)
    if "customer_id" not in normalized:
        for candidate in (
            "id",
            "customerId",
            "customerID",
            "contact_id",
            "contactId",
            "account_id",
            "external_id",
        ):
            value = normalized.get(candidate)
            if value is not None and _clean_text(value):
                normalized["customer_id"] = value
                break
    if "customer_id" not in normalized and customer_id:
        normalized["customer_id"] = customer_id
    if isinstance(normalized.get("email"), str):
        normalized["email"] = normalized["email"].strip().lower()
    if "status" not in normalized:
        for candidate in (
            "state",
            "customer_status",
            "customerStatus",
            "lifecycle_status",
            "lifecycleStatus",
        ):
            value = normalized.get(candidate)
            if value is not None and _clean_text(value):
                normalized["status"] = value
                break
    return normalized


@dataclass(frozen=True)
class LedgerRefundApiConnector:
    """Read one refund from a ledger/refund API."""

    base_url: str
    refund_id: str
    bearer_token: str | None = None
    path_template: str = "/refunds/{refund_id}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    allow_private_hosts: bool = False
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "ledger_refund_api"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"refund_id": self.refund_id},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=self.allow_private_hosts,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = (
            _normalise_refund_record(source.record, refund_id=self.refund_id)
            if source.record is not None
            else None
        )
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata={**(source.metadata or {}), "refund_id": self.refund_id},
        )


@dataclass(frozen=True)
class CustomerRecordApiConnector:
    """Read one customer/contact/account record from a CRM API."""

    base_url: str
    customer_id: str
    bearer_token: str | None = None
    path_template: str = "/customers/{customer_id}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    allow_private_hosts: bool = False
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "customer_record_api"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"customer_id": self.customer_id},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=self.allow_private_hosts,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = (
            _normalise_customer_record(source.record, customer_id=self.customer_id)
            if source.record is not None
            else None
        )
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata={**(source.metadata or {}), "customer_id": self.customer_id},
        )


@dataclass(frozen=True)
class GenericRestApiConnector:
    """Read one arbitrary JSON record from a customer system for proof."""

    base_url: str
    record_ref: str
    bearer_token: str | None = None
    path_template: str = "/records/{record_ref}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    allow_private_hosts: bool = False
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "generic_rest_api"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"record_ref": self.record_ref},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=self.allow_private_hosts,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = dict(source.record) if source.record is not None else None
        if record is not None and "record_ref" not in record:
            record["record_ref"] = self.record_ref
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata={**(source.metadata or {}), "record_ref": self.record_ref},
        )


@dataclass(frozen=True)
class PostgresReadOnlyConnector:
    """Read one source-of-record row through a constrained PostgreSQL query."""

    database_url: str
    query: str
    params: Mapping[str, Any] | None = None
    timeout_seconds: float = 5.0
    allow_private_hosts: bool = False
    allow_sqlite_for_tests: bool = False
    fail_closed_config_errors: bool = False
    connector_type: str = "postgres_read"

    def _validated(self) -> tuple[str, str, dict[str, str | int | float | bool | None]]:
        database_url = _safe_database_url(
            self.database_url,
            allow_private_hosts=self.allow_private_hosts,
            allow_sqlite_for_tests=self.allow_sqlite_for_tests,
        )
        query = validate_postgres_read_query(self.query)
        params = _normalize_sql_params(self.params)
        return database_url, query, params

    def fetch(self) -> SourceRecord:
        try:
            database_url, query, params = self._validated()
        except ConnectorConfigError:
            if not self.fail_closed_config_errors:
                raise
            safe_url = "postgres_connector_url_unavailable"
            safe_query = self.query or "postgres_connector_query_unavailable"
            return SourceRecord(
                record=None,
                record_found=None,
                metadata=_database_metadata(
                    connector_type=self.connector_type,
                    database_url=safe_url,
                    query=safe_query,
                    error="connector_config_error",
                    error_code="connector_config_invalid",
                    attempts=0,
                    timeout_seconds=self.timeout_seconds,
                    retryable=False,
                ),
            )

        engine = None
        try:
            connect_args: dict[str, Any] = {}
            if not self.allow_sqlite_for_tests:
                connect_args["connect_timeout"] = max(1, int(self.timeout_seconds))
            engine = create_engine(
                database_url,
                future=True,
                pool_pre_ping=False,
                connect_args=connect_args,
            )
            with engine.connect() as connection:
                with connection.begin():
                    if connection.dialect.name == "postgresql":
                        connection.execute(sql_text("SET TRANSACTION READ ONLY"))
                    result = connection.execute(sql_text(query), params)
                    row = result.mappings().first()
        except SQLAlchemyError as exc:
            return SourceRecord(
                record=None,
                record_found=None,
                metadata=_database_metadata(
                    connector_type=self.connector_type,
                    database_url=database_url,
                    query=query,
                    error=exc.__class__.__name__,
                    error_code=_sql_error_code(exc),
                    attempts=1,
                    timeout_seconds=self.timeout_seconds,
                    retryable=_sql_error_retryable(exc),
                ),
            )
        finally:
            if engine is not None:
                engine.dispose()

        if row is None:
            return SourceRecord(
                record=None,
                record_found=False,
                metadata=_database_metadata(
                    connector_type=self.connector_type,
                    database_url=database_url,
                    query=query,
                    attempts=1,
                    timeout_seconds=self.timeout_seconds,
                    retryable=False,
                    record_found=False,
                ),
            )

        record = _json_safe(dict(row))
        return SourceRecord(
            record=record,
            record_found=True,
            metadata=_database_metadata(
                connector_type=self.connector_type,
                database_url=database_url,
                query=query,
                attempts=1,
                timeout_seconds=self.timeout_seconds,
                retryable=False,
                record_found=True,
            ),
        )
