from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from ._sor_integrations_schema_primary import LedgerRefundConnectorStatusResponse


class StripePaymentConnectorStatusResponse(LedgerRefundConnectorStatusResponse):
    pass


class StripePaymentConnectorConfigRequest(BaseModel):
    base_url: str = Field(default="https://api.stripe.com", max_length=2048)
    path_template: str = Field(default="/v1/payment_intents/{record_ref}", max_length=512)
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    bearer_token: str | None = Field(default=None, max_length=4096)
    clear_bearer_token: bool = False

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("base_url is required")
        return cleaned

    @field_validator("bearer_token")
    @classmethod
    def _normalize_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) < 8:
            raise ValueError("bearer_token must be at least 8 characters")
        return cleaned


class StripePaymentConnectorTestRequest(BaseModel):
    payment_id: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="payment_status", max_length=64)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class StripePaymentConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: StripePaymentConnectorStatusResponse


class ShopifyConnectorStatusResponse(LedgerRefundConnectorStatusResponse):
    pass


class ShopifyConnectorConfigRequest(BaseModel):
    base_url: str = Field(..., max_length=2048)
    path_template: str = Field(default="/admin/api/2025-01/orders/{record_ref}.json", max_length=512)
    record_path: str | None = Field(default="order", max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    bearer_token: str | None = Field(default=None, max_length=4096)
    clear_bearer_token: bool = False

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("base_url is required")
        return cleaned

    @field_validator("bearer_token")
    @classmethod
    def _normalize_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) < 8:
            raise ValueError("bearer_token must be at least 8 characters")
        return cleaned


class ShopifyConnectorTestRequest(BaseModel):
    record_ref: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="shopify_record", max_length=64)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class ShopifyConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: ShopifyConnectorStatusResponse


__all__ = [name for name in globals() if not name.startswith("__")]
