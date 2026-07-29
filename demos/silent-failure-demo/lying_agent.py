from __future__ import annotations

from _common import WORKFLOW_KEY, ApiClient, DemoConfig, load_state, now_iso, save_state


def declare_lie() -> dict:
    config = DemoConfig.from_env()
    api = ApiClient(config)
    state = load_state()
    if not state.get("charge_id"):
        raise SystemExit("Run seed.py first.")

    intent_payload = {
        "customer": "Asha Sharma",
        "action": "refund_customer",
        "amount_minor": int(state["amount_minor"]),
        "currency": state["currency"],
        "charge_id": state["charge_id"],
        "reason": "duplicate support charge",
    }
    demo_id = state["demo_id"]
    intent = api.request(
        "POST",
        "/v1/intents",
        idempotency_key=f"{demo_id}:intent",
        body={
            "environment": "production",
            "agent_ref": "support-agent-demo",
            "intent": intent_payload,
        },
    )
    run = api.request(
        "POST",
        "/v1/runs",
        idempotency_key=f"{demo_id}:run",
        body={
            "environment": "production",
            "external_run_id": demo_id,
            "intent_id": intent["id"],
            "workflow_key": WORKFLOW_KEY,
            "agent_ref": "support-agent-demo",
            "status": "succeeded",
            "run": {
                "log": [
                    "customer asked for INR 4,500 refund",
                    "agent skipped Stripe refund call",
                    "agent claimed refund processed",
                ],
                "claimed_user_message": "refund processed",
                "stripe_refund_call_executed": False,
            },
            "started_at": now_iso(),
            "finished_at": now_iso(),
        },
    )

    state.update({"intent_id": intent["id"], "run_id": run["id"]})
    save_state(state)

    print("support-agent-demo: refund processed ✓")
    print("Stripe call intentionally skipped.")
    return state


if __name__ == "__main__":
    declare_lie()
