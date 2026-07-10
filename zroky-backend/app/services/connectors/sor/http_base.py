from __future__ import annotations

from app.services.connectors.sor.core import *  # noqa: F403
from app.services.connectors.sor.money import *  # noqa: F403


@dataclass(frozen=True)
class HttpJsonRecordConnector:
    """Fetch a JSON record from a customer-hosted system-of-record adapter."""

    base_url: str
    path_template: str
    path_values: Mapping[str, Any]
    query: Mapping[str, Any] | None = None
    bearer_token: str | None = None
    basic_auth_username: str | None = None
    basic_auth_password: str | None = None
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
        elif (
            self.basic_auth_username
            and self.basic_auth_username.strip()
            and self.basic_auth_password
            and self.basic_auth_password.strip()
        ):
            token = f"{self.basic_auth_username.strip()}:{self.basic_auth_password.strip()}".encode()
            headers["Authorization"] = f"Basic {b64encode(token).decode('ascii')}"
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
    record: Mapping[str, Any], *, refund_id: str, infer_plain_amount_usd: bool = True
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
    if isinstance(normalized.get("currency"), str):
        normalized["currency"] = normalized["currency"].upper()
    if "amount_minor" not in normalized:
        for candidate in ("amount_minor", "amount_cents", "amountCents", "amount_usd_cents"):
            value = normalized.get(candidate)
            if value is not None:
                _set_money_from_minor_units(normalized, value, currency=normalized.get("currency"))
                break
    if "amount_major" not in normalized:
        for candidate in ("amount_major", "amountUSD", "amountUsd", "amount_usd"):
            value = normalized.get(candidate)
            if value is not None:
                _set_money_from_major_units(normalized, value, currency=normalized.get("currency"))
                break
    if infer_plain_amount_usd and "amount_usd" not in normalized and (
        not isinstance(normalized.get("currency"), str)
        or normalized["currency"].strip().upper() in {"", "USD"}
    ):
        value = normalized.get("amount")
        if value is not None:
            normalized["amount_usd"] = value
    if "status" not in normalized:
        for candidate in ("state", "refund_status", "refundStatus"):
            value = normalized.get(candidate)
            if value is not None and _clean_text(value):
                normalized["status"] = value
                break
    return normalized


def _normalise_stripe_refund_record(
    record: Mapping[str, Any], *, refund_id: str
) -> dict[str, Any]:
    normalized = _normalise_refund_record(
        record,
        refund_id=refund_id,
        infer_plain_amount_usd=False,
    )
    normalized.setdefault("stripe_refund_id", normalized.get("refund_id") or refund_id)
    charge = normalized.get("charge")
    if charge is not None and _clean_text(charge):
        normalized.setdefault("charge_id", charge)
    payment_intent = normalized.get("payment_intent")
    if payment_intent is not None and _clean_text(payment_intent):
        normalized.setdefault("payment_intent_id", payment_intent)
    stripe_amount = normalized.get("amount")
    _set_money_from_minor_units(normalized, stripe_amount, currency=normalized.get("currency"))
    return normalized


def _normalise_razorpay_refund_record(
    record: Mapping[str, Any], *, refund_id: str
) -> dict[str, Any]:
    normalized = _normalise_refund_record(
        record,
        refund_id=refund_id,
        infer_plain_amount_usd=False,
    )
    normalized.setdefault("razorpay_refund_id", normalized.get("refund_id") or refund_id)
    payment_id = normalized.get("payment_id") or normalized.get("paymentId")
    if payment_id is not None and _clean_text(payment_id):
        normalized.setdefault("payment_id", payment_id)
        normalized.setdefault("razorpay_payment_id", payment_id)
    razorpay_amount = normalized.get("amount")
    if isinstance(normalized.get("currency"), str):
        normalized["currency"] = normalized["currency"].upper()
    _set_money_from_minor_units(
        normalized,
        razorpay_amount,
        currency=normalized.get("currency"),
        legacy_usd_alias=False,
    )
    receipt = normalized.get("receipt")
    if receipt is not None and _clean_text(receipt):
        normalized.setdefault("receipt", receipt)
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


def _normalise_hubspot_contact_record(
    record: Mapping[str, Any], *, record_ref: str
) -> dict[str, Any]:
    normalized = dict(record)
    properties = normalized.get("properties")
    if isinstance(properties, Mapping):
        for key, value in properties.items():
            normalized.setdefault(str(key), value)

    hubspot_id = normalized.get("id") or normalized.get("hs_object_id")
    if hubspot_id is not None and _clean_text(hubspot_id):
        normalized.setdefault("hubspot_id", hubspot_id)
        normalized.setdefault("hs_object_id", hubspot_id)

    normalized.setdefault("record_ref", record_ref)
    if "customer_id" not in normalized:
        for candidate in ("hs_object_id", "hubspot_id", "id", "email"):
            value = normalized.get(candidate)
            if value is not None and _clean_text(value):
                normalized["customer_id"] = value
                break
    if "customer_id" not in normalized and record_ref:
        normalized["customer_id"] = record_ref

    if isinstance(normalized.get("email"), str):
        normalized["email"] = normalized["email"].strip().lower()

    if "status" not in normalized:
        for candidate in (
            "lifecyclestage",
            "hs_lead_status",
            "customer_status",
            "lifecycle_status",
        ):
            value = normalized.get(candidate)
            if value is not None and _clean_text(value):
                normalized["status"] = value
                break
    return normalized


def _normalise_zendesk_ticket_record(
    record: Mapping[str, Any], *, record_ref: str
) -> dict[str, Any]:
    normalized = dict(record)
    ticket_id = normalized.get("id") or normalized.get("ticket_id")
    if ticket_id is not None and _clean_text(ticket_id):
        normalized["ticket_id"] = str(ticket_id)
        normalized.setdefault("record_ref", str(ticket_id))
    else:
        normalized.setdefault("record_ref", record_ref)
        normalized.setdefault("ticket_id", record_ref)

    for source, target in (
        ("requester_id", "customer_id"),
        ("assignee_id", "owner_id"),
        ("updated_at", "last_updated_at"),
    ):
        value = normalized.get(source)
        if value is not None and target not in normalized:
            normalized[target] = value
    return normalized


def _normalise_jira_issue_record(
    record: Mapping[str, Any], *, record_ref: str
) -> dict[str, Any]:
    normalized = dict(record)
    fields = normalized.get("fields")
    field_map = dict(fields) if isinstance(fields, Mapping) else {}

    issue_id = normalized.get("id") or field_map.get("id")
    issue_key = normalized.get("key") or field_map.get("key") or record_ref
    if issue_id is not None and _clean_text(issue_id):
        normalized.setdefault("jira_issue_id", str(issue_id))
    if issue_key is not None and _clean_text(issue_key):
        normalized.setdefault("jira_issue_key", str(issue_key))
        normalized.setdefault("issue_key", str(issue_key))
        normalized.setdefault("record_ref", str(issue_key))
    else:
        normalized.setdefault("record_ref", record_ref)

    summary = normalized.get("summary") or field_map.get("summary")
    if summary is not None:
        normalized.setdefault("summary", summary)

    status_obj = field_map.get("status")
    if isinstance(status_obj, Mapping):
        status_name = status_obj.get("name")
        status_id = status_obj.get("id")
        if status_name is not None:
            normalized.setdefault("status", status_name)
        if status_id is not None:
            normalized.setdefault("status_id", status_id)
    elif status_obj is not None:
        normalized.setdefault("status", status_obj)

    for source_key, target_name, target_id in (
        ("assignee", "assignee", "assignee_id"),
        ("reporter", "reporter", "reporter_id"),
        ("creator", "creator", "creator_id"),
    ):
        value = field_map.get(source_key)
        if not isinstance(value, Mapping):
            continue
        display_name = value.get("displayName") or value.get("name") or value.get("emailAddress")
        account_id = value.get("accountId") or value.get("key") or value.get("name")
        if display_name is not None:
            normalized.setdefault(target_name, display_name)
        if account_id is not None:
            normalized.setdefault(target_id, account_id)

    for source_key, target_name, target_id in (
        ("issuetype", "issue_type", "issue_type_id"),
        ("project", "project", "project_id"),
        ("priority", "priority", "priority_id"),
    ):
        value = field_map.get(source_key)
        if not isinstance(value, Mapping):
            continue
        name = value.get("name") or value.get("key")
        item_id = value.get("id") or value.get("key")
        if name is not None:
            normalized.setdefault(target_name, name)
        if item_id is not None:
            normalized.setdefault(target_id, item_id)

    for source, target in (
        ("updated", "updated_at"),
        ("created", "created_at"),
        ("resolutiondate", "resolved_at"),
    ):
        value = field_map.get(source)
        if value is not None:
            normalized.setdefault(target, value)

    labels = field_map.get("labels")
    if isinstance(labels, list):
        normalized.setdefault("labels", labels)
    return normalized


def _normalise_salesforce_record(
    record: Mapping[str, Any], *, object_type: str, record_ref: str
) -> dict[str, Any]:
    normalized = dict(record)
    sf_id = normalized.get("Id") or normalized.get("id") or record_ref
    if sf_id is not None and _clean_text(sf_id):
        normalized.setdefault("salesforce_id", sf_id)
        normalized.setdefault("record_ref", str(sf_id))
    else:
        normalized.setdefault("record_ref", record_ref)
    normalized.setdefault("object_type", object_type)

    if "status" not in normalized:
        for candidate in ("Status", "StageName", "LeadStatus", "CaseStatus"):
            value = normalized.get(candidate)
            if value is not None and _clean_text(value):
                normalized["status"] = value
                break
    if "amount_usd" not in normalized:
        amount = normalized.get("Amount")
        if amount is not None:
            normalized["amount_usd"] = amount
    return normalized


def _normalise_zoho_record(
    record: Mapping[str, Any], *, module_name: str, record_ref: str
) -> dict[str, Any]:
    normalized = dict(record)
    zoho_id = normalized.get("id") or normalized.get("Id") or record_ref
    if zoho_id is not None and _clean_text(zoho_id):
        normalized.setdefault("zoho_record_id", zoho_id)
        normalized.setdefault("record_ref", str(zoho_id))
    else:
        normalized.setdefault("record_ref", record_ref)
    normalized.setdefault("module_name", module_name)

    if "status" not in normalized:
        for candidate in ("Status", "Lead_Status", "Stage", "Deal_Stage"):
            value = normalized.get(candidate)
            if value is not None and _clean_text(value):
                normalized["status"] = value
                break
    owner = normalized.get("Owner")
    if isinstance(owner, Mapping):
        owner_name = owner.get("name") or owner.get("full_name")
        owner_id = owner.get("id")
        if owner_name is not None:
            normalized.setdefault("owner", owner_name)
        if owner_id is not None:
            normalized.setdefault("owner_id", owner_id)
    if "amount_usd" not in normalized:
        amount = normalized.get("Amount") or normalized.get("Deal_Amount")
        if amount is not None:
            normalized["amount_usd"] = amount
    return normalized


def _normalise_netsuite_finance_record(
    record: Mapping[str, Any], *, record_type: str, record_ref: str
) -> dict[str, Any]:
    normalized = dict(record)
    ns_id = (
        normalized.get("id")
        or normalized.get("internalId")
        or normalized.get("internal_id")
        or record_ref
    )
    if ns_id is not None and _clean_text(ns_id):
        normalized.setdefault("netsuite_record_id", str(ns_id))
        normalized.setdefault("record_ref", str(ns_id))
    else:
        normalized.setdefault("record_ref", record_ref)
    normalized.setdefault("record_type", record_type)

    tran_id = normalized.get("tranId") or normalized.get("tranid") or normalized.get("documentNumber")
    if tran_id is not None and _clean_text(tran_id):
        normalized.setdefault("tran_id", tran_id)

    if "status" not in normalized:
        for candidate in ("status", "approvalStatus", "orderStatus", "paymentStatus"):
            value = normalized.get(candidate)
            if isinstance(value, Mapping):
                value = value.get("refName") or value.get("name") or value.get("id")
            if value is not None and _clean_text(value):
                normalized["status"] = value
                break

    currency = normalized.get("currency")
    if isinstance(currency, Mapping):
        currency_value = (
            currency.get("refName")
            or currency.get("name")
            or currency.get("id")
            or currency.get("symbol")
        )
        if currency_value is not None:
            normalized["currency"] = currency_value
    if isinstance(normalized.get("currency"), str):
        normalized["currency"] = normalized["currency"].upper()

    if "amount_major" not in normalized:
        for candidate in ("total", "amount", "tranTotal", "foreignTotal", "netAmount"):
            value = normalized.get(candidate)
            if value is not None:
                _set_money_from_major_units(
                    normalized,
                    value,
                    currency=normalized.get("currency"),
                )
                break

    entity = normalized.get("entity") or normalized.get("vendor") or normalized.get("customer")
    if isinstance(entity, Mapping):
        entity_name = entity.get("refName") or entity.get("name")
        entity_id = entity.get("id") or entity.get("internalId")
        if entity_name is not None:
            normalized.setdefault("entity", entity_name)
        if entity_id is not None:
            normalized.setdefault("entity_id", entity_id)
    return normalized


__all__ = [name for name in globals() if not name.startswith("__")]
