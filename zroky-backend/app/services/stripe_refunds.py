from __future__ import annotations

from typing import Any


def refund_observation_state(refund: dict[str, Any]) -> dict[str, Any]:
    stripe_status = str(refund.get("status") or "")
    return {
        "refund_id": refund["id"],
        "charge_id": refund.get("charge"),
        "amount_minor": int(refund.get("amount") or 0),
        "currency": str(refund.get("currency") or "").lower(),
        "status": "posted" if stripe_status == "succeeded" else stripe_status,
        "stripe_status": stripe_status,
    }
