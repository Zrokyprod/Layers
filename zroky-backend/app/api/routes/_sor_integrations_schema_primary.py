from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

class OAuthStartResponse(BaseModel):
    authorization_url: str



class LedgerRefundConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_bearer_token: bool
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class LedgerRefundConnectorConfigRequest(BaseModel):
    base_url: str = Field(..., max_length=2048)
    path_template: str = Field(default="/refunds/{refund_id}", max_length=512)
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    bearer_token: str | None = Field(default=None, max_length=4096)
    clear_bearer_token: bool = False

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


class LedgerRefundConnectorTestRequest(BaseModel):
    refund_id: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="refund", max_length=64)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class LedgerRefundConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: LedgerRefundConnectorStatusResponse


class StripeRefundConnectorStatusResponse(LedgerRefundConnectorStatusResponse):
    pass


class StripeRefundConnectorConfigRequest(BaseModel):
    base_url: str = Field(default="https://api.stripe.com", max_length=2048)
    path_template: str = Field(default="/v1/refunds/{refund_id}", max_length=512)
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


class StripeRefundConnectorTestRequest(LedgerRefundConnectorTestRequest):
    pass


class StripeRefundConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: StripeRefundConnectorStatusResponse


class RazorpayRefundConnectorStatusResponse(LedgerRefundConnectorStatusResponse):
    pass


class RazorpayRefundConnectorConfigRequest(BaseModel):
    base_url: str = Field(default="https://api.razorpay.com", max_length=2048)
    path_template: str = Field(default="/v1/refunds/{refund_id}", max_length=512)
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    key_id: str = Field(..., min_length=4, max_length=255)
    key_secret: str | None = Field(default=None, max_length=4096)
    clear_key_secret: bool = False

    @field_validator("base_url", "key_id")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value is required")
        return cleaned

    @field_validator("key_secret")
    @classmethod
    def _normalize_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) < 8:
            raise ValueError("key_secret must be at least 8 characters")
        return cleaned


class RazorpayRefundConnectorTestRequest(LedgerRefundConnectorTestRequest):
    pass


class RazorpayRefundConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: RazorpayRefundConnectorStatusResponse


class CustomerRecordConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_bearer_token: bool
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class CustomerRecordConnectorConfigRequest(BaseModel):
    base_url: str = Field(..., max_length=2048)
    path_template: str = Field(default="/customers/{customer_id}", max_length=512)
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    bearer_token: str | None = Field(default=None, max_length=4096)
    clear_bearer_token: bool = False

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


class CustomerRecordConnectorTestRequest(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="customer_record_update", max_length=64)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class CustomerRecordConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: CustomerRecordConnectorStatusResponse


class GenericRestConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_bearer_token: bool
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class GenericRestConnectorConfigRequest(BaseModel):
    base_url: str = Field(..., max_length=2048)
    path_template: str = Field(default="/records/{record_ref}", max_length=512)
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    bearer_token: str | None = Field(default=None, max_length=4096)
    clear_bearer_token: bool = False

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


class GenericRestConnectorTestRequest(BaseModel):
    record_ref: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="custom", max_length=64)
    system_ref: str | None = Field(default=None, max_length=255)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class GenericRestConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: GenericRestConnectorStatusResponse



__all__ = [name for name in globals() if not name.startswith("__")]
