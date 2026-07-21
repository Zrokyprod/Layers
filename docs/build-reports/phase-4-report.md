# Zroky Phase 4 Build Report

Status: Complete at source-test level  
Phase: Assurance Pack Compiler  
Tracker IDs: P4-001 to P4-004

## Scope

Phase 4 defines workflow correctness as data before adding predicate execution, simulation, or UI.

## Completed IDs

- P4-001 Workflow Assurance Pack schema.
- P4-002 CEL predicate evaluation.
- P4-003 Pack simulation cases.
- P4-004 Minimal workflow builder UI.

## Added Code

- `zroky-backend/app/domain/assurance_pack/schema.py`
- `zroky-backend/app/domain/assurance_pack/predicate.py`
- `zroky-backend/app/domain/assurance_pack/simulation.py`
- `zroky-backend/app/api/routes/assurance_packs.py`
- `zroky-dashboard/src/app/(dashboard)/workflows/page.tsx`
- `zroky-dashboard/src/app/(dashboard)/workflows/page.test.tsx`

## Changed Code

- `zroky-backend/app/api/router.py`
- `zroky-backend/tests/test_final_intents_api.py`
- `zroky-dashboard/src/lib/api.ts`
- `zroky-dashboard/src/lib/dashboard-route-contract.ts`
- `zroky-dashboard/src/components/dashboard-shell.tsx`
- `zroky-dashboard/src/components/dashboard-shell.test.tsx`
- `zroky-dashboard/src/lib/dashboard-route-contract.test.ts`

## Tests And Checks

- `python -m pytest tests/test_final_intents_api.py tests/test_final_domain_tables.py -q` passed in `zroky-backend`.
- `python -m py_compile app/domain/assurance_pack/schema.py app/api/routes/assurance_packs.py app/api/router.py` passed in `zroky-backend`.
- `python -m py_compile app/domain/assurance_pack/schema.py app/api/routes/assurance_packs.py` passed after removing the Pydantic schema-field warning.
- `python -m py_compile app/domain/assurance_pack/predicate.py app/api/routes/assurance_packs.py` passed in `zroky-backend`.
- `python -m pytest tests/test_final_intents_api.py::test_assurance_pack_predicate_evaluator_is_bounded -q` passed in `zroky-backend`.
- `python -m py_compile app/domain/assurance_pack/simulation.py app/api/routes/assurance_packs.py` passed in `zroky-backend`.
- `npm test -- --run "src/app/(dashboard)/workflows/page.test.tsx" "src/components/dashboard-shell.test.tsx" "src/lib/dashboard-route-contract.test.ts"` passed in `zroky-dashboard`.

## Known Risks

- CEL support is a bounded subset: comparisons, boolean operators, constants, and dotted object fields. No functions/macros yet.
- Pack simulation covers success, missing, wrong, duplicate, stale, and conflict cases.
- Workflow builder is intentionally minimal: JSON draft editor, backend validation, and publish flow. No visual node canvas yet.

## Decision

Phase 4 is complete at source-test level. Next phase: P5.
