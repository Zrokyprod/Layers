"""System-of-record connectors for outcome verification.

The first production connector is intentionally narrow: read one refund row
from a customer's ledger/refund API, then let outcome_reconciliation compare
claimed-vs-actual. Connector failures never become a false pass.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from app.services.outcome_reconciliation import SourceRecord


class ConnectorConfigError(ValueError):
    """Raised when connector config is unsafe or incomplete."""


_TEMPLATE_RE = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*)}")
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}
_AUTH_FAILED_HTTP_STATUSES = {401, 403}
_RETRYABLE_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_MAX_CONNECTOR_ATTEMPTS = 4


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


def _metadata(
    *,
    connector_type: str,
    request_url: str,
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
