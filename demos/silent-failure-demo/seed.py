from __future__ import annotations

from _common import (
    EXECUTOR_REF,
    PACK_VERSION,
    PLAYBOOK_KEY,
    RUNNER_CREDENTIAL_REF,
    SOURCE_BINDING,
    WORKFLOW_KEY,
    ApiClient,
    DemoConfig,
    create_test_charge,
    demo_id,
    load_state,
    save_state,
)


def assurance_pack(amount_minor: int, currency: str) -> dict:
    return {
        "schema_version": "zroky.workflow_assurance_pack.v1",
        "workflow_key": WORKFLOW_KEY,
        "version": PACK_VERSION,
        "intent_schema": {"type": "object"},
        "object_types": [{"key": "refund", "schema": {"type": "object"}}],
        "effects": [
            {
                "key": "refund_posted",
                "object_type": "refund",
                "predicate": (
                    "refund.status == 'posted' and "
                    "refund.amount_minor == intent.amount_minor and "
                    "refund.currency == intent.currency and "
                    "refund.charge_id == intent.charge_id"
                ),
            }
        ],
        "source_bindings": [
            {
                "key": SOURCE_BINDING,
                "connector_capability": "stripe_refund.read",
                "object_type": "refund",
                "freshness_seconds": 300,
            }
        ],
        "recovery_playbooks": [
            {
                "key": PLAYBOOK_KEY,
                "incident_type": "missing",
                "steps": [
                    {
                        "step_key": "reissue_refund",
                        "effect_keys": ["refund_posted"],
                        "adapter": "stripe_refund",
                        "operation": "refund.create",
                        "credential_ref": RUNNER_CREDENTIAL_REF,
                        "target": {},
                        "arguments": {
                            "amount_minor": amount_minor,
                            "reason": "requested_by_customer",
                        },
                    }
                ],
            }
        ],
    }


def setup() -> dict:
    config = DemoConfig.from_env()
    api = ApiClient(config)
    state = load_state()
    run_id = demo_id()
    charge = create_test_charge(config, run_id)

    print(f"Stripe test charge ready: {charge['id']} {config.currency.upper()} {config.amount_minor}")
    connector = api.request(
        "PUT",
        "/v1/integrations/system-of-record/stripe-refund/config",
        admin=True,
        body={"bearer_token": config.stripe_secret_key},
    )
    print(f"Stripe refund connector configured: connected={connector.get('connected')}")

    pack = api.request(
        "POST",
        "/v1/assurance-packs",
        admin=True,
        body={"environment": "production", "pack": assurance_pack(config.amount_minor, config.currency)},
    )
    print(f"Assurance pack ready: {pack['workflow_key']} {pack['version']}")

    state.update(
        {
            "demo_id": run_id,
            "project": config.project,
            "workflow_key": WORKFLOW_KEY,
            "pack_id": pack["id"],
            "playbook_key": PLAYBOOK_KEY,
            "executor_ref": EXECUTOR_REF,
            "credential_ref": RUNNER_CREDENTIAL_REF,
            "charge_id": charge["id"],
            "amount_minor": config.amount_minor,
            "currency": config.currency,
        }
    )
    save_state(state)
    return state


if __name__ == "__main__":
    setup()
