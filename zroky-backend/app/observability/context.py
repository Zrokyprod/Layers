from __future__ import annotations

from contextvars import ContextVar, Token


_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="-")
_correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


def set_request_context(
    *,
    request_id: str,
    tenant_id: str,
    correlation_id: str | None = None,
) -> tuple[Token[str], Token[str], Token[str] | None]:
    request_token = _request_id_var.set(request_id)
    tenant_token = _tenant_id_var.set(tenant_id)
    if correlation_id is not None:
        correlation_token = _correlation_id_var.set(correlation_id)
        return request_token, tenant_token, correlation_token
    return request_token, tenant_token, None


def reset_request_context(tokens: tuple[Token[str], Token[str], Token[str] | None]) -> None:
    request_token, tenant_token, correlation_token = tokens
    _request_id_var.reset(request_token)
    _tenant_id_var.reset(tenant_token)
    if correlation_token is not None:
        _correlation_id_var.reset(correlation_token)


def get_request_id() -> str:
    return _request_id_var.get()


def get_tenant_id() -> str:
    return _tenant_id_var.get()


def get_correlation_id() -> str:
    return _correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> Token[str]:
    """Set correlation ID for outgoing request propagation."""
    return _correlation_id_var.set(correlation_id)
