# Stripe Refund Test Loop Report

Status: Verified contract and live runner
Tracker IDs: P11-009, P11-010

## Scope

This proves the first Stripe-shaped refund loop through final Zroky APIs without adding a new connector framework.

The contract test uses Stripe test-mode semantics and an authoritative Stripe refund observation shape. It does not call the live Stripe API or store a Stripe key.

The live runner calls the Stripe test API only when `STRIPE_TEST_SECRET_KEY` is set to a key starting with `sk_test_`.

## Verified Flow

Case A: real source-of-record refund exists.

1. Publish `stripe-refund-test-loop` Assurance Pack.
2. Create trusted refund intent.
3. Force `approval_required`.
4. Approve the final approval requirement with matching `binding_digest`.
5. Declare agent run claiming refund success.
6. Ingest authoritative `stripe_refund` observation with `status=succeeded`.
7. Build outcome graph.
8. Create and verify signed evidence bundle.

Result: `verification_status=verified`, signed evidence verification passes.

Case B: agent claims success but Stripe source-of-record has no refund observation.

1. Create and approve a second refund intent.
2. Declare agent run claiming refund success.
3. Do not ingest a Stripe refund observation.
4. Build outcome graph.

Result: `verification_status=failed`, graph classification is `missing`, and an open incident is created.

## Evidence

- `python -m pytest tests/test_final_intents_api.py::test_stripe_refund_test_loop_verifies_real_sor_and_catches_false_success -q`
- `python -m py_compile scripts/run_stripe_test_loop.py`
- Missing-key refusal passed: the runner exits before touching Stripe/backend when `STRIPE_TEST_SECRET_KEY` is absent.

## Live Runner

Use an existing Stripe test refund:

```powershell
$env:STRIPE_TEST_SECRET_KEY = "sk_test_..."
python scripts/run_stripe_test_loop.py --api-base-url http://127.0.0.1:8000 --project-id stripe-live-test --stripe-refund-id re_...
```

Or explicitly create a test charge and refund:

```powershell
$env:STRIPE_TEST_SECRET_KEY = "sk_test_..."
python scripts/run_stripe_test_loop.py --api-base-url http://127.0.0.1:8000 --project-id stripe-live-test --create-test-refund
```

For a hosted backend, also provide `ZROKY_API_KEY` or `ZROKY_BEARER_TOKEN` with an admin/owner-capable project context.

## Next Step

Run the live runner against a real backend using Stripe test credentials and save the JSON result.
