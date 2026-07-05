from __future__ import annotations

from app.services._sor_connectors_http_base import *  # noqa: F403


@dataclass(frozen=True)
class StripePaymentConnector:
    """Read one Stripe payment object for source-of-record verification."""

    payment_id: str
    bearer_token: str | None = None
    base_url: str = "https://api.stripe.com"
    path_template: str = "/v1/payment_intents/{record_ref}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "stripe_payment"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"record_ref": self.payment_id, "payment_id": self.payment_id},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=False,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = _normalise_stripe_payment_record(source.record, payment_id=self.payment_id) if source.record is not None else None
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata={
                **(source.metadata or {}),
                "payment_id": self.payment_id,
                "stripe_object": record.get("object") if record else "payment",
            },
        )


@dataclass(frozen=True)
class ShopifyAdminConnector:
    """Read one Shopify Admin record for source-of-record verification."""

    record_ref: str
    bearer_token: str | None = None
    base_url: str = "https://example.myshopify.com"
    path_template: str = "/admin/api/2025-01/orders/{record_ref}.json"
    query: Mapping[str, Any] | None = None
    record_path: str | None = "order"
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "shopify_admin"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"record_ref": self.record_ref, "order_id": self.record_ref},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=False,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = _normalise_shopify_record(source.record, record_ref=self.record_ref) if source.record is not None else None
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata={**(source.metadata or {}), "record_ref": self.record_ref},
        )


def _normalise_stripe_payment_record(record: Mapping[str, Any], *, payment_id: str) -> dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("payment_id", normalized.get("id") or payment_id)
    if isinstance(normalized.get("currency"), str):
        normalized["currency"] = normalized["currency"].upper()
    for candidate in ("amount", "amount_received", "amount_captured"):
        if candidate in normalized:
            _set_money_from_minor_units(normalized, normalized.get(candidate), currency=normalized.get("currency"))
            break
    if "status" not in normalized:
        if normalized.get("paid") is True:
            normalized["status"] = "paid"
        elif normalized.get("captured") is True:
            normalized["status"] = "captured"
    return normalized


def _normalise_shopify_record(record: Mapping[str, Any], *, record_ref: str) -> dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("record_ref", normalized.get("id") or normalized.get("admin_graphql_api_id") or record_ref)
    normalized.setdefault("order_id", normalized.get("id") or record_ref)
    if isinstance(normalized.get("currency"), str):
        normalized["currency"] = normalized["currency"].upper()
    for candidate in ("total_price", "current_total_price", "subtotal_price"):
        if candidate in normalized:
            _set_money_from_major_units(normalized, normalized.get(candidate), currency=normalized.get("currency"))
            break
    if "status" not in normalized:
        normalized["status"] = (
            normalized.get("financial_status")
            or normalized.get("fulfillment_status")
            or ("cancelled" if normalized.get("cancelled_at") else None)
        )
    return normalized


__all__ = [name for name in globals() if not name.startswith("__")]
