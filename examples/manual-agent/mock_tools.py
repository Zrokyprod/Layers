"""Mock systems touched by the manual QA agent.

These functions never call Stripe, Slack, CRM, production, or customer systems.
They only produce deterministic payloads that make protected-action scenarios
feel realistic while Zroky receives the real action intent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def grant_access(customer_id: str, role: str) -> dict[str, Any]:
    return {
        "mock_system": "mock_access",
        "status": "granted",
        "customer_id": customer_id,
        "role": role,
        "observed_at": now_iso(),
    }


def revoke_access(customer_id: str, role: str) -> dict[str, Any]:
    return {
        "mock_system": "mock_access",
        "status": "revoked",
        "customer_id": customer_id,
        "role": role,
        "observed_at": now_iso(),
    }


def refund_payment(account_id: str, amount_minor: int, currency: str = "USD") -> dict[str, Any]:
    return {
        "mock_system": "mock_ledger",
        "status": "refund_requested",
        "account_id": account_id,
        "amount_minor": amount_minor,
        "currency": currency,
        "observed_at": now_iso(),
    }


def update_crm_record(customer_id: str, field: str, value: str) -> dict[str, Any]:
    return {
        "mock_system": "mock_crm",
        "status": "updated",
        "customer_id": customer_id,
        "field": field,
        "value": value,
        "observed_at": now_iso(),
    }


def change_feature_flag(flag: str, enabled: bool) -> dict[str, Any]:
    return {
        "mock_system": "mock_deploy",
        "status": "changed",
        "flag": flag,
        "enabled": enabled,
        "observed_at": now_iso(),
    }


def send_external_message(channel: str, recipient: str) -> dict[str, Any]:
    return {
        "mock_system": "mock_messaging",
        "status": "queued",
        "channel": channel,
        "recipient": recipient,
        "observed_at": now_iso(),
    }
