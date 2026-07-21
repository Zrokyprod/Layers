# Zroky Phase 8 Build Report

Status: In progress
Phase: Evidence and Customer-Facing Assurance
Tracker IDs: P8-001 to P8-004

## Scope

Phase 8 turns final lifecycle state into customer-facing proof bundles that can be signed, verified, and displayed.

## Completed IDs

- P8-001 Evidence bundle schema.
- P8-002 DSSE/in-toto-style signing.
- P8-003 Evidence verifier endpoint.
- P8-004 Evidence dashboard.

## Changed Code

- `zroky-backend/app/api/routes/evidence.py`
- `zroky-backend/tests/test_final_intents_api.py`
- `zroky-dashboard/src/lib/api.ts`
- `zroky-dashboard/src/lib/evidence-ledger.ts`
- `zroky-dashboard/src/app/(dashboard)/evidence/page.tsx`
- `zroky-dashboard/src/app/(dashboard)/evidence/FocusedProofPanel.tsx`
- `zroky-dashboard/src/app/(dashboard)/evidence/page.test.tsx`

## Tests And Checks

- `python -m pytest tests/test_final_intents_api.py::test_final_evidence_bundle_requires_final_sections -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/evidence.py` passed in `zroky-backend`.
- `npm test -- --run 'src/app/(dashboard)/evidence/page.test.tsx'` passed in `zroky-dashboard`.
- `npm test -- --run src/lib/dashboard-route-contract.test.ts src/lib/evidence-ledger.test.ts` passed in `zroky-dashboard`.
- `python -m pytest tests/test_final_intents_api.py::test_final_evidence_bundle_requires_final_sections -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/evidence.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py::test_final_evidence_bundle_requires_final_sections -q` passed in `zroky-backend`.
- `python -m py_compile app/api/routes/evidence.py` passed in `zroky-backend`.

## Known Risks

- Evidence bundles are schema-normalized, stored, signed with the existing Ed25519 receipt key, verifiable for digest/signature tampering, and viewable in the evidence dashboard through direct `bundle_id` links.

## Decision

Phase 8 is complete at source-test level. Next phase: P9 Live Product Hardening.
